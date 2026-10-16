"""Independently download staged Windows assets and compare the original CI files."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

REPOSITORY = "feifeigong/ai-first-tools"


def api(path: str):
    return json.loads(subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{path}"], check=True, capture_output=True).stdout)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validated_assets(root: Path, version: str) -> list[Path]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid Windows version")
    installation = json.loads((root / "windows/installer-test.json").read_text(encoding="utf-8-sig"))
    workspace = json.loads((root / "windows/installed-self-test.json").read_text(encoding="utf-8-sig"))
    required = {"silentInstall", "silentReinstall", "installedSelfChecks", "installedVersion", "extraFilePreserved", "safeUninstall"}
    if tuple(map(int, version.split('.'))) >= (0,3,12):
        required |= {"bundledRuntime", "bundledControls", "backgroundUpgrade", "backgroundUninstall"}
    checks = installation.get("checks") or {}
    if installation.get("passed") is not True or installation.get("version") != version \
            or not required <= set(checks) or any(checks[name] is not True for name in required) \
            or workspace.get("failed") != 0 or workspace.get("passed", 0) < 62:
        raise ValueError("Windows installation and workspace reports did not pass")
    if tuple(map(int, version.split('.'))) >= (0,3,12):
        try:
            runtime = json.loads((root / "windows/resume-runtime-test.json").read_text(encoding="utf-8-sig"))
            background = json.loads((root / "windows/resume-control-test.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise ValueError('Bundled auto-resume reports did not pass') from error
        if runtime.get('failed') != 0 or runtime.get('passed',0) < 4 or background.get('passed') is not True or len(background.get('checks',{})) < 5 or not all(value is True for value in background['checks'].values()):
            raise ValueError('Bundled auto-resume reports did not pass')
    assets = [root / "release" / f"AI-First-Tools-Setup-{version}.exe",
              root / "release" / f"AI-First-Tools-Portable-{version}-win-x64.zip"]
    sums = root / "release/SHA256SUMS.txt"
    expected = [f"{digest(path)}  {path.name}" for path in assets]
    if sums.read_text(encoding="utf-8-sig").splitlines() != expected:
        raise ValueError("Windows package checksum mismatch")
    return [*assets, sums]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise ValueError("Invalid build source")
    project = Path(__file__).resolve().parents[1] / "workspace/AIFirst.Workspace.csproj"
    version = ET.parse(project).findtext("PropertyGroup/Version")
    expected = validated_assets(args.artifacts, version)
    tag = f"v{version}"
    reference = api(f"git/ref/tags/{tag}")["object"]
    if reference.get("type") != "commit" or reference.get("sha") != args.commit:
        raise ValueError("Windows release tag does not match the verified build")
    matching = [item for item in api("releases?per_page=100") if item.get("tag_name") == tag]
    if len(matching) != 1 or matching[0].get("draft") is not True:
        raise ValueError("Expected one matching Windows draft; public assets left unchanged")
    release = matching[0]
    assets = {item["name"]: item for item in release["assets"]}
    if len(assets) != len(release["assets"]) or set(assets) != {path.name for path in expected}:
        raise ValueError("Staged Windows asset names differ")
    downloaded = args.artifacts / "independent-windows-download"
    downloaded.mkdir()
    subprocess.run(["gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", str(downloaded)], check=True, timeout=300)
    checks = []
    for path in expected:
        remote = assets[path.name]
        fingerprint = digest(path)
        copy = downloaded / path.name
        if remote.get("state") != "uploaded" or remote.get("digest") != f"sha256:{fingerprint}" \
                or remote.get("size") != path.stat().st_size or copy.stat().st_size != path.stat().st_size \
                or digest(copy) != fingerprint:
            raise ValueError(f"Uploaded Windows file differs from the verified CI build: {path.name}")
        checks.append({"name": path.name, "bytes": path.stat().st_size, "sha256": fingerprint})
    report = {"passed": True, "version": version, "source": args.commit, "releaseId": release["id"],
              "scope": "independent CI and draft downloads, installer and workspace reports, immutable source tag, exact names, bytes and SHA-256",
              "installerChecks": installation_checks(args.artifacts), "assets": checks}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


def installation_checks(root: Path) -> dict:
    return json.loads((root / "windows/installer-test.json").read_text(encoding="utf-8-sig"))["checks"]


if __name__ == "__main__":
    main()
