"""Fast native source probe; never substitutes for the frozen release gate."""
import os
from pathlib import Path
import sys

assert os.environ.get('GITHUB_ACTIONS')=='true' and sys.platform=='darwin'
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'macos'),str(root/'dialog-mover'),str(root/'dialog-mover/vendor'),str(root/'auto-resume/src')]
from prepare_macos import prepare
prepare(root/'artifacts/macos/resources')
from copilot_refresh_audit import audit
raise SystemExit(audit(root/'artifacts/source-refresh-guard.json',frozen_required=False))
