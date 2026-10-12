from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def check(package: Path):
    errors = []
    for item in package.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(package)
        if item.suffix.casefold() in {".db", ".sqlite", ".sqlite3", ".jsonl", ".log", ".pyc", ".pyo"}:
            errors.append(f"Unexpected data/cache: {relative}")
        if item.name.casefold() in {"auth.json", "cookies.json", "tools.json", "state.json", "health-report.json"}:
            errors.append(f"Private configuration: {relative}")
        if any(part in {"sessions", "qa-runs", "__pycache__"} for part in relative.parts):
            errors.append(f"Private directory: {relative}")
    runtime = json.loads((package / "AI一手工具工作台.runtimeconfig.json").read_text(encoding="utf-8"))["runtimeOptions"]
    if "frameworks" in runtime or "framework" in runtime or not runtime.get("includedFrameworks"):
        errors.append("Workspace must include the .NET runtime")
    engine = package / "tools" / "dialog-mover-v0.3" / "_internal" / "bin"
    for name in ("txcript.exe", "MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
        if not (engine / name).is_file():
            errors.append(f"Missing engine dependency: {name}")
    ui = engine.parent / "ui"
    outer_logo = package / "assets" / "dialog-mover.png"
    inner_logo = ui / "assets" / "dialog-mover.png"
    for logo in (outer_logo, inner_logo):
        if not logo.is_file():
            errors.append(f"Missing tool logo: {logo.relative_to(package)}")
    if outer_logo.is_file() and inner_logo.is_file() and outer_logo.read_bytes() != inner_logo.read_bytes():
        errors.append("Workspace and embedded tool logos must be identical")
    if not (ui / "index.html").is_file() or 'src="assets/dialog-mover.png"' not in (ui / "index.html").read_text(encoding="utf-8"):
        errors.append("Embedded tool must display the shared tool logo")
    for name in ("LICENSE", "NOTICE", "THIRD-PARTY-LICENSES/Python-LICENSE.txt", "THIRD-PARTY-LICENSES/rust-components.json", "THIRD-PARTY-LICENSES/Microsoft-WebView2-SDK-LICENSE.txt", "THIRD-PARTY-LICENSES/Microsoft-VC-Redist.txt", "docs/SUPPORT.md"):
        if not (package / name).is_file():
            errors.append(f"Missing document: {name}")
    if errors:
        raise RuntimeError("\n".join(errors))
    print("Self-contained runtime, engine dependencies, shared tool logo, notices and private-data exclusions: OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    check(parser.parse_args().package.resolve())
