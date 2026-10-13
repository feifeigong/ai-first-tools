from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import updates

APP_NAME = "AI一手工具工作台.app"
EXECUTABLE = "AI First Tools"
MAX_PACKAGE = 512 * 1024 * 1024


class UpdateError(Exception):
    pass


class Cancelled(UpdateError):
    pass


def state_root() -> Path:
    return Path.home() / "Library/Application Support/AI一手工具工作台/updates"


def running_bundle() -> Path:
    executable = Path(sys.executable).resolve()
    bundle = executable.parents[2]
    if not getattr(sys, "frozen", False) or executable != bundle / "Contents/MacOS" / EXECUTABLE or bundle.suffix != ".app":
        raise UpdateError("请使用完整的 Mac 应用，源码运行不能直接更新。")
    if "AppTranslocation" in bundle.parts or "Volumes" in bundle.parts:
        raise UpdateError("请先把软件拖到“应用程序”并从那里打开，之后就能一键更新。")
    return bundle


def package_from_release(release: dict) -> dict | None:
    version = release["version"]
    architecture = platform.machine()
    expected = f"AI-First-Tools-{version}-macos-{architecture}.dmg"
    assets = release.get("assets", [])
    if not isinstance(assets, list) or updates.release_key(version) is None or architecture not in ("arm64", "x86_64"):
        return None
    selected = {}
    for name, limit in ((expected, MAX_PACKAGE), ("SHA256SUMS.txt", 65536)):
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
        if len(matches) != 1:
            return None
        asset = matches[0]
        if asset.get("state") != "uploaded" or type(asset.get("size")) is not int or not 0 < asset["size"] <= limit:
            return None
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(asset.get("digest", ""))):
            return None
        url = f"{updates.REPOSITORY}/releases/download/v{version}/{name}"
        if asset.get("browser_download_url") != url:
            return None
        selected["dmg" if name == expected else "sums"] = {"name": name, "size": asset["size"], "digest": asset["digest"][7:], "url": url}
    return {"version": version, "architecture": architecture, **selected}


def safe_download_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme == "https" and parts.username is None and parts.password is None and parts.port in (None, 443) and (
            parts.hostname in ("release-assets.githubusercontent.com", "objects.githubusercontent.com")
            or parts.hostname == "github.com" and parts.path.startswith("/feifeigong/ai-first-tools/releases/download/"))
    except ValueError:
        return False


class DownloadRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if not safe_download_url(newurl):
            raise UpdateError("更新下载地址不符合安全要求，旧版未改动。")
        return super().redirect_request(request, response, code, message, headers, newurl)


def download(asset: dict, path: Path, progress, cancelled) -> None:
    if not safe_download_url(asset["url"]):
        raise UpdateError("更新下载地址不符合安全要求。")
    opener = build_opener(DownloadRedirect(), HTTPSHandler(context=updates.tls_context()))
    digest = hashlib.sha256()
    received = 0
    started = time.monotonic()
    try:
        with opener.open(Request(asset["url"], headers={"User-Agent": "AI-First-Tools-macOS"}), timeout=30) as response, path.open("xb") as output:
            if not safe_download_url(response.geturl()):
                raise UpdateError("更新下载地址不符合安全要求。")
            while True:
                if cancelled.is_set():
                    raise Cancelled("已取消下载，当前版本可以继续使用。")
                if time.monotonic() - started > 900:
                    raise UpdateError("下载超时，请稍后再试。当前版本未改动。")
                block = response.read(256 * 1024)
                if not block:
                    break
                received += len(block)
                if received > asset["size"]:
                    raise UpdateError("更新文件大小不符合要求。")
                output.write(block)
                digest.update(block)
                progress(received * 100 / asset["size"])
            output.flush()
            os.fsync(output.fileno())
        if received != asset["size"] or digest.hexdigest() != asset["digest"]:
            raise UpdateError("更新包未通过完整性校验，旧版未改动。请重新下载。")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def command(arguments, timeout=60) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    for name in ("DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH"):
        environment.pop(name, None)
    return subprocess.run(arguments, capture_output=True, check=True, timeout=timeout, env=environment)


