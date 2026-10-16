from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

REPOSITORY = "feifeigong/ai-first-tools"


def validated_assets(directory: Path, release: str) -> list[Path]:
    if not re.fullmatch(r"\d+\.\d+\.\d+-macos-preview\.\d+", release):
        raise ValueError("Invalid Mac preview version")
    assets = []
    sums = []
    for architecture in ("arm64", "x86_64"):
        source = directory / f"macos-{architecture}"
        name = f"AI-First-Tools-{release}-macos-{architecture}.dmg"
        dmg = source / name
        with dmg.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        expected = f"{digest}  {name}"
        if (source / f"SHA256SUMS-{architecture}.txt").read_text().strip() != expected:
            raise ValueError("DMG digest mismatch")
        kinds = ("self", "smoke", "network", "update", 'resume') if int(release.rsplit('.',1)[1]) >= 15 else ("self", "smoke", "network", "update")
        for kind in kinds:
            report = source / f"{kind}-test.json"
            result = json.loads(report.read_text())
            if result.get("passed") is not True or not result.get("checks") or not all(value is True for value in result["checks"].values()):
                raise ValueError("Native app checks did not pass")
            if kind == "update" and not {"nativeUpdateClick", "bridgeDrained", "nativeParentExit"}.issubset(result["checks"]):
                raise ValueError("Native update click and bridge handoff checks are required")
            if kind == 'resume' and not {'nativeRuntimeWithoutExternalInstallation','singlePackagedWatcher','startupSwitchIndependent','stopBlocksStartupRelaunch','updateRestoresRunningAndStartup','realLaunchAgentStopsWithoutRelaunch','finderRemovalCleansBackgroundAndStartup','cleanupPreservesUserSettings'} <= set(result['checks']):
                raise ValueError('Actual bundled auto-resume lifecycle checks are required')
            if kind=='smoke' and int(release.rsplit('.',1)[1])>=15 and result['checks'].get('autoResumeControlBridge') is not True:
                raise ValueError('Native auto-resume page and bridge check is required')
            if kind != "smoke" and (result.get("architecture") != architecture or result.get("version", {}).get("release") != release):
                raise ValueError("Native report version or architecture mismatch")
            target = directory / f"{kind}-test-{architecture}.json"
            shutil.copy2(report, target)
            assets.append(target)
        target = directory / name
        shutil.copy2(dmg, target)
        assets.append(target)
        sums.append(expected)
    manifest = directory / "SHA256SUMS.txt"
    manifest.write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    return [*assets, manifest]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.commit):
        parser.error("Expected a full build commit")
    root = Path(__file__).resolve().parent.parent
    release = json.loads((root / "macos/version.json").read_text())["release"]
    tag = f"v{release}"
    command = ["gh", "api", f"repos/{REPOSITORY}/releases?per_page=100"]
    response = subprocess.run(command, capture_output=True, text=True, check=True)
    releases = json.loads(response.stdout)
    if not isinstance(releases, list):
        raise ValueError("Invalid release list")
    draft = next((release for release in releases if release.get("tag_name") == tag), None)
    if draft is None or draft.get("draft") is not True:
        print("No matching draft; published releases left unchanged")
        return
    reference = json.loads(subprocess.run(["gh", "api", f"repos/{REPOSITORY}/git/ref/tags/{tag}"], check=True, capture_output=True, text=True).stdout)
    if reference.get("object", {}).get("type") != "commit" or reference["object"]["sha"] != arguments.commit:
        raise ValueError("Prepare a lightweight release tag at the verified build commit")
    assets = validated_assets(arguments.artifacts, release)
    subprocess.run(["gh", "release", "upload", tag, "--repo", REPOSITORY, "--clobber", *map(str, assets)], check=True)
    print("Validated assets staged; release remains a draft")


if __name__ == "__main__":
    main()
