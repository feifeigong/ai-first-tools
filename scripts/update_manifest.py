from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def generate(package: Path, version: str) -> None:
    files = []
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name != "update-manifest.json":
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files.append({"path": path.relative_to(package).as_posix(), "size": path.stat().st_size, "sha256": digest})
    (package / "update-manifest.json").write_text(json.dumps({"version": version, "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--version", required=True)
    arguments = parser.parse_args()
    generate(arguments.package.resolve(), arguments.version)
