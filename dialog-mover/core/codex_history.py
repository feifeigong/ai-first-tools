"""Read native plain/compressed history without unpacking into the source store."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

import zstandard

from .common import read_db

MAX_HEADER = 128 * 1024
MAX_LINE = 16 * 1024 * 1024
MAX_BYTES = 256 * 1024 * 1024
MAX_WINDOW = 64 * 1024 * 1024  # pinned C backend passes bytes to libzstd
ENVELOPES = {'session_meta', 'response_item', 'event_msg', 'turn_context',
             'world_state', 'token_usage_record', 'compacted'}
UNREADABLE = '这条记录的本地文件暂时无法读取，请在 ChatGPT 打开后刷新列表。'


def _canonical(path: Path) -> Path:
    value = str(path.resolve())
    if os.name == 'nt':
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
    return Path(value)


def _safe(path: Path, directory: Path) -> bool:
    try:
        boundary = _canonical(directory)
        if not path.is_file() or not _canonical(path).is_relative_to(boundary):
            return False
        # Reject links inside the history tree. Ancestors above the selected root
        # are not part of it (macOS commonly exposes /var through /private/var).
        cursor = path
        while _canonical(cursor) != boundary:
            if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                return False
            if cursor.parent == cursor:
                return False
            cursor = cursor.parent
        return True
    except OSError:
        return False


def files(root: Path, folder: str = 'sessions') -> dict[str, Path]:
    result = {}
    directory = root / folder
    for pattern in ('rollout-*.jsonl.zst', 'rollout-*.jsonl'):
        for path in sorted(directory.rglob(pattern)):
            if not _safe(path, directory):
                continue
            name = path.name.removesuffix('.zst').removesuffix('.jsonl')
            try:
                sid = str(uuid.UUID(name[-36:]))
            except ValueError:
                continue
            result[sid] = path
    return result


def _chunks(path: Path):
    """Bound frame windows/output; reject incomplete frames including concatenations.

    decompressobj has no max_output parameter. Tiny compressed inputs bound each
    call's expansion; no unbounded one-shot decompression is used.
    """
    with path.open('rb') as stream:
        if path.suffix != '.zst':
            while block := stream.read(65536):
                yield block
            return
        decoder = None
        total = frames = compressed = 0
        while block := stream.read(128):
            compressed += len(block)
            if compressed > MAX_BYTES:
                raise ValueError(UNREADABLE)
            while block:
                if decoder is None:
                    frames += 1
                    if frames > 4096:
                        raise ValueError(UNREADABLE)
                    decoder = zstandard.ZstdDecompressor(max_window_size=MAX_WINDOW).decompressobj()
                decoded = decoder.decompress(block)
                total += len(decoded)
                if total > MAX_BYTES:
                    raise ValueError('这条记录过大，未开始搬家，原记录已保留。')
                if decoded:
                    yield decoded
                block = decoder.unused_data if decoder.eof else b''
                if decoder.eof:
                    decoder = None
        if decoder is not None or not frames:
            raise ValueError(UNREADABLE)


def metadata(path: Path | None) -> dict:
    """Decode only the first session_meta; never parse or return chat content."""
    if path is None:
        return {}
    try:
        pending = bytearray()
        with closing(_chunks(path)) as chunks:
            for block in chunks:
                head, separator, _ = block.partition(b'\n')
                pending.extend(head)
                if len(pending) > MAX_HEADER:
                    return {}
                if separator:
                    break
            else:
                return {}
        record = json.loads(pending)
        payload = record.get('payload') if isinstance(record, dict) and record.get('type') == 'session_meta' else None
        return payload if isinstance(payload, dict) else {}
    except (OSError, UnicodeError, ValueError, zstandard.ZstdError):
        return {}


def resolve(root: Path, sid: str, logical: str = '', known: dict | None = None) -> Path | None:
    candidates = []
    if logical:
        path = Path(logical)
        candidates.extend((path, Path(str(path) + '.zst')) if path.suffix == '.jsonl' else (path,))
    fallback = (known if known is not None else files(root)).get(sid.lower())
    if fallback:
        candidates.append(fallback)
    for path in dict.fromkeys(candidates):
        if not path.name.endswith(('.jsonl', '.jsonl.zst')) or not _safe(path, root / 'sessions'):
            continue
        if str(metadata(path).get('id', '')).lower() == sid.lower():
            return path
    return None


def _validate_line(raw: bytes, sid: str, first: bool) -> None:
    if len(raw) > MAX_LINE:
        raise ValueError(UNREADABLE)
    record = json.loads(raw.decode('utf-8'))
    if not isinstance(record, dict) or record.get('type') not in ENVELOPES or not isinstance(record.get('payload'), dict):
        raise ValueError('这条记录使用了暂不支持的格式，未开始搬家，原记录已保留。')
    if record['type'] == 'session_meta':
        if not first or str(record['payload'].get('id', '')).lower() != sid.lower():
            raise ValueError(UNREADABLE)
        if record.get('ordinal', 0) != 0:
            raise ValueError('这条记录在本机还不完整，请在 ChatGPT 打开完整记录后重试。')
    elif first:
        raise ValueError(UNREADABLE)


def _snapshot(path: Path, target: Path, sid: str) -> None:
    before = path.stat()
    pending = bytearray()
    total = lines = 0
    try:
        with target.open('xb') as output, closing(_chunks(path)) as chunks:
            for block in chunks:
                total += len(block)
                if total > MAX_BYTES:
                    raise ValueError(UNREADABLE)
                output.write(block)
                pending.extend(block)
                while (end := pending.find(b'\n')) >= 0:
                    raw = bytes(pending[:end]); del pending[:end + 1]
                    if not raw.strip():
                        raise ValueError(UNREADABLE)
                    _validate_line(raw, sid, lines == 0)
                    lines += 1
                if len(pending) > MAX_LINE:
                    raise ValueError(UNREADABLE)
            if pending or not lines:
                raise ValueError(UNREADABLE)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('这条对话仍在更新，请稍后再搬，原记录没有改动。')
    except (UnicodeError, json.JSONDecodeError, zstandard.ZstdError) as error:
        raise ValueError(UNREADABLE) from error


@contextmanager
def export_home(root: Path, sid: str):
    """Present a compressed selection to the pinned engine in an isolated home.

    The original index may still point at the logical .jsonl filename. Do not
    materialize that filename in the real source or leak this home to imports.
    """
    logical = ''
    database = root / 'state_5.sqlite'
    if database.is_file():
        with closing(read_db(database)) as db:
            row = db.execute('SELECT rollout_path FROM threads WHERE id=?', (sid,)).fetchone()
            logical = row[0] if row else ''
    path = resolve(root, sid, logical)
    if path is None:
        raise ValueError(UNREADABLE)
    if path.suffix != '.zst':
        yield None
        return
    with tempfile.TemporaryDirectory(prefix='ai-first-history-read-') as scratch:
        home = Path(scratch)
        (home / 'sessions').mkdir()
        _snapshot(path, home / 'sessions' / f'rollout-{sid}.jsonl', sid)
        yield home
