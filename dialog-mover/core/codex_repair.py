"""Create a compatible copy of one legacy import; never edit the old thread.

This is an explicit repair operation, not a background migration or a diagnostic.
Its caller must have permission to read that thread's content and create a copy.
All original files are retained verbatim in the workbench's private repair area.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import codex_import
from .chatgpt import _norm

MAX_BYTES = 100 * 1024 * 1024
ENVELOPES = {'session_meta', 'response_item', 'event_msg', 'world_state',
             'turn_context', 'token_usage_record'}
ITEMS = {'message', 'reasoning', 'function_call', 'function_call_output',
         'custom_tool_call', 'custom_tool_call_output', 'web_search_call', 'compaction', 'additional_tools'}


def plain(path: Path) -> None:
    if not path.is_absolute() or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                                     for p in (path, *path.parents)):
        raise ValueError('修复位置无法安全核对，原记录未改动。')


def inside(path: Path, root: Path) -> bool:
    if os.name == 'nt':
        return _norm(str(path.resolve())).startswith(_norm(str(root.resolve())) + '\\')
    return path.resolve().is_relative_to(root.resolve()) and path.resolve() != root.resolve()


def _stamp(record: dict) -> datetime:
    value = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('原记录缺少明确时区，未生成修复副本。')
    return value


def compatible_records(chunks: list[list[dict]], old_id: str, new_id: str) -> tuple[list[dict], int]:
    """Validate known files, preserve user/assistant history, discard replay links.

    Original runtime instructions and capability declarations stay in the full
    archive, not in the active instruction hierarchy of the new thread.
    Distinct later files must contain later, completed turns. Branch conflicts
    are rejected rather than silently selecting or interleaving messages.
    """
    uuid.UUID(old_id); uuid.UUID(new_id)
    if not chunks or len(chunks) > 8:
        raise ValueError('没有找到唯一的旧版搬家记录。')
    first = chunks[0][0] if chunks[0] else {}
    if first.get('type') != 'session_meta' or first.get('payload', {}).get('dialog_mover_import_format') not in {
            'paginated-import-v1', 'paginated-import-v2', 'paginated-import-v3'}:
        raise ValueError('这不是可识别的旧版搬家记录，原记录未改动。')
    meta = {'timestamp': first['timestamp'], 'type': 'session_meta',
            'payload': {'id': new_id, 'cli_version': first['payload'].get('cli_version', '')}}
    output = [meta]
    previous_end = None
    known_turns = set()
    archived_runtime = 0
    for chunk in chunks:
        if not chunk or chunk[0].get('type') != 'session_meta' or chunk[0].get('payload', {}).get('id') != old_id:
            raise ValueError('原记录的编号不一致，未生成修复副本。')
        starts = {}; complete = set(); response_times = []
        for entry in chunk:
            if not isinstance(entry, dict) or entry.get('type') not in ENVELOPES:
                raise ValueError('记录中出现未知格式，完整资料保留，未猜测修复。')
            at = _stamp(entry)
            payload = entry.get('payload')
            if not isinstance(payload, dict):
                raise ValueError('原记录格式不完整，未生成修复副本。')
            if entry['type'] == 'event_msg':
                if payload.get('type') == 'task_started':
                    turn = payload.get('turn_id')
                    if not isinstance(turn, str) or turn in starts:
                        raise ValueError('原记录的轮次无法核对，未生成修复副本。')
                    starts[turn] = at
                if payload.get('type') == 'task_complete':
                    complete.add(payload.get('turn_id'))
                continue
            if entry['type'] != 'response_item':
                continue
            kind = payload.get('type')
            if kind not in ITEMS:
                raise ValueError('记录中出现未知内容格式，未猜测修复。')
            if kind == 'additional_tools' or kind == 'message' and payload.get('role') in {'system', 'developer'}:
                archived_runtime += 1
                continue
            if kind == 'message' and payload.get('role') not in {'user', 'assistant'}:
                raise ValueError('原记录的消息角色无法核对，未生成修复副本。')
            response_times.append(at)
            output.append({'timestamp': entry['timestamp'], 'type': 'response_item', 'payload': copy.deepcopy(payload)})
        if set(starts) != complete:
            raise ValueError('这条对话还有未结束的轮次，请等任务结束后再修复。')
        if set(starts) & known_turns:
            raise ValueError('发现重叠的对话分支，未猜测合并，原记录保留。')
        if response_times and previous_end is not None and min(response_times) < previous_end:
            raise ValueError('记录的先后顺序存在冲突，未猜测合并。')
        if response_times:
            previous_end = max(response_times)
        known_turns.update(starts)
    # Existing v4 conversion preserves foreign reasoning/search/compaction as
    # history and regenerates all display IDs/ordinals, without response links.
    result = codex_import.paginated_history(output, new_id)
    if any(entry.get('type') == 'response_item' and entry['payload']['type'] in codex_import.NONPORTABLE_ITEMS for entry in result):
        raise ValueError('兼容转换未通过，未生成修复副本。')
    return result, archived_runtime


def _uuid7() -> str:
    milliseconds = time.time_ns() // 1_000_000
    random = secrets.randbits(74)
    return str(uuid.UUID(int=(milliseconds << 80) | (7 << 76) | ((random >> 62) << 64)
                         | (2 << 62) | (random & ((1 << 62) - 1))))


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def create_copy(*, root: Path, archive_root: Path, source_paths: list[Path], old_id: str,
                title: str, directory: str, env: dict, approved: bool = False) -> dict:
    if approved is not True:
        raise ValueError('尚未授权读取这条对话的正文并创建副本。')
    root = root.absolute(); archive_root = archive_root.absolute()
    plain(root); plain(archive_root)
    private_archive = Path(env['LOCALAPPDATA']) / 'AI一手工具工作台' / 'memory-preview' / 'codex-repairs'
    if _norm(str(archive_root)) != _norm(str(private_archive)) or not 1 <= len(source_paths) <= 8:
        raise ValueError('修复原档只能保存在工作台自己的资料区。')
    if Path(env['CODEX_HOME']).resolve() != root.resolve() or not Path(directory).is_dir():
        raise ValueError('修复目标无法核对，原记录未改动。')
    database = root / 'state_5.sqlite'; plain(database)
    codex_import.validate(database)
    snapshots = []
    total_bytes = 0
    for path in source_paths:
        path = path.absolute(); plain(path)
        if not inside(path, root / 'sessions') or path.suffix != '.jsonl':
            raise ValueError('原记录位置不在目标记录库中，未读取正文。')
        if any(path.samefile(previous[0]) for previous in snapshots):
            continue
        before = path.stat()
        if before.st_size > MAX_BYTES:
            raise ValueError('原记录过大，未生成修复副本。')
        raw = path.read_bytes()
        total_bytes += len(raw)
        if total_bytes > MAX_BYTES or any(len(line) > 16 * 1024 * 1024 for line in raw.splitlines()):
            raise ValueError('原记录过大，未生成修复副本。')
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('这条对话仍在更新，原记录未改动。')
        records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        snapshots.append((path, raw, records, hashlib.sha256(raw).hexdigest()))
    new_id = _uuid7()
    records, runtime_count = compatible_records([row[2] for row in snapshots], old_id, new_id)
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        original = connection.execute('SELECT title,name,cwd,rollout_path,originator,source FROM threads WHERE id=?', (old_id,)).fetchone()
    if not original or title not in original[:2] or _norm(original[2]) != _norm(directory) or original[4] != 'codex_work_desktop' or original[5] != 'vscode':
        raise ValueError('原对话登记已变化，未生成修复副本。')
    if not any(path.samefile(Path(original[3])) for path, *_ in snapshots):
        raise ValueError('没有包含这条对话当前的记录，未生成修复副本。')
    receipt_dir = archive_root / str(uuid.UUID(old_id)); plain(receipt_dir)
    receipt_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = receipt_dir / 'repair.lock'; plain(lock)
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    receipt_path = receipt_dir / 'receipt.json'; plain(receipt_path)
    digests = [row[3] for row in snapshots]
    committed = False; path = None
    try:
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if receipt.get('sourceDigests') != digests or receipt.get('oldId') != old_id:
                raise ValueError('原对话在上次修复后又有变化，已有副本保留，未重复创建。')
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
                saved = connection.execute('SELECT id FROM threads WHERE id=?', (receipt.get('newId'),)).fetchone()
            if saved and receipt.get('state') in {'prepared', 'saved'}:
                return {'ok': True, 'reused': True, 'newId': saved[0], 'modelRequests': 0, 'originalUnchanged': True}
            raise ValueError('已有修复登记需要核对，未重复创建。')
        for index, (_, raw, _, _) in enumerate(snapshots):
            archive = receipt_dir / f'original-{index + 1}.jsonl'; plain(archive)
            if archive.exists() and archive.read_bytes() != raw:
                raise ValueError('已有原档与当前记录不同，原档保留，未覆盖。')
            if not archive.exists():
                with archive.open('xb') as stream:
                    stream.write(raw)
        now = datetime.now(timezone.utc)
        path = root / 'sessions' / now.strftime('%Y/%m/%d') / f'rollout-{now:%Y-%m-%dT%H-%M-%S}-{new_id}.jsonl'
        plain(path); path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ValueError('新副本编号已存在，未覆盖。')
        receipt = {'version': 1, 'oldId': old_id, 'newId': new_id, 'sourceDigests': digests, 'state': 'prepared'}
        _atomic_json(receipt_path, receipt)
        for source, raw, _, _ in snapshots:
            if source.read_bytes() != raw:
                raise ValueError('这条对话仍在更新，未登记修复副本。')
        with path.open('x', encoding='utf-8') as stream:
            stream.write(''.join(json.dumps(entry, ensure_ascii=False) + '\n' for entry in records))
        user = next((entry['payload'] for entry in records if entry.get('type') == 'response_item'
                     and entry['payload'].get('type') == 'message' and entry['payload'].get('role') == 'user'), None)
        if user is None:
            raise ValueError('没有可恢复的用户正文，未登记修复副本。')
        document = {'cwd': directory, 'title': title + '（兼容修复）', 'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': part['text']} for part in user.get('content', []) if part.get('type') == 'input_text']}]}
        codex_import.register(path, new_id, document, 'chatgpt_work', env)
        committed = True
        receipt.update(state='saved', runtimeRecordsArchived=runtime_count, sourceFiles=len(snapshots))
        _atomic_json(receipt_path, receipt)
        return {'ok': True, 'reused': False, 'newId': new_id, 'sourceFiles': len(snapshots),
                'runtimeRecordsArchived': runtime_count, 'originalUnchanged': True, 'modelRequests': 0}
    finally:
        # A committed index entry must never be left pointing at a deleted file.
        if not committed and path is not None and path.exists():
            path.unlink()
        os.close(descriptor)
        lock.unlink(missing_ok=True)
