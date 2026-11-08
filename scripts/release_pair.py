"""Publish one explicitly requested, independently verified Windows/Mac pair."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "feifeigong/ai-first-tools"
REQUEST_PATH = ".github/release-pair.json"
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")


def command(args: list[str], **kwargs) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def api(path: str, *, method: str = "GET", payload: dict | None = None, optional: bool = False):
    args = ["gh", "api", f"repos/{REPOSITORY}/{path}", "--method", method]
    if payload is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True)
    if result.returncode:
        if optional and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(f"GitHub {method} {path} failed; no publication success assumed")
    return json.loads(result.stdout)


def read_request(root: Path = ROOT) -> dict:
    request = json.loads((root / REQUEST_PATH).read_text(encoding="utf-8"))
    fields = {"schema", "attempt", "publish", "windows_version", "macos_release", "notes"}
    if (not isinstance(request, dict) or set(request) != fields or request["schema"] != 1
            or request["publish"] is not True or type(request["attempt"]) is not int
            or request["attempt"] < 1):
        raise ValueError("An explicit enabled release request and positive attempt are required")
    windows = ET.parse(root / "workspace/AIFirst.Workspace.csproj").findtext("PropertyGroup/Version")
    mac = json.loads((root / "macos/version.json").read_text(encoding="utf-8"))
    if (not isinstance(windows, str) or not re.fullmatch(r"\d+\.\d+\.\d+", windows)
            or request["windows_version"] != windows or mac.get("version") != windows
            or request["macos_release"] != mac.get("release")
            or not re.fullmatch(re.escape(windows) + r"-macos-preview\.\d+", str(mac.get("release")))):
        raise ValueError("Requested Windows and Mac versions must match the checked-out source")
    notes = request["notes"]
    if (not isinstance(notes, str) or not re.fullmatch(r"docs/releases/[A-Za-z0-9._-]+\.md", notes)
            or not (root / notes).read_text(encoding="utf-8").strip()):
        raise ValueError("Release notes must be a nonempty reviewed repository file")
    return request


def validate_context(commit: str) -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if (not SHA.fullmatch(commit) or not re.fullmatch(r"[0-9]+", run_id)
            or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_REF") != "refs/heads/master"
            or os.environ.get("GITHUB_SHA") != commit
            or command(["git", "rev-parse", "HEAD"], cwd=ROOT).strip() != commit):
        raise ValueError("Release must use this master run's exact checked-out source commit")
    if api("git/ref/heads/master").get("object", {}).get("sha") != commit:
        raise ValueError("Master advanced; this release request is no longer the source head")
    return run_id


def tags(request: dict) -> dict[str, str]:
    return {"windows": "v" + request["windows_version"], "macos": "v" + request["macos_release"]}


def expected_names(request: dict, platform: str) -> set[str]:
    if platform == "windows":
        version = request["windows_version"]
        return {f"AI-First-Tools-Setup-{version}.exe",
                f"AI-First-Tools-Portable-{version}-win-x64.zip", "SHA256SUMS.txt"}
    release = request["macos_release"]
    kinds = ("self", "smoke", "network", "update", "resume", "memory", "reset", "reset-rules",
             "codex-import", "copilot-refresh")
    return {"SHA256SUMS.txt", *(f"AI-First-Tools-{release}-macos-{arch}.dmg" for arch in ("arm64", "x86_64")),
            *(f"{kind}-test-{arch}.json" for arch in ("arm64", "x86_64") for kind in kinds)}


def targets(request: dict, commit: str) -> dict:
    releases = api("releases?per_page=100")
    if not isinstance(releases, list):
        raise ValueError("Invalid release inventory")
    result = {}
    for platform, tag in tags(request).items():
        matches = [item for item in releases if item.get("tag_name") == tag]
        if len(matches) > 1 or (matches and matches[0].get("draft") is not True):
            raise ValueError(f"Refusing to replace an already public or ambiguous release: {tag}")
        reference = api(f"git/ref/tags/{tag}", optional=True)
        if reference is not None and (reference.get("object", {}).get("type") != "commit"
                or reference.get("object", {}).get("sha") != commit):
            raise ValueError(f"Existing tag must already be a lightweight tag at this source: {tag}")
        if matches and reference is None:
            raise ValueError(f"Existing draft is missing its immutable source tag: {tag}")
        result[platform] = {"tag": tag, "reference": reference, "release": matches[0] if matches else None}
    return result


def validate_local_artifacts(request: dict) -> None:
    from verify_windows_release import validated_assets as windows_assets
    from stage_macos_release import validated_assets as mac_assets
    windows_assets(ROOT / "artifacts", request["windows_version"])
    mac_assets(ROOT / "artifacts/release-stage", request["macos_release"])
    # These additional existing Windows staging checks must also pass before tags exist.
    installation = json.loads((ROOT / "artifacts/windows/installer-test.json").read_text(encoding="utf-8-sig"))
    if not installation.get("checks") or not all(value is True for value in installation["checks"].values()):
        raise ValueError("Every installer check must pass before creating release tags")
    ui = json.loads((ROOT / "artifacts/windows/release-highlights-ui/report.json").read_text(encoding="utf-8-sig"))
    required_ui = {mode + name for mode in ("done", "close", "escape")
                   for name in ("Layout", "Focus", "Acknowledged")}
    runtime = json.loads((ROOT / "artifacts/windows/resume-runtime-test.json").read_text(encoding="utf-8-sig"))
    required_runtime = {
        "Frozen credit policy never spends before full weekly exhaustion",
        "Frozen independent automation preserves timer deduplication and spending permissions",
        "Native Codex supports the isolated ephemeral request flags without model requests",
        "Frozen main-session identity and final submission safety",
    }
    passed = {item.get("name") for item in runtime.get("results", []) if item.get("passed") is True}
    if (ui.get("passed") is not True or any(ui.get("checks", {}).get(name) is not True for name in required_ui)
            or runtime.get("failed") != 0 or not required_runtime <= passed):
        raise ValueError("Windows native UI and packaged safety checks are incomplete")


def prepare(request: dict, commit: str, run_id: str, output: Path) -> None:
    validate_local_artifacts(request)
    selected = targets(request, commit)  # Validate both before creating either tag/draft.
    body = (ROOT / request["notes"]).read_text(encoding="utf-8").rstrip()
    body += f"\n\n源码：`{commit}`\n\n构建：[同次双平台验证](https://github.com/{REPOSITORY}/actions/runs/{run_id})\n"
    for platform, target in selected.items():
        tag = target["tag"]
        if target["reference"] is None:
            api("git/refs", method="POST", payload={"ref": f"refs/tags/{tag}", "sha": commit})
        metadata = {"tag_name": tag, "target_commitish": commit, "name": f"AI一手工具箱 {tag[1:]}",
                    "body": body, "draft": True, "prerelease": platform == "macos"}
        if target["release"] is None:
            api("releases", method="POST", payload=metadata)
        else:
            api(f"releases/{target['release']['id']}", method="PATCH", payload=metadata)
    output.parent.mkdir(parents=True, exist_ok=True)
    reports = {}
    for platform in ("windows", "macos"):
        arguments = ["--commit", commit]
        directory = ROOT / ("artifacts" if platform == "windows" else "artifacts/release-stage")
        if platform == "macos":
            arguments += ["--artifacts", str(directory)]
        command([sys.executable, str(ROOT / f"scripts/stage_{platform}_release.py"), *arguments], cwd=ROOT)
        report = output.parent / f"{platform}-verification.json"
        command([sys.executable, str(ROOT / f"scripts/verify_{platform}_release.py"), "--commit", commit,
                 "--artifacts", str(directory), "--report", str(report)], cwd=ROOT)
        reports[platform] = json.loads(report.read_text(encoding="utf-8"))
    receipt = {"schema": 1, "source": commit, "run_id": run_id, "request": request, **reports}
    validate_receipt(receipt, request, commit, run_id)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_receipt(receipt: dict, request: dict, commit: str, run_id: str) -> None:
    if (receipt.get("schema") != 1 or receipt.get("source") != commit or receipt.get("run_id") != run_id
            or receipt.get("request") != request):
        raise ValueError("Verification receipt must belong to this exact request, source and run")
    for platform, version_field, version in (("windows", "version", request["windows_version"]),
                                             ("macos", "release", request["macos_release"])):
        report = receipt.get(platform, {})
        assets = report.get("assets", [])
        if (report.get("passed") is not True or report.get("source") != commit
                or report.get(version_field) != version or type(report.get("releaseId")) is not int
                or {item["name"] for item in assets} != expected_names(request, platform)
                or len({item["name"] for item in assets}) != len(assets)
                or any(not isinstance(item.get("sha256"), str) or not DIGEST.fullmatch(item["sha256"])
                       or type(item.get("bytes")) is not int or item["bytes"] < 0
                       or Path(item["name"]).name != item["name"] for item in assets)):
            raise ValueError(f"Incomplete independent verification: {platform}")


def verified_remote(platform: str, tag: str, report: dict, commit: str) -> dict:
    reference = api(f"git/ref/tags/{tag}").get("object", {})
    release = api(f"releases/{report['releaseId']}")
    assets = release.get("assets", [])
    expected = {item["name"]: item for item in report["assets"]}
    if (reference.get("type") != "commit" or reference.get("sha") != commit
            or release.get("id") != report["releaseId"] or release.get("tag_name") != tag
            or type(release.get("draft")) is not bool or release.get("prerelease") is not (platform == "macos")
            or len(assets) != len(expected) or {item["name"] for item in assets} != set(expected)):
        raise ValueError(f"Verified release identity or asset set changed: {platform}")
    for asset in assets:
        item = expected[asset["name"]]
        if (asset.get("state") != "uploaded" or asset.get("size") != item["bytes"]
                or asset.get("digest") != "sha256:" + item["sha256"]):
            raise ValueError(f"Verified release bytes changed: {asset['name']}")
    return release


def publish(receipt: dict, request: dict, commit: str, run_id: str, output: Path) -> None:
    validate_receipt(receipt, request, commit, run_id)
    releases = {platform: verified_remote(platform, tag, receipt[platform], commit)
                for platform, tag in tags(request).items()}
    result = {"source": commit, "run_id": run_id, "published": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        # GitHub has no atomic two-release transaction. A retry may skip only
        # the identical release ID, immutable source and verified bytes above.
        for platform in ("macos", "windows"):
            current = releases[platform]
            if current["draft"]:
                api(f"releases/{current['id']}", method="PATCH", payload={
                    "draft": False, "prerelease": platform == "macos",
                    "make_latest": "true" if platform == "windows" else "false"})
            remote = verified_remote(platform, tags(request)[platform], receipt[platform], commit)
            if remote["draft"]:
                raise ValueError(f"Publication was not confirmed: {platform}")
            result["published"][platform] = remote["html_url"]
    finally:
        result["passed"] = set(result["published"]) == {"windows", "macos"}
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def macos_gate() -> bool:
    if (os.environ.get("PAIRED_RELEASE") == "true" or os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_REF") != "refs/heads/master"):
        return True
    try:
        before = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["before"]
        if not SHA.fullmatch(before) or before == "0" * 40:
            return True
        changed = command(["git", "diff", "--name-only", before, "HEAD", "--", REQUEST_PATH], cwd=ROOT)
        read_request()
        return REQUEST_PATH not in changed.splitlines()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        return True  # An uncertain scope must retain the normal native build.


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("request", "prepare", "publish", "macos-gate"))
    parser.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.operation == "macos-gate":
        with args.output.open("a", encoding="utf-8") as output:
            output.write(f"build={'true' if macos_gate() else 'false'}\n")
        return
    request = read_request()
    run_id = validate_context(args.commit)
    if args.operation == "request":
        targets(request, args.commit)
        with args.output.open("a", encoding="utf-8") as output:
            output.write(f"source={args.commit}\n")
    elif args.operation == "prepare":
        prepare(request, args.commit, run_id, args.output)
    else:
        if args.receipt is None:
            parser.error("publish requires the verified receipt from this run")
        publish(json.loads(args.receipt.read_text(encoding="utf-8")), request, args.commit, run_id, args.output)


if __name__ == "__main__":
    main()
