"""Workbench-owned local folders. Never accept a user's existing project."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

OWNER = "ai-first-memory"
SCOPE = "workbench-library-v1"
MARKER = ".ai-first-workspace.json"


def no_links(path: Path):
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise ValueError("资料位置发生变化，已停止搬家。已有项目不会被写入。")


def create(library: Path) -> Path:
    library = library.absolute()
    no_links(library)
    parent = library / "copilot-workspaces"
    no_links(parent)
    parent.mkdir(parents=True, exist_ok=True)
    workspace = parent / uuid.uuid4().hex
    workspace.mkdir()
    with (workspace / MARKER).open("x", encoding="utf-8") as stream:
        json.dump({"owner": OWNER, "scope": SCOPE, "id": workspace.name}, stream)
    return workspace.resolve()


def validate(workspace: Path, library: Path) -> Path:
    workspace, library = workspace.absolute(), library.absolute()
    no_links(workspace)
    no_links(library)
    # Check links before canonicalizing. A Windows 8.3 alias is the same owned
    # directory, but a junction/symlink must never bypass the ownership gate.
    workspace, library = workspace.resolve(), library.resolve()
    def key(path: Path) -> Path:
        value = str(path)
        if os.name == 'nt':
            if value.startswith('\\\\?\\UNC\\'):
                value = '\\\\' + value[8:]
            elif value.startswith('\\\\?\\'):
                value = value[4:]
        return Path(value)
    if (not workspace.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", workspace.name)
            or key(workspace.parent) != key(library / "copilot-workspaces")):
        raise ValueError("智能搬家只能使用工具箱新建的资料项目，已有项目不会被写入。")
    marker = workspace / MARKER
    no_links(marker)
    try:
        saved = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("无法核对资料项目的归属，已停止写入。") from None
    if saved != {"owner": OWNER, "scope": SCOPE, "id": workspace.name}:
        raise ValueError("资料项目的归属标记发生变化，已停止写入。")
    return workspace.resolve()


def library_for(memory: Path) -> Path:
    # The caller supplies only its own memory root, never an arbitrary archive path.
    workspace = memory.absolute().parent
    library = workspace.parent.parent
    if memory.name != ".agent-memory":
        raise ValueError("不是工具箱创建的资料位置。")
    validate(workspace, library)
    return library.resolve()
