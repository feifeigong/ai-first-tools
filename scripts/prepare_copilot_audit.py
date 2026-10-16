"""Checksum-pinned official runtime used by synthetic history tests, never shipped."""
from __future__ import annotations

import base64
import hashlib
import os
import platform
import sys
import tarfile
from pathlib import Path
from urllib.request import urlopen

PACKAGES = {
    ("win32", "AMD64"): ("win32-x64", "XlSIx7egXW4q3tbsPPl37WC0IxxRpjdwDIBLgTtzPR3qynBZML/H11WNandTVw5fVAUxnQ/RZE32r3At9emXQA=="),
    ("darwin", "arm64"): ("darwin-arm64", "2V3TL1nKk43TvxIa8T28df9+6VYT2zR/aSQLyd8WOVhUsF2hhpNzDeXGMOYEuyn2UrkbIJJ1V2TRrhQm+6HW1g=="),
    ("darwin", "x86_64"): ("darwin-x64", "pQYqPtMcX75MO87Wd4Grqn0W5EzEJ88EPOulTszRa/3eYH41Dr5UEPaYW96ng53pnKvn1VwnJSm+X18YQfAYYw=="),
}


def main():
    target, digest = PACKAGES[(sys.platform, platform.machine())]
    root = Path(__file__).resolve().parent.parent / "artifacts/copilot-audit"
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "runtime.tgz"
    with urlopen(f"https://registry.npmjs.org/@github/copilot-{target}/-/copilot-{target}-1.0.98.tgz", timeout=60) as response, archive.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    with archive.open("rb") as source:
        if base64.b64encode(hashlib.file_digest(source, "sha512").digest()).decode() != digest:
            raise ValueError("Official Copilot audit runtime integrity mismatch")
    with tarfile.open(archive) as source:
        source.extractall(root, filter="data")
    binary = root / "package" / ("copilot.exe" if sys.platform == "win32" else "copilot")
    if not binary.is_file():
        raise ValueError("Official Copilot runtime missing")
    binary.chmod(0o755)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
        output.write(f"DIALOG_MOVER_NATIVE_COPILOT={binary}\n")


if __name__ == "__main__":
    main()
