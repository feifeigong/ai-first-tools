from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    arguments = parser.parse_args()
    destination = arguments.package / "THIRD-PARTY-LICENSES" / "rust-crates"
    destination.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(arguments.metadata.read_text(encoding="utf-8-sig"))
    notices = []
    for package in metadata["packages"]:
        if package.get("source") is None:
            continue
        directory = Path(package["manifest_path"]).parent
        output = destination / f"{package['name']}-{package['version']}"
        output.mkdir(parents=True, exist_ok=True)
        for source in directory.rglob("*"):
            if source.is_file() and (source.name.upper().startswith(("LICENSE", "COPYING", "NOTICE")) or source.name == package.get("license_file")):
                target = output / source.relative_to(directory)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        notices.append({"name": package["name"], "version": package["version"], "license": package.get("license"), "repository": package.get("repository")})
    (destination.parent / "rust-components.json").write_text(json.dumps(notices, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Rust dependency notices: {len(notices)}")


if __name__ == "__main__":
    main()