def validate_app(bundle: Path, release: str, architecture: str) -> None:
    if bundle.is_symlink() or not bundle.is_dir() or bundle.suffix != ".app":
        raise UpdateError("更新包不是完整的应用。")
    root = bundle.resolve()
    total = count = 0
    for directory, folders, files in os.walk(bundle, followlinks=False):
        for name in [*folders, *files]:
            path = Path(directory) / name
            count += 1
            if not path.resolve().is_relative_to(root):
                raise UpdateError("更新包含有不安全的链接。")
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
            if count > 50000 or total > 2 * 1024 * 1024 * 1024:
                raise UpdateError("更新包超出允许大小。")
    info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
    metadata = json.loads((bundle / "Contents/Resources/version.json").read_text(encoding="utf-8"))
    if info.get("CFBundleIdentifier") != "cn.aifirst.tools" or info.get("CFBundleExecutable") != EXECUTABLE or metadata.get("release") != release:
        raise UpdateError("更新包的软件或版本不匹配。")
    command(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)])
    architectures = command(["/usr/bin/lipo", "-archs", str(bundle / "Contents/MacOS" / EXECUTABLE)]).stdout.decode().split()
    if architecture not in architectures:
        raise UpdateError("更新包与 Mac 芯片不匹配。")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def fingerprint(bundle: Path) -> str:
    digest = hashlib.sha256()
    for directory, folders, files in os.walk(bundle, followlinks=False):
        for name in sorted([*folders, *files]):
            path = Path(directory) / name
            digest.update(path.relative_to(bundle).as_posix().encode())
            if path.is_symlink():
                digest.update(os.readlink(path).encode())
            elif path.is_file():
                with path.open("rb") as handle:
                    digest.update(hashlib.file_digest(handle, "sha256").digest())
                digest.update(str(path.stat().st_mode).encode())
        folders.sort()
    return digest.hexdigest()


def stage_bundle(target: Path, candidate: Path, version: str, current: str, architecture: str, directory: Path) -> Path:
    validate_app(target, current, architecture)
    validate_app(candidate, version, architecture)
    if updates.release_key(version) is None or updates.release_key(current) is None or updates.release_key(version) <= updates.release_key(current):
        raise UpdateError("更新版本必须比当前版本新。")
    staged = directory / "candidate.app"
    if candidate != staged:
        command(["/usr/bin/ditto", str(candidate), str(staged)])
    helper = directory / "helper.app"
    command(["/usr/bin/ditto", str(target), str(helper)])
    validate_app(staged, version, architecture)
    validate_app(helper, current, architecture)
    snapshot = target.stat()
    job = directory / "job.json"
    write_json(job, {"target": str(target), "version": version, "current": current, "architecture": architecture,
                     "device": snapshot.st_dev, "inode": snapshot.st_ino, "originalDigest": fingerprint(target),
                     "candidateDigest": fingerprint(staged), "parentPid": os.getpid(), "nonce": uuid.uuid4().hex})
    return job


def prepare(target: Path, package: dict, current: str, progress, cancelled) -> Path:
    directory = Path(tempfile.mkdtemp(prefix=".ai-first-update-", dir=target.parent))
    directory.chmod(0o700)
    mount = directory / "mount"
    mounted = False
    try:
        progress("downloading", 0)
        sums = directory / "SHA256SUMS.txt"
        download(package["sums"], sums, lambda value: None, cancelled)
        pattern = rf"{package['dmg']['digest']}  {re.escape(package['dmg']['name'])}"
        lines = sums.read_text(encoding="utf-8").splitlines()
        matches = [line for line in lines if line.endswith("  " + package["dmg"]["name"])]
        if len(matches) != 1 or re.fullmatch(pattern, matches[0]) is None:
            raise UpdateError("发布校验文件与更新包不匹配。")
        dmg = directory / "update.dmg"
        download(package["dmg"], dmg, lambda value: progress("downloading", value), cancelled)
        progress("preparing", 100)
        mount.mkdir()
        command(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(dmg)])
        mounted = True
        if cancelled.is_set():
            raise Cancelled("已取消下载，当前版本可以继续使用。")
        job = stage_bundle(target, mount / APP_NAME, package["version"], current, package["architecture"], directory)
        command(["/usr/bin/hdiutil", "detach", str(mount)])
        mounted = False
        dmg.unlink()
        return job
    except Exception:
        if mounted:
            try:
                command(["/usr/bin/hdiutil", "detach", str(mount)])
                mounted = False
            except (OSError, subprocess.SubprocessError):
                pass
        if not mounted:
            shutil.rmtree(directory)
        raise


