from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from prepare_macos import ROOT, prepare
from collect_licenses import collect_python
from prepare_macos_auto_resume import prepare as prepare_resume


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), required=True)
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != args.architecture:
        parser.error("Build on a real macOS runner with the matching CPU architecture")
    resources = prepare(ROOT / "artifacts" / "macos" / "resources")
    prepare_resume(args.architecture)
    from PIL import Image

    with Image.open(ROOT / "workspace" / "assets" / "ai-first-app-icon.png") as image:
        image.save(resources / "ai-first.icns", format="ICNS")
    output = ROOT / "artifacts" / "macos" / args.architecture
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output / "dist"),
                    "--workpath", str(output / "build"), str(ROOT / "macos" / "AI-First-Tools.spec")], check=True, cwd=ROOT)
    app = output / "dist" / "AI一手工具工作台.app"
    notices = app / "Contents" / "Resources" / "THIRD-PARTY-LICENSES"
    notices.mkdir(parents=True, exist_ok=True)
    collect_python(output / "build" / "AI-First-Tools" / "Analysis-00.toc", notices)
    metadata = output / "cargo-metadata.json"
    with metadata.open("w", encoding="utf-8") as handle:
        subprocess.run(["cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path", str(ROOT / "txcript" / "Cargo.toml")], check=True, stdout=handle)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "collect_rust_licenses.py"), "--metadata", str(metadata),
                    "--package", str(app / "Contents" / "Resources")], check=True)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    launcher = app / "Contents" / "MacOS" / "AI First Tools"
    for flag in ("--self-test", "--smoke-test", "--network-test", "--update-test", '--resume-test'):
        environment = os.environ.copy()
        if flag == "--network-test":
            environment["SSL_CERT_FILE"] = str(output / "no-host-python-ca.pem")
            environment["SSL_CERT_DIR"] = str(output / "no-host-python-ca")
        subprocess.run([str(launcher), flag, "--report", str(output / (flag.removeprefix("--") + ".json"))],
                       check=True, timeout=360 if flag in ("--update-test",'--resume-test') else 120, env=environment)
    version = json.loads((ROOT / "macos" / "version.json").read_text(encoding="utf-8"))["release"]
    staging = output / "dmg-content"
    staging.mkdir(exist_ok=True)
    shutil.copytree(app, staging / app.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    shutil.copy2(ROOT / "docs" / "MACOS.md", staging / "先看这里.txt")
    dmg = output / f"AI-First-Tools-{version}-macos-{args.architecture}.dmg"
    subprocess.run(["hdiutil", "create", "-volname", "AI一手工具工作台", "-srcfolder", str(staging), "-format", "UDZO", str(dmg)], check=True)
    subprocess.run(["hdiutil", "verify", str(dmg)], check=True)
    with dmg.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    (output / f"SHA256SUMS-{args.architecture}.txt").write_text(f"{digest}  {dmg.name}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
