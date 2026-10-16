"""Honor the local workbench's startup preference without changing task permissions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def allow_background_watch(argv: list[str], environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    # Interactive CLI use keeps its existing behavior. The original Windows startup
    # task and supervisor both use exactly `watch --quiet`.
    if argv != ["watch", "--quiet"] or env.get("AI_FIRST_MANUAL_WATCH") == "1":
        return True
    local = env.get("LOCALAPPDATA")
    if not local:
        return True
    name = "bundled-auto-resume-startup.json" if getattr(sys, "frozen", False) else "auto-resume-startup.json"
    path = Path(local) / "AI一手工具工作台" / name
    if not path.exists():
        return True
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return isinstance(value, dict) and value.get("autostart") is True
    except (OSError, ValueError):
        return False