def read_job(path: Path) -> dict:
    directory = path.parent
    if path.name != "job.json" or path.is_symlink() or directory.is_symlink() or not directory.name.startswith(".ai-first-update-"):
        raise UpdateError("更新任务位置不符合要求。")
    data = json.loads(path.read_text(encoding="utf-8"))
    target = Path(data["target"])
    if not target.is_absolute() or target.is_symlink() or target.parent.resolve() != directory.parent.resolve() or target.suffix != ".app":
        raise UpdateError("更新目标位置不符合要求。")
    if type(data.get("parentPid")) is not int or data["parentPid"] <= 0 or not re.fullmatch(r"[0-9a-f]{32}", data.get("nonce", "")):
        raise UpdateError("更新任务不完整。")
    if data.get("architecture") not in ("arm64", "x86_64") or updates.release_key(data.get("version", "")) is None or updates.release_key(data.get("current", "")) is None or updates.release_key(data["version"]) <= updates.release_key(data["current"]):
        raise UpdateError("更新版本或芯片不符合要求。")
    if sys.platform == "darwin" and (directory.stat().st_uid != os.getuid() or path.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077):
        raise UpdateError("更新任务权限不符合要求。")
    return data


def discard(job: Path) -> None:
    read_job(job)
    if (job.parent / "mount").is_dir() and os.path.ismount(job.parent / "mount"):
        raise UpdateError("正在准备更新，请稍后再试。")
    shutil.rmtree(job.parent)


