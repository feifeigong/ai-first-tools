#!/usr/bin/env python3
from __future__ import annotations

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_auto_resume.workspace_control import allow_background_watch

if __name__ == "__main__":
    # These controls never load/save ordinary CLI settings or enter the quota loop.
    if len(sys.argv) == 3 and sys.argv[1] == "--watch-status":
        from codex_auto_resume.watch_control import write_status
        raise SystemExit(write_status(Path(sys.argv[2])))
    if sys.argv[1:] == ["--request-stop"]:
        from codex_auto_resume.watch_control import request_stop
        raise SystemExit(request_stop())
    if getattr(sys, "frozen", False):
        native = Path(sys._MEIPASS) / "bin"
        os.environ["CODEX_MANAGED_PACKAGE_ROOT"] = str(native)
        os.environ["PATH"] = str(native / "vendor" / "x86_64-pc-windows-msvc" / "codex-path") + os.pathsep + os.environ.get("PATH", "")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) == 3 and sys.argv[1] == "--runtime-self-test":
        from codex_auto_resume.bundle_tests import run
        raise SystemExit(run(Path(sys.argv[2])))
    if not allow_background_watch(sys.argv[1:]):
        raise SystemExit(0)
    from codex_auto_resume.cli import main
    raise SystemExit(main())
