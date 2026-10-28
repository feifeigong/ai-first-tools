from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

REPOSITORY = "feifeigong/ai-first-tools"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.commit):
        parser.error("Expected a full source commit")
    root = Path(__file__).resolve().parent.parent
    version = ET.parse(root / "workspace/AIFirst.Workspace.csproj").findtext("PropertyGroup/Version")
    report = json.loads((root / "artifacts/windows/installer-test.json").read_text(encoding="utf-8-sig"))
    checks = json.loads((root / "artifacts/windows/installed-self-test.json").read_text(encoding="utf-8-sig"))
    if report.get("passed") is not True or report.get("version") != version or not report.get("checks") or not all(value is True for value in report["checks"].values()) or checks.get("failed") != 0 or checks.get("passed", 0) < 62:
        raise ValueError("Installer audit did not pass")
    if tuple(map(int,version.split('.'))) >= (0,3,19):
        ui=json.loads((root/'artifacts/windows/release-highlights-ui/report.json').read_text(encoding='utf-8-sig'))
        required={mode+name for mode in ('done','close','escape') for name in ('Layout','Focus','Acknowledged')}
        if ui.get('passed') is not True or not required <= ui.get('checks',{}).keys() or not all(ui['checks'][name] is True for name in required):
            raise ValueError('Native release highlights did not pass')
    if tuple(map(int,version.split('.'))) >= (0,3,21):
        resume=json.loads((root/'artifacts/windows/resume-runtime-test.json').read_text(encoding='utf-8-sig'))
        if resume.get('failed') != 0 or not any(check.get('name') == 'Frozen credit policy never spends before full weekly exhaustion'
                and check.get('passed') is True for check in resume.get('results', [])):
            raise ValueError('Packaged weekly credit boundary did not pass')
    release = root / "artifacts/release"
    assets = [release / f"AI-First-Tools-Setup-{version}.exe", release / f"AI-First-Tools-Portable-{version}-win-x64.zip"]
    sums = release / "SHA256SUMS.txt"
    expected = []
    for asset in assets:
        with asset.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        expected.append(f"{digest}  {asset.name}")
    if sums.read_text(encoding="utf-8-sig").splitlines() != expected:
        raise ValueError("Windows package digests differ")
    releases = json.loads(subprocess.run(["gh", "api", f"repos/{REPOSITORY}/releases?per_page=100"], check=True, capture_output=True).stdout)
    tag = f"v{version}"
    draft = next((item for item in releases if item.get("tag_name") == tag), None)
    if draft is None or draft.get("draft") is not True:
        print("No matching draft; published packages left unchanged")
        return
    reference = json.loads(subprocess.run(["gh", "api", f"repos/{REPOSITORY}/git/ref/tags/{tag}"], check=True, capture_output=True).stdout)
    if reference.get("object", {}).get("type") != "commit" or reference["object"]["sha"] != arguments.commit:
        raise ValueError("Prepare a lightweight release tag at the verified build commit")
    subprocess.run(["gh", "release", "upload", tag, "--repo", REPOSITORY, "--clobber", *map(str, [*assets, sums])], check=True)
    print("Verified Windows packages staged; release remains a draft")


if __name__ == "__main__":
    main()