def start_helper(job: Path) -> subprocess.Popen:
    data = read_job(job)
    ready = job.parent / "ready.json"
    ready.unlink(missing_ok=True)
    environment = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    process = subprocess.Popen([str(job.parent / "helper.app/Contents/MacOS" / EXECUTABLE), "--apply-update", str(job)],
                               env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ready.is_file():
            result = json.loads(ready.read_text())
            if result.get("nonce") == data["nonce"] and result.get("pid") == process.pid:
                return process
        if process.poll() is not None:
            break
        time.sleep(0.1)
    raise UpdateError("更新程序还没准备好，旧版不会关闭。请稍后重试。")


def atomic_swap(first: Path, second: Path) -> None:
    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    swap = library.renamex_np
    swap.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    swap.restype = ctypes.c_int
    if swap(os.fsencode(first), os.fsencode(second), 2) != 0:
        raise OSError(ctypes.get_errno(), "安全替换应用未完成")


def replace_bundle(job: Path, relaunch=None) -> bool:
    data = read_job(job)
    directory = job.parent
    target = Path(data["target"])
    backup = directory / "backup.app"
    candidate = directory / "candidate.app"
    moved = False
    previous = candidate
    state_root().mkdir(parents=True, exist_ok=True)
    receipt = state_root() / "result.json"
    phase = "validation"
    try:
        snapshot = target.stat()
        if snapshot.st_dev != data["device"] or snapshot.st_ino != data["inode"] or backup.exists():
            raise UpdateError("当前应用已变化，更新没有执行。")
        validate_app(target, data["current"], data["architecture"])
        validate_app(candidate, data["version"], data["architecture"])
        if fingerprint(target) != data["originalDigest"] or fingerprint(candidate) != data["candidateDigest"]:
            raise UpdateError("应用在下载后发生变化，更新没有执行。")
        phase = "preflight"
        probe = directory / "probe.json"
        environment = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        subprocess.run([str(candidate / "Contents/MacOS" / EXECUTABLE), "--self-test", "--report", str(probe)],
                       check=True, timeout=60, capture_output=True, env=environment)
        if json.loads(probe.read_text()).get("passed") is not True:
            raise UpdateError("新版启动自检未通过。")
        phase = "replacement"
        atomic_swap(target, candidate)
        moved = True
        phase = "backup"
        candidate.rename(backup)
        previous = backup
        write_json(receipt, {"success": True, "version": data["version"], "message": f"已更新到 {data['version']}，原来的对话与设置保留。"})
        phase = "relaunch"
        (relaunch or (lambda app: command(["/usr/bin/open", "-n", str(app)])))(target)
        return True
    except Exception as error:
        restored = False
        if moved:
            try:
                atomic_swap(target, previous)
                restored = True
                try:
                    previous.rename(directory / "failed.app")
                except OSError:
                    pass
            except OSError:
                pass
        write_json(receipt, {"success": False, "version": data["current"], "phase": phase, "errorCode": type(error).__name__,
                             "message": "更新没有完成，已恢复旧版。" if restored else "更新没有完成，旧版或备份仍保留。请检查文件权限后重试。"})
        if not moved or restored:
            try:
                (relaunch or (lambda app: command(["/usr/bin/open", "-n", str(app)])))(target)
            except (OSError, subprocess.SubprocessError):
                pass
        return False


def helper_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-update", type=Path, required=True)
    arguments = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The update helper runs on macOS only")
    job = arguments.apply_update
    data = read_job(job)
    if Path(sys.executable).resolve() != (job.parent / "helper.app/Contents/MacOS" / EXECUTABLE).resolve():
        raise UpdateError("更新程序位置不匹配。")
    import fcntl

    state_root().mkdir(parents=True, exist_ok=True)
    with (job.parent / "helper.lock").open("a") as operation:
        try:
            fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 1
        write_json(job.parent / "ready.json", {"nonce": data["nonce"], "pid": os.getpid()})
        return _wait_and_replace(job, data)


def _wait_and_replace(job: Path, data: dict) -> int:
    deadline = time.monotonic() + 120
    while True:
        try:
            os.kill(data["parentPid"], 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            write_json(state_root() / "result.json", {"success": False, "version": data["current"], "phase": "parent_exit", "errorCode": "timeout", "message": "软件尚未关闭，本次更新没有执行。"})
            return 1
        time.sleep(0.25)
    audit = data.get("audit") is True
    if audit:
        target = Path(data["target"])
        if not target.parent.name.startswith("ai-first-update-audit-") or not target.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise UpdateError("隔离检查不允许更新真实安装位置。")
    import fcntl

    with (state_root().parent / "workspace.lock").open("a") as instance:
        try:
            fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            write_json(state_root() / "result.json", {"success": False, "version": data["current"], "message": "软件又被打开了，本次更新没有执行。关闭后重试即可。"})
            return 1
        def relaunch(app):
            fcntl.flock(instance, fcntl.LOCK_UN)
            if not audit:
                command(["/usr/bin/open", "-n", str(app)])
                return
            report = job.parent / "relaunch.json"
            command(["/usr/bin/open", "-W", "-n", str(app), "--args", "--smoke-test", "--report", str(report)], timeout=120)
            if not report.is_file() or json.loads(report.read_text()).get("passed") is not True:
                raise UpdateError("隔离 Cocoa 重启检查失败。")
        return 0 if replace_bundle(job, relaunch) else 1


def audit_update(app: Path, report: Path) -> None:
    import threading

    with tempfile.TemporaryDirectory(prefix="ai-first-update-audit-") as temporary:
        root = Path(temporary)
        target = root / APP_NAME
        command(["/usr/bin/ditto", str(app), str(target)])
        version = json.loads((app / "Contents/Resources/version.json").read_text())["release"]
        metadata = target / "Contents/Resources/version.json"
        metadata.write_text(json.dumps({"version": "0.4.0", "release": "0.4.0-macos-preview.2"}))
        command(["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(target)])
        directory = Path(tempfile.mkdtemp(prefix=".ai-first-update-", dir=root))
        directory.chmod(0o700)
        job = stage_bundle(target, app, version, "0.4.0-macos-preview.2", platform.machine(), directory)
        data = read_job(job)
        blocker = subprocess.Popen(["/bin/sleep", "2"])
        data.update({"parentPid": blocker.pid, "audit": True})
        write_json(job, data)
        threading.Thread(target=blocker.wait, daemon=True).start()
        original_home = os.environ.get("HOME")
        os.environ["HOME"] = str(root / "isolated-home")
        try:
            worker = start_helper(job)
            worker.wait(timeout=180)
            receipt = state_root() / "result.json"
            outcome = json.loads(receipt.read_text()) if receipt.is_file() else {}
            relaunched = json.loads((directory / "relaunch.json").read_text()) if (directory / "relaunch.json").is_file() else {}
            checks = {"replacement": worker.returncode == 0 and outcome.get("success") is True, "nativeRelaunch": relaunched.get("passed") is True,
                      "backupPreserved": (directory / "backup.app").is_dir(),
                      "version": json.loads((target / "Contents/Resources/version.json").read_text())["release"] == version}
            report.write_text(json.dumps({"passed": all(checks.values()), "checks": checks, "version": {"release": version},
                                          "diagnostics": {"phase": outcome.get("phase"), "errorCode": outcome.get("errorCode"), "helperReturnCode": worker.returncode,
                                                          "preflightReport": (directory / "probe.json").is_file(), "receipt": receipt.is_file()},
                                          "architecture": platform.machine(), "scope": "frozen helper, isolated app copies, atomic replacement and Cocoa relaunch; no installed app or real records"}, indent=2))
        finally:
            if original_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = original_home
