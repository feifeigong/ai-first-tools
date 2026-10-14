from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tarfile
from pathlib import Path


PACKAGES = {
    "arm64": ("aarch64", "b293a0fcdd871900a44c0a4f40a1aa401b31e02854f790ebdb8bd5d1177fd1fe"),
    "x86_64": ("x86_64", "d68e39d8f62639f33f7d00656554cb9c3ef7809e664a3827e62ab3ace3c21b21"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--architecture", required=True, choices=PACKAGES)
    arguments = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The native history audit requires a Mac runner")
    architecture, expected = PACKAGES[arguments.architecture]
    root = Path(__file__).resolve().parent.parent / "artifacts/native-history-audit"
    root.mkdir(parents=True, exist_ok=True)
    name = f"codex-{architecture}-apple-darwin"
    package = root / f"{name}.tar.gz"
    url = f"https://github.com/openai/codex/releases/download/rust-v0.162.1/{package.name}"
    subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--max-time", "180", url, "--output", str(package)], check=True)
    with package.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != expected:
            raise ValueError("Official native history audit binary checksum mismatch")
    with tarfile.open(package) as archive:
        archive.extractall(root, filter="data")
    binary = root / name
    if not binary.is_file():
        raise ValueError("Official native history audit executable is missing")
    binary.chmod(0o755)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as handle:
        handle.write(f"DIALOG_MOVER_NATIVE_CODEX={binary}\n")


if __name__ == "__main__":
    main()
