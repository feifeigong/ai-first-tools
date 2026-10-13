"""Shared helpers: paths, time text, read-only SQLite access."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

_isolated_home: Path | None = None


def home() -> Path:
    if _isolated_home is not None:
        return _isolated_home
    if sys.platform != "win32":
        return Path(os.environ.get("HOME") or Path.home())
    return Path(os.environ.get("USERPROFILE") or Path.home())


def appdata() -> Path:
    if sys.platform == "darwin":
        return Path(os.environ.get("APPDATA") or home() / "Library" / "Application Support")
    return Path(os.environ.get("APPDATA") or home() / "AppData" / "Roaming")


def localappdata() -> Path:
    if sys.platform == "darwin":
        return Path(os.environ.get("LOCALAPPDATA") or appdata())
    return Path(os.environ.get("LOCALAPPDATA") or home() / "AppData" / "Local")


def _registry_env(name: str) -> str:
    """User and machine environment values, for apps started from the desktop."""
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        for root, sub in (
            (winreg.HKEY_CURRENT_USER, "Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(root, sub) as key:
                    value, _ = winreg.QueryValueEx(key, name)
                    if value:
                        return os.path.expandvars(str(value))
            except OSError:
                continue
    except ImportError:
        pass
    return ""


def codex_home() -> Path | None:
    candidates = []
    for value in (os.environ.get("CODEX_HOME"), _registry_env("CODEX_HOME")):
        if value:
            candidates.append(Path(value))
    candidates.append(home() / ".codex")
    for path in candidates:
        if (path / "sessions").is_dir():
            return path
    return None


def user_env(name: str) -> str:
    """An environment variable as the user set it, even if this app was started
    from the desktop (which may not have inherited it)."""
    return os.environ.get(name) or _registry_env(name)


def proxy_env() -> dict:
    """Proxy settings saved for the user, for apps started from the desktop."""
    found = {}
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY"):
        value = os.environ.get(name) or _registry_env(name)
        if value:
            found[name] = value
    return found


def read_db(path: Path) -> sqlite3.Connection:
    """Open a database strictly read-only; never create, never write."""
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path or "")).rstrip("\\/")


def same_path(left: str, right: str) -> bool:
    return bool(left) and bool(right) and norm(left) == norm(right)


def under_path(path: str, parent: str) -> bool:
    left, right = norm(path), norm(parent)
    return bool(left) and bool(right) and (left == right or left.startswith(right + os.sep))


def folder_name(path: str) -> str:
    return Path(path).name or path


def as_millis(value) -> int:
    if isinstance(value, str) and not value.strip().replace(".", "", 1).isdigit():
        return _iso_millis(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number <= 0:
        return 0
    if number < 10**12:
        number *= 1000
    return int(number)


def _iso_millis(text: str) -> int:
    import re
    from datetime import datetime

    cleaned = re.sub(r"(\.\d{6})\d+", r"\1", text.strip())
    try:
        stamp = datetime.fromisoformat(cleaned)
    except ValueError:
        return 0
    if stamp.year < 2000:
        return 0
    return int(stamp.timestamp() * 1000)


def when_text(millis: int) -> str:
    if not millis:
        return ""
    delta = max(0, time.time() - millis / 1000)
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{int(delta // 60)} 分钟前"
    if delta < 86400:
        return f"{int(delta // 3600)} 小时前"
    if delta < 86400 * 30:
        return f"{int(delta // 86400)} 天前"
    stamp = time.localtime(millis / 1000)
    return time.strftime("%Y-%m-%d", stamp)


def uri_to_path(uri: str) -> str:
    text = uri or ""
    for _ in range(3):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    if text.startswith("file:"):
        text = urlparse(text).path
    if sys.platform != "win32":
        return text
    text = text.replace("/", "\\")
    if len(text) > 3 and text[0] == "\\" and text[2] == ":":
        text = text[1:]
    return text


def open_external(value: str) -> None:
    if sys.platform == "win32":
        os.startfile(value)
    elif sys.platform == "darwin":
        subprocess.run(["/usr/bin/open", "--", value], check=True, timeout=15)
    else:
        subprocess.run(["xdg-open", value], check=True, timeout=15)


def make_session(
    sid: str,
    title: str,
    millis: int = 0,
    folder: str = "",
    movable: bool = True,
    note: str = "",
    root: str = "",
    kind: str = "",
    source: str = "",
) -> dict:
    return {
        "id": sid,
        "title": (title or "").strip() or "未命名对话",
        "when": when_text(millis),
        "ts": millis,
        "folder": folder or "",
        "movable": movable,
        "note": note,
        "root": root,
        "kind": kind,
        "source": source,
    }


def make_group(title: str, kind: str, sessions: list[dict], path: str = "", ordered: bool = False) -> dict:
    """`ordered` keeps the order the app itself uses; otherwise newest first."""
    if not ordered:
        sessions = sorted(sessions, key=lambda item: item["ts"], reverse=True)
    return {"title": title, "kind": kind, "path": path, "sessions": sessions}


def finish_groups(groups: list[dict], keep: bool = False) -> list[dict]:
    """Drop empty groups. `keep` leaves them in the order given (the app's own order)."""
    groups = [group for group in groups if group["sessions"]]
    if keep:
        return groups
    order = {"task": 0, "space": 1, "project": 1, "folder": 1, "recent": 2, "none": 3}
    groups.sort(
        key=lambda group: (
            order.get(group["kind"], 1),
            -max((item["ts"] for item in group["sessions"]), default=0),
        )
    )
    return groups
