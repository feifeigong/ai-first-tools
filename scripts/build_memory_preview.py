"""Rebuild one local Windows preview from this checkout; never publish or install."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "artifacts" / "memory-preview-build"
ENGINE_SHA = "799b80dff7ba44cb05f1a92ed5f64a4969ffefc5ad7b3566600ed88adaaaacd2"
# This preview may fix Windows watcher lifecycle and honor a user stop immediately
# before reset-credit/resume submission. Quota thresholds, reset-credit policy and
# session discovery must remain at the verified release baseline.
RESUME_LIFECYCLE_FILES = {
    "auto-resume/run.py",
    "auto-resume/src/codex_auto_resume/procutil.py",
    "auto-resume/src/codex_auto_resume/watch_control.py",
    "auto-resume/src/codex_auto_resume/bundle_tests.py",
    "auto-resume/src/codex_auto_resume/daemon.py",
    "auto-resume/src/codex_auto_resume/redeem.py",
    "auto-resume/tests/test_procutil.py",
    "auto-resume/tests/test_watch_control.py",
    "auto-resume/tests/test_stop_safety.py",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inputs():
    values = {}
    names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "workspace", "dialog-mover", "auto-resume"], cwd=ROOT).decode("utf-8").split("\0")
    for name in names:
        if not name: continue
        path = ROOT / name
        if path.is_file(): values[name] = sha(path)
    return values


def verify_engine_scope():
    changed = set()
    for arguments in (
        ["diff", "--name-only", "-z", "HEAD", "--", "txcript", "auto-resume"],
        ["ls-files", "--others", "--exclude-standard", "-z", "--", "txcript", "auto-resume"],
    ):
        changed.update(name for name in subprocess.check_output(["git", *arguments], cwd=ROOT).decode("utf-8").split("\0") if name)
    if changed - RESUME_LIFECYCLE_FILES:
        raise RuntimeError("Edits outside the approved auto-resume lifecycle scope are present")


def run(name, args, cwd=ROOT, timeout=600):
    print(name, flush=True)
    log = WORK / (name + ".log")
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=environment, stdout=output, stderr=subprocess.STDOUT,
                                timeout=timeout, creationflags=0x08000000 if os.name == "nt" else 0)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace")[-4000:])
        raise RuntimeError(f"{name} failed; see {log}")


def main():
    global WORK
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--build-directory', type=Path)
    parser.add_argument("--replace-preview", action="store_true")
    arguments = parser.parse_args()
    if arguments.build_directory is not None:
        requested = arguments.build_directory.resolve()
        if not requested.is_relative_to(ROOT / 'artifacts') or requested.exists():
            raise RuntimeError('Use a fresh build directory within checkout artifacts')
        WORK = requested
    destination = arguments.output.resolve()
    if destination == ROOT or destination.is_relative_to(ROOT):
        raise RuntimeError("Choose a dedicated user-facing output folder outside the source checkout")
    if destination.exists() and any(destination.iterdir()):
        marker_path = destination / "development-preview.json"
        if not arguments.replace_preview or not marker_path.is_file() or json.loads(marker_path.read_text(encoding="utf-8")).get("kind") != "local-memory-preview":
            raise RuntimeError("The delivery folder must be empty or be this task's explicitly replaceable local preview")
        # A running Windows image cannot be opened for write. Do not replace an active preview.
        with (destination / "AI一手工具工作台.exe").open("r+b"):
            pass
    WORK.mkdir(parents=True, exist_ok=True)
    revisions = subprocess.check_output(["git", "rev-parse", "HEAD", "origin/master"], cwd=ROOT, text=True).splitlines()
    if len(revisions) != 2 or revisions[0] != revisions[1]:
        raise RuntimeError("The checkout baseline differs from the verified GitHub master")
    verify_engine_scope()
    if sha(ROOT / "dialog-mover/bin/txcript.exe") != ENGINE_SHA:
        raise RuntimeError("The local migration engine is not the pinned verified project engine")
    source_hashes = inputs()
    python = Path(sys.executable)
    mover_root = ROOT / "dialog-mover"
    run("build-memory-service", [python, "-m", "PyInstaller", "--noconfirm", "--distpath", WORK / "service", "--workpath", WORK / "service-cache", "记忆服务.spec"], mover_root)
    shutil.copy2(WORK / "service/AI一手记忆服务.exe", mover_root / "bin/AI一手记忆服务.exe")
    run("build-mover", [python, "-m", "PyInstaller", "--noconfirm", "--distpath", WORK / "mover", "--workpath", WORK / "mover-cache", "对话搬家.spec"], mover_root)
    run("build-resume", [python, "-m", "PyInstaller", "--noconfirm", "--distpath", WORK / "resume", "--workpath", WORK / "resume-cache", "AI一手续跑后台.spec"], ROOT / "auto-resume")
    package = WORK / "package"
    if package.exists():
        if package.resolve().parent != WORK.resolve(): raise RuntimeError("Unexpected intermediate package path")
        package.rename(WORK / ("previous-package-" + uuid.uuid4().hex))
    run("build-workspace", ["dotnet", "publish", ROOT / "workspace/AIFirst.Workspace.csproj", "-c", "Release", "-r", "win-x64", "--self-contained", "true", "-p:PublishSingleFile=false", "-o", package])
    shutil.copytree(WORK / "mover/对话搬家", package / "tools/dialog-mover-v0.3")
    shutil.copytree(WORK / "resume/AI一手续跑后台", package / "tools/auto-resume")
    runtime = package / "tools/dialog-mover-v0.3/_internal"
    for name in ("MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
        shutil.copy2(runtime / name, runtime / "bin" / name)
    for name in ("LICENSE", "NOTICE", "README.md"):
        shutil.copy2(ROOT / name, package / name)
    shutil.copytree(ROOT / "docs", package / "docs")
    run("collect-licenses", [python, ROOT / "scripts/collect_licenses.py", "--toc", WORK / "mover-cache/对话搬家/Analysis-00.toc", "--package", package, "--nsis", ROOT / "artifacts/build-tools/nsis/nsis-3.12"])
    run("collect-engine-licenses", [python, ROOT / "scripts/collect_rust_licenses.py", "--metadata", ROOT / "artifacts/cargo-metadata.json", "--package", package])
    notices = package / "THIRD-PARTY-LICENSES"
    for name, output in (("LICENSE", "Codex-LICENSE.txt"), ("NOTICE", "Codex-NOTICE.txt")):
        shutil.copy2(ROOT / "auto-resume/bin" / name, notices / output)
    shutil.copy2(ROOT / "auto-resume/codex-runtime.lock.json", notices / "Codex-runtime.json")
    for name in ("Microsoft-WebView2-SDK-LICENSE.txt", "Microsoft-WebView2-SDK-NOTICE.txt", "Microsoft-VC-Redist.txt"):
        shutil.copy2(ROOT / "licenses" / name, notices / name)
    marker = {"kind": "local-memory-preview", "baseline": revisions[0], "published": False, "source_sha256": source_hashes,
              "engine_sha256": ENGINE_SHA, "memory_service_sha256": sha(runtime / "bin/AI一手记忆服务.exe")}
    (package / "development-preview.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    run("frozen-memory-check", [package / "tools/dialog-mover-v0.3/对话搬家.exe", "--memory-self-test", WORK / "frozen-memory-check.json"], timeout=60)
    memory_report = json.loads((WORK / "frozen-memory-check.json").read_text(encoding="utf-8"))
    if memory_report.get("passed") is not True:
        raise RuntimeError("The frozen memory service check did not pass")
    compatibility_report_path = WORK / 'codex-import-checks.json'
    run('frozen-history-check', [package / 'tools/dialog-mover-v0.3/对话搬家.exe',
        '--codex-import-self-test', compatibility_report_path], timeout=120)
    compatibility = json.loads(compatibility_report_path.read_text(encoding='utf-8'))
    if (compatibility.get('passed') is not True or len(compatibility.get('checks', {})) < 7
            or any(value is not True for value in compatibility['checks'].values())
            or compatibility.get('modelRequests') != 0):
        raise RuntimeError('The frozen history compatibility check did not pass')
    resume_report_path = WORK / "frozen-resume-check.json"
    resume_report_path.unlink(missing_ok=True)
    run("frozen-resume-check", [package / "tools/auto-resume/AI一手续跑后台.exe", "--runtime-self-test", resume_report_path], timeout=180)
    resume_report = json.loads(resume_report_path.read_text(encoding="utf-8-sig"))
    resume_results = resume_report.get("results") or []
    if resume_report.get("failed") != 0 or len(resume_results) < 4 or resume_report.get("passed") != len(resume_results) or any(test.get("passed") is not True for test in resume_results):
        raise RuntimeError("The frozen auto-resume runtime checks did not pass")
    native_report_path = WORK / "native-resume-control-check.json"
    native_report_path.unlink(missing_ok=True)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    run("native-resume-control-check", [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
        ROOT / "workspace/tests/AutoResumeBundled.Native.Tests.ps1", "-Package", package, "-Report", native_report_path], timeout=180)
    native_report = json.loads(native_report_path.read_text(encoding="utf-8-sig"))
    native_checks = native_report.get("checks") or {}
    if native_report.get("passed") is not True or len(native_checks) < 5 or any(value is not True for value in native_checks.values()):
        raise RuntimeError("The native auto-resume control checks did not pass")
    run("workspace-self-check", [package / "AI一手工具工作台.exe", "--self-test", "--report", WORK / "workspace-checks.json"], timeout=180)
    workspace_report = json.loads((WORK / "workspace-checks.json").read_text(encoding="utf-8"))
    if workspace_report.get("failed") != 0 or not workspace_report.get("tests") or any(test.get("passed") is not True for test in workspace_report["tests"]):
        raise RuntimeError("The native workspace checks did not pass")
    catalog = json.loads((package / "assets/tool-catalog.json").read_text(encoding="utf-8"))
    if {tool["id"] for tool in catalog} != {"dialog-mover", "auto-resume"}:
        raise RuntimeError("Unexpected experimental tools in this preview")
    if inputs() != source_hashes:
        raise RuntimeError("Source files changed during compilation; the delivery was not copied")
    run("update-file-manifest", [python, ROOT / "scripts/update_manifest.py", "--package", package, "--version", "0.3.16"])
    run("package-content-check", [python, ROOT / "scripts/check_release.py", "--package", package])
    shutil.copytree(package, destination, dirs_exist_ok=True)
    print(json.dumps({"output": str(destination), "baseline": revisions[0], "memory_checks": memory_report,
        "resume_runtime_passed": True, "resume_controls_passed": True, "workspace_passed": True}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
