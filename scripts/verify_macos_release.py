from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from stage_macos_release import REPOSITORY, validated_assets


def api(path: str):
    return json.loads(subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{path}"],
                                     check=True, capture_output=True, text=True).stdout)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    release = json.loads((Path(__file__).resolve().parent.parent / "macos/version.json").read_text())["release"]
    tag = f"v{release}"
    reference = api(f"git/ref/tags/{tag}")["object"]
    if reference.get("type") != "commit" or reference.get("sha") != args.commit:
        raise ValueError("Release tag does not match the verified native build")
    expected = validated_assets(args.artifacts, release)
    # GitHub's public tag lookup can return 404 for an unpublished draft.
    matching = [item for item in api("releases?per_page=100") if item.get("tag_name") == tag]
    if len(matching) != 1:
        raise ValueError("Expected exactly one release draft for the verified tag")
    metadata = matching[0]
    assets = {asset["name"]: asset for asset in metadata["assets"]}
    if metadata.get("draft") is not True or len(assets) != len(metadata["assets"]) or set(assets) != {path.name for path in expected}:
        raise ValueError("Expected the complete matching draft, leaving published releases unchanged")
    downloaded = args.artifacts / "independent-release-download"
    downloaded.mkdir()
    subprocess.run(["gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", str(downloaded)],
                   check=True, timeout=180)
    checks = []
    for path in expected:
        remote = assets[path.name]
        fingerprint = digest(path)
        copy = downloaded / path.name
        if remote.get("state") != "uploaded" or remote.get("digest") != f"sha256:{fingerprint}" \
                or remote.get("size") != path.stat().st_size or copy.stat().st_size != path.stat().st_size \
                or digest(copy) != fingerprint:
            raise ValueError(f"Uploaded asset differs from the verified native build: {path.name}")
        checks.append({"name": path.name, "bytes": path.stat().st_size, "sha256": fingerprint})
    report = {"passed": True, "release": release, "source": args.commit, "releaseId": metadata["id"],
              "scope": "separately downloaded original CI artifacts and draft assets; native reports, exact names, bytes and SHA-256",
              "assets": checks}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
