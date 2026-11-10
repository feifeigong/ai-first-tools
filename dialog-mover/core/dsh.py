"""Read and write DSH local sessions. Existing sessions are only read."""

from __future__ import annotations

import json
import os
import sys
import uuid
from io import BytesIO
from pathlib import Path

import zstandard

from .common import appdata, home


def community_root() -> Path | None:
    """DSH Desktop（社区版）把会话放在 Electron 用户数据下的 harness。Mac 同样使用 Application Support/dsh-desktop/harness。"""
    path = appdata() / "dsh-desktop" / "harness"
    return path if (path / "sessions").is_dir() else None


def official_root() -> Path | None:
    """DeepSeek Harness（官方桌面端）默认使用 ~/.dsh，可用 DSH_HOME 改走别处，这里只认默认目录。"""
    path = home() / ".dsh"
    return path if (path / "sessions").is_dir() else None


def data_root() -> Path | None:
    """社区版会话目录。测试会替换这个函数，正式读取不要再退回官方目录。"""
    return community_root()


def installed() -> bool:
    return data_root() is not None


def official_installed() -> bool:
    return official_root() is not None


def _store(product: str) -> Path | None:
    if product == "dsh_official":
        return official_root()
    return data_root()


def project_key(path: str, platform: str | None = None) -> str:
    """Match DSH's session folder names, such as --D-javaProject-kxEes--."""
    platform = platform or sys.platform
    text = os.path.normpath(path or "")
    if platform == "win32" and any(ord(ch) > 127 for ch in text):
        text = _short_path(text) or text
        text = os.path.normpath(text)
    if platform == "win32" and len(text) >= 2 and text[1] == ":":
        drive = text[0]
        rest = text[3:].strip("\\").replace("\\", "-")
        return f"--{drive}-{rest}--" if rest else f"--{drive}---"
    rest = text.strip("/\\").replace("\\", "-").replace("/", "-")
    return f"--{rest}--" if rest else "--root--"


def _short_path(path: str) -> str:
    if sys.platform != "win32" or not os.path.exists(path):
        return ""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, len(buffer))
        return buffer.value if length else ""
    except (AttributeError, OSError):
        return ""


def _text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    chunks = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") not in ("text", "reasoning", "input_text", "output_text"):
            continue
        text = str(part.get("text") or part.get("reasoning") or "").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def _read_events(path: Path) -> list[dict]:
    raw = path.read_bytes()
    with zstandard.ZstdDecompressor().stream_reader(BytesIO(raw)) as reader:
        text = reader.read().decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _find(session_id: str, root: Path | None = None) -> Path | None:
    base = root or data_root()
    if base is None:
        return None
    direct = base / "sessions"
    if not direct.is_dir():
        return None
    for path in direct.rglob("session.jsonl.zstd"):
        if path.parent.name == session_id:
            return path
    return None


def document(session_id: str, root: Path | None = None, product: str = "dsh") -> dict:
    path = _find(session_id, root or _store(product))
    if path is None:
        name = "DeepSeek 官方桌面端" if product == "dsh_official" else "DSH 社区桌面端"
        raise ValueError(f"没有找到这条{name}对话。")
    messages = []
    title = ""
    cwd = ""
    for event in _read_events(path):
        kind = event.get("type")
        if kind == "session":
            cwd = str(event.get("cwd") or "")
        elif kind == "session/title":
            title = str((event.get("data") or {}).get("title") or "")
        elif kind == "user/message":
            data = event.get("data") or {}
            text = _text(data.get("content"))
            if text:
                messages.append({"role": "user", "content": text})
        elif kind == "assistant/message":
            message = (event.get("data") or {}).get("message") or {}
            text = _text(message.get("content"))
            if text:
                messages.append({"role": "assistant", "content": text})
    if not messages:
        raise ValueError("这条 DSH 对话没有可读取的正文。")
    return {"id": session_id, "title": title or "未命名对话", "cwd": cwd, "messages": messages}


def groups(root: Path | None = None, product: str = "dsh") -> list[dict]:
    from .common import finish_groups, folder_name, make_group, make_session

    base = root or _store(product)
    if base is None:
        return []
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for path in sorted((base / "sessions").rglob("session.jsonl.zstd")):
        try:
            item = document(path.parent.name, base)
        except ValueError:
            continue
        folder = item.get("cwd") or ""
        if folder not in grouped:
            grouped[folder] = []
            order.append(folder)
        grouped[folder].append(
            make_session(path.parent.name, item["title"], folder=folder, source=product)
        )
    built = [
        make_group(folder_name(folder) if folder else "没有目录", "folder" if folder else "none", grouped[folder], path=folder)
        for folder in order
    ]
    return finish_groups(built)


