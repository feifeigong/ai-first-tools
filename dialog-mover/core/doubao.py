from __future__ import annotations

import sys
from pathlib import Path

from .common import localappdata, user_env

WORKSPACE_SUFFIX = Path(".doubaowork/agent_mode/workspace")
INDEX_NAME = "chrome_doubaowork-chat_0.indexeddb.leveldb"


def profile() -> Path:
    override = user_env("DOUBAO_WORK_DIR")
    if override:
        path = Path(override)
        if path.parts[-3:] == WORKSPACE_SUFFIX.parts:
            return path.parents[2]
    base = localappdata() / "DoubaoWork"
    windows = base / "User Data" / "Default"
    candidates = (base / "Default", windows) if sys.platform == "darwin" else (windows,)
    return next((path for path in candidates if (path / ".doubaowork").is_dir()
                 or (path / "IndexedDB" / INDEX_NAME).is_dir()), candidates[0])


def workspace() -> Path:
    override = user_env("DOUBAO_WORK_DIR")
    return Path(override) if override else profile() / WORKSPACE_SUFFIX


def installed() -> bool:
    return workspace().is_dir() or (profile() / ".doubaowork").is_dir() or (profile() / "IndexedDB" / INDEX_NAME).is_dir()