def group_turns(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """把连续的助手正文收成一轮。工具结果没有可见文字，不单独占一条。"""
    turns: list[tuple[str, str]] = []
    pending_user = ""
    pending_assistant: list[str] = []

    def flush() -> None:
        nonlocal pending_user, pending_assistant
        if not pending_user and not pending_assistant:
            return
        turns.append((pending_user, "\n\n".join(pending_assistant)))
        pending_user = ""
        pending_assistant = []

    for role, text in messages:
        if role == "user":
            if pending_user or pending_assistant:
                flush()
            pending_user = text
        else:
            pending_assistant.append(text)
    flush()
    return turns


def compose_events(session_id: str, created: int, directory: str, title: str, messages: list[tuple[str, str]]) -> tuple[list[dict], int]:
    """按官方日志顺序写：先开回合和步骤，再写正文。正文不能出现在第一个步骤之前。"""
    events: list[dict] = [{
        "type": "session",
        "version": 0,
        "id": session_id,
        "createdAt": created,
        "cwd": directory,
        "delegationDepth": 0,
        "agentPreset": "standard",
    }]
    seq = 0
    user_seqs: list[int] = []

    def push(kind: str, data: dict, surface: bool = False, sources: list[int] | None = None) -> int:
        nonlocal seq
        current = seq
        event = {"type": kind, "seq": current, "time": created, "data": data}
        if surface:
            event["surfaceOp"] = "append"
        if sources:
            event["sourceEventSeqs"] = sources
        events.append(event)
        seq += 1
        return current

    for turn_no, (user_text, assistant_text) in enumerate(group_turns(messages), start=1):
        push("turn/start", {"turn": turn_no})
        push("step/start", {"turn": turn_no, "step": 1})
        if user_text:
            user_seqs.append(push("user/message", {
                "id": str(uuid.uuid4()),
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
                "source": {"kind": "user"},
            }, surface=True))
        chunk_seqs: list[int] = []
        if assistant_text:
            chunk_seqs.append(push("assistant/chunk", {
                "turn": turn_no,
                "step": 1,
                "chunk": {"type": "text-delta", "index": 0, "text": assistant_text},
            }))
            push("assistant/message", {
                "turn": turn_no,
                "step": 1,
                "message": {
                    "id": str(uuid.uuid4()),
                    "role": "assistant",
                    "content": [{"type": "text", "text": assistant_text}],
                    "source": {"kind": "model", "provider": "zcode", "model": "history"},
                },
            }, surface=True, sources=chunk_seqs)
        push("step/end", {"turn": turn_no, "step": 1})
        push("turn/end", {"turn": turn_no, "reason": {"kind": "completed"}})
    title_seq = push("session/title", {
        "title": title,
        "messageSeqs": user_seqs,
        "source": {"kind": "user" if not user_seqs else "fallback"},
    })
    return events, title_seq


def import_document(document: dict, directory: str, root: Path | None = None, product: str = "dsh") -> dict:
    base = root or _store(product)
    if base is None:
        if product == "dsh_official":
            raise ValueError("没有找到 DeepSeek 官方桌面端的会话目录。请先打开一次 DeepSeek Harness。")
        raise ValueError("没有找到 DSH 社区桌面端的会话目录。请先打开一次 DSH Desktop。")
    if not directory or not Path(directory).is_dir():
        raise ValueError("请先选好要放进去的文件夹。")
    messages = []
    for message in document.get("messages") or []:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _text(message.get("content"))
        if text:
            messages.append((role, text))
    if not messages:
        raise ValueError("这条对话没有可写入 DSH 的正文。")
    created = int(__import__("time").time() * 1000)
    session_id = "session-" + str(uuid.uuid4())
    title = document.get("title") or "未命名对话"
    events, seq = compose_events(session_id, created, directory, title, messages)
    folder = base / "sessions" / project_key(directory) / session_id
    folder.mkdir(parents=True, exist_ok=True)
    packed = pack_frames(events)
    destination = folder / "session.jsonl.zstd"
    temporary = destination.with_suffix(".zstd.tmp")
    temporary.write_bytes(packed)
    temporary.replace(destination)
    _index(base, session_id, directory, created)
    _projection(base, session_id, directory, created, title, seq)
    reread = document_messages(destination)
    expected = [text for _user, assistant in group_turns(messages) for text in (_user, assistant) if text]
    if expected != [item["content"] for item in reread]:
        destination.unlink(missing_ok=True)
        raise ValueError("写入 DSH 后重新读取不一致，已撤销这次写入。")
    refreshed = _refresh_app(product, base)
    return {"id": session_id, "location": str(destination), "refreshed": refreshed}


def pack_frames(events: list[dict]) -> bytes:
    """官方和社区版都要求第一帧只有会话头，后面的事件单独成帧，并带校验和。"""
    header = (json.dumps(events[0], ensure_ascii=False) + "\n").encode("utf-8")
    body = ("\n".join(json.dumps(event, ensure_ascii=False) for event in events[1:]) + "\n").encode("utf-8")
    compressor = zstandard.ZstdCompressor(write_checksum=True)
    return compressor.compress(header) + compressor.compress(body)


def document_messages(path: Path) -> list[dict]:
    saved = []
    for event in _read_events(path):
        kind = event.get("type")
        if kind == "user/message":
            text = _text((event.get("data") or {}).get("content"))
        elif kind == "assistant/message":
            text = _text(((event.get("data") or {}).get("message") or {}).get("content"))
        else:
            continue
        if text:
            role = "user" if kind == "user/message" else "assistant"
            saved.append({"role": role, "content": text})
    return saved


def _index(root: Path, session_id: str, directory: str, created: int) -> None:
    path = root / "storages" / "session_projcache.json"
    if not path.is_file():
        return
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    tables = cache.setdefault("tables", {})
    sessions = tables.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        return
    current = sessions.get(session_id)
    if not isinstance(current, dict):
        current = {}
        sessions[session_id] = current
    current["identity"] = {"createdAt": created, "cwd": directory}
    rows = current.setdefault("rows", {})
    if not isinstance(rows, dict):
        rows = {}
        current["rows"] = rows
    meta = rows.get("sessionListMetadata")
    if not isinstance(meta, dict):
        meta = {"ver": 1, "seq": 1, "val": {}}
        rows["sessionListMetadata"] = meta
    val = meta.setdefault("val", {})
    if isinstance(val, dict):
        val["blank"] = False
        val["lastPromptAt"] = created
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _projection(root: Path, session_id: str, directory: str, created: int, title: str, seq: int) -> None:
    """侧栏读的是每条会话一份的投影，不读整份旧缓存。"""
    folder = root / "storages" / "session_projcache" / "sessions"
    folder.mkdir(parents=True, exist_ok=True)
    record = {
        "version": 4,
        "record": {
            "identity": {"createdAt": created, "cwd": directory},
            "rows": {
                "sessionListMetadata": {
                    "ver": 1,
                    "seq": seq,
                    "val": {"blank": False, "lastPromptAt": created},
                },
                "title": {"ver": 1, "seq": seq, "val": title},
            },
        },
    }
    path = folder / f"{session_id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _refresh_app(product: str, base: Path) -> bool:
    """正在运行的桌面端只在重新连接时重读会话列表。写完后把对应窗口重新打开。"""
    live = official_root() if product == "dsh_official" else data_root()
    if live is None or Path(base).resolve() != Path(live).resolve() or sys.platform != "win32":
        return False
    image = "DeepSeek Harness.exe" if product == "dsh_official" else "DSH Desktop.exe"
    script = (
        "$image = $env:AI_FIRST_DSH_IMAGE; "
        "$procs = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq $image }); "
        "if (-not $procs) { exit 2 }; "
        "$main = $procs | Where-Object { $_.CommandLine -and $_.CommandLine -notmatch '--type=' -and $_.CommandLine -notmatch '--no-open' } | Select-Object -First 1; "
        "if (-not $main) { $main = $procs | Select-Object -First 1 }; "
        "$exe = $main.ExecutablePath; "
        "if (-not $exe) { exit 3 }; "
        "foreach ($proc in $procs) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }; "
        "$deadline = (Get-Date).AddSeconds(8); "
        "$name = [IO.Path]::GetFileNameWithoutExtension($image); "
        "while ((Get-Date) -lt $deadline) { "
        "  $left = @(Get-Process -Name $name -ErrorAction SilentlyContinue); "
        "  if (-not $left) { break }; "
        "  Start-Sleep -Milliseconds 300 "
        "}; "
        "Start-Process -FilePath $exe; "
        "exit 0"
    )
    try:
        result = __import__("subprocess").run(
            ["powershell", "-NoProfile", "-Command", script],
            env={**os.environ, "AI_FIRST_DSH_IMAGE": image},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, __import__("subprocess").SubprocessError):
        _note(f"refresh {product}: failed to start")
        return False
    _note(f"refresh {product}: exit {result.returncode}")
    return result.returncode == 0


def _note(text: str) -> None:
    try:
        from .mover import log
    except Exception:
        return
    log(text)
