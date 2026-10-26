"""Local watcher identity and lifetime; never reads accounts or conversations."""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any


_FORMAT = "ai-first-watch-v1"
_held: dict[str, Any] = {}


class WatchStateError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _plain(path: Path) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise WatchStateError("state_unavailable")


def _read_text(path: Path, limit: int = 8192) -> str:
    _plain(path)
    with path.open("r", encoding="utf-8-sig") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise WatchStateError("state_unavailable")
    return value


def _atomic_json(path: Path, value: dict) -> None:
    _plain(path)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink()


def _try_lock(stream) -> bool:
    stream.seek(0)
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as error:
        # EACCES/EAGAIN are the documented non-blocking lock conflict results.
        if error.errno in (11, 13, 35, 36):
            return False
        raise


def _unlock(stream) -> None:
    stream.seek(0)
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _control_gate(path: Path):
    """Serialize new starts with stop requests, without locking out read-only probes."""
    gate = path.with_name("watch.control.lock")
    _plain(gate)
    with gate.open("a+b") as stream:
        if gate.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + 5
        while not _try_lock(stream):
            if time.monotonic() >= deadline:
                raise WatchStateError("control_busy")
            time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(stream)


def _lock_held(path: Path) -> bool:
    if _key(path) in _held:
        return True
    lock = path.with_name("watch.lock")
    if not lock.exists():
        return False
    _plain(lock)
    # Read-only status must neither create nor rewrite any state file.
    with lock.open("rb") as stream:
        if not _try_lock(stream):
            return True
        _unlock(stream)
    return False


def _darwin_process_start(pid: int) -> int | None:
    """Kernel birth time, independent of launchd's locale and time zone.

    Layout: Apple's bsd/sys/proc_info.h, PROC_PIDTBSDINFO. Read only the
    target process metadata; never request its environment or credentials.
    """
    class BsdInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint32) for name in (
            'flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid',
            'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
        _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
        _fields_ += [(name, ctypes.c_uint32) for name in ('nfiles', 'pgid', 'jobc', 'tdev', 'tpgid')]
        _fields_ += [('nice', ctypes.c_int32), ('seconds', ctypes.c_uint64), ('microseconds', ctypes.c_uint64)]

    library = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    query = library.proc_pidinfo
    query.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    query.restype = ctypes.c_int
    info = BsdInfo()
    size = query(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if size == 0 and ctypes.get_errno() == 3:  # ESRCH
        return None
    if (size != ctypes.sizeof(info) or info.pid != pid or not info.seconds
            or info.microseconds >= 1_000_000):
        raise WatchStateError('identity_unverified')
    return info.seconds * 1_000_000 + info.microseconds


def _inspect_process(pid: int) -> dict | None:
    """Read only this PID's executable, start time and command line."""
    if sys.platform == "darwin":
        try:
            executable_text = subprocess.check_output(["/bin/ps", "-ww", "-p", str(pid), "-o", "comm="], text=True).strip()
            command = subprocess.check_output(["/bin/ps", "-ww", "-p", str(pid), "-o", "command="], text=True).strip()
        except subprocess.CalledProcessError:
            return None
        started = _darwin_process_start(pid)
        if not executable_text or started is None or not command: return None
        executable = Path(executable_text)
        if not executable.is_absolute() or not (command == executable_text or command.startswith(executable_text + " ")):
            raise WatchStateError("identity_unverified")
        import shlex
        return {"pid": pid, "executable": str(executable.resolve()), "started_at": started,
                "argv": [str(executable.resolve()), *shlex.split(command[len(executable_text):])]}
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        # This compatibility branch serves source/Linux/Mac tests and existing watchers.
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart=", "-o", "command="], text=True).strip()
        if not output:
            return None
        import shlex
        pieces = output.split(maxsplit=5)
        if len(pieces) != 6:
            raise WatchStateError("identity_unverified")
        argv = shlex.split(pieces[5])
        executable = str(Path(argv[0]).resolve()) if Path(argv[0]).is_absolute() else argv[0]
        return {"pid": pid, "executable": executable, "started_at": " ".join(pieces[:5]), "argv": argv}

    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() in (87, 1168):
            return None
        raise WatchStateError("identity_unverified")
    try:
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise WatchStateError("identity_unverified")
        if code.value != 259:
            return None
        size = wintypes.DWORD(32768)
        name = ctypes.create_unicode_buffer(size.value)
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            raise WatchStateError("identity_unverified")
        created, ended, system, user = (wintypes.FILETIME() for _ in range(4))
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in (created, ended, system, user))):
            raise WatchStateError("identity_unverified")
        started = (created.dwHighDateTime << 32) | created.dwLowDateTime

        class UnicodeString(ctypes.Structure):
            _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT), ("Buffer", wintypes.LPWSTR)]
        query = ctypes.WinDLL("ntdll").NtQueryInformationProcess
        query.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
        query.restype = ctypes.c_long
        required = wintypes.ULONG()
        query(handle, 60, None, 0, ctypes.byref(required))
        if required.value < ctypes.sizeof(UnicodeString) or required.value > 131072:
            raise WatchStateError("identity_unverified")
        buffer = ctypes.create_string_buffer(required.value)
        if query(handle, 60, buffer, required.value, ctypes.byref(required)) < 0:
            raise WatchStateError("identity_unverified")
        value = UnicodeString.from_buffer(buffer)
        command = ctypes.wstring_at(value.Buffer, value.Length // 2)
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
        count = ctypes.c_int()
        arguments = shell.CommandLineToArgvW(command, ctypes.byref(count))
        if not arguments:
            raise WatchStateError("identity_unverified")
        try:
            argv = [arguments[index] for index in range(count.value)]
        finally:
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree(arguments)
        return {"pid": pid, "executable": name.value, "started_at": started, "argv": argv}
    finally:
        kernel.CloseHandle(handle)


def _watcher(identity: dict) -> bool:
    executable = Path(identity["executable"])
    argv = identity["argv"]
    if not executable.is_absolute() or not argv or _key(Path(argv[0])) != _key(executable):
        return False
    if executable.name == "AI一手续跑后台.exe":
        if argv[1:] != ["watch", "--quiet"] or executable.parent.name != "auto-resume" or executable.parent.parent.name != "tools":
            return False
        root = executable.parent.parent.parent
        required = [executable, root / "AI一手工具工作台.exe", root / "assets/auto-resume-bundled.ps1",
                    root / "assets/auto-resume-control.ps1", root / "assets/tool-catalog.json"]
        for path in required:
            _plain(path)
            if not path.is_file():
                return False
        catalog = json.loads(_read_text(root / "assets/tool-catalog.json", 65536))
        return isinstance(catalog, list) and any(isinstance(item, dict) and item.get("id") == "auto-resume" and item.get("nativePage") == "auto-resume" for item in catalog)
    if sys.platform == "darwin" and executable.name == "AI First Tools":
        if argv[1:] not in (["--auto-resume-watch"], ["--auto-resume-watch", "--manual"]): return False
        if executable.parent.name != "MacOS" or executable.parent.parent.name != "Contents" or executable.parent.parent.parent.name != "AI一手工具工作台.app": return False
        import plistlib
        info = executable.parent.parent / "Info.plist"
        _plain(executable)
        _plain(info)
        if not executable.is_file() or not info.is_file(): return False
        with info.open("rb") as stream: metadata = plistlib.load(stream)
        return metadata.get("CFBundleIdentifier") in {"cn.aifirst.tools", "cn.aifirst.tools.preview"} and metadata.get("CFBundleExecutable") == executable.name
    # Source installations are supported only with the exact original runner and modules.
    if executable.name.lower() not in ("python.exe", "pythonw.exe", "python", "python3") and not executable.name.startswith("python3."):
        return False
    if len(argv) != 4 or argv[2:] != ["watch", "--quiet"]:
        return False
    runner = Path(argv[1])
    if not runner.is_absolute() or runner.name != "run.py":
        return False
    source = runner.parent / "src/codex_auto_resume"
    required = [runner, source / "daemon.py", source / "workspace_control.py", source / "config.py"]
    return all(path.is_file() and not path.is_symlink() for path in required)


def _pid(path: Path) -> int | None:
    if not path.exists():
        return None
    text = _read_text(path, 128).strip()
    if not text or not text.splitlines()[0].isdigit():
        raise WatchStateError("state_unavailable")
    value = int(text.splitlines()[0])
    if value <= 0:
        raise WatchStateError("state_unavailable")
    return value


def _identity_matches(owner: dict, actual: dict, path: Path) -> bool:
    return (owner.get("format") == _FORMAT and owner.get("pid") == actual["pid"]
            and owner.get("started_at") == actual["started_at"]
            and isinstance(owner.get("executable"), str) and _key(Path(owner["executable"])) == _key(Path(actual["executable"]))
            and owner.get("state_directory") == _key(path.parent))


def inspect_watch(path: Path) -> dict:
    held = _lock_held(path)
    pid = _pid(path)
    idle = {"running": False, "ready": False, "pid": None, "executable": None}
    if pid is None:
        if held:
            raise WatchStateError("starting")
        return idle
    actual = _inspect_process(pid)
    if actual is None or not _watcher(actual):
        if held:
            raise WatchStateError("identity_unverified")
        return idle  # A stale or unrelated reused PID never blocks a new watcher.
    owner_path = path.with_name("watch.owner.json")
    if owner_path.exists():
        owner = json.loads(_read_text(owner_path))
        if not isinstance(owner, dict) or not _identity_matches(owner, actual, path):
            raise WatchStateError("identity_unverified")
        if not held:
            raise WatchStateError("identity_unverified")
    elif held:
        raise WatchStateError("starting")
    # An old version has no owner/OS lock, so its exact live process/package is required.
    return {"running": True, "ready": True, "pid": pid, "executable": actual["executable"]}


def claim(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _control_gate(path):
        return _claim_locked(path)


def _claim_locked(path: Path) -> bool:
    identity_key = _key(path)
    if identity_key in _held:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name("watch.lock")
    _plain(lock_path)
    stream = lock_path.open("a+b")
    try:
        if lock_path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        if not _try_lock(stream):
            stream.close()
            return False
        previous = _pid(path)
        if previous and previous != os.getpid():
            actual = _inspect_process(previous)
            if actual is not None and _watcher(actual):
                _unlock(stream)
                stream.close()
                return False
        actual = _inspect_process(os.getpid())
        if actual is None:
            raise WatchStateError("identity_unverified")
        owner = {"format": _FORMAT, "pid": os.getpid(), "executable": actual["executable"],
                 "started_at": actual["started_at"], "state_directory": _key(path.parent)}
        _plain(path)
        path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        _atomic_json(path.with_name("watch.owner.json"), owner)
        _held[identity_key] = stream
        return True
    except BaseException:
        if not stream.closed:
            stream.close()  # Closing releases the OS lock even if identity persistence failed.
        raise


def release(path: Path) -> None:
    stream = _held.pop(_key(path), None)
    try:
        if _pid(path) == os.getpid():
            path.unlink(missing_ok=True)
            owner_path = path.with_name("watch.owner.json")
            if owner_path.exists():
                owner = json.loads(_read_text(owner_path))
                if isinstance(owner, dict) and owner.get("pid") == os.getpid():
                    owner_path.unlink()
    except (OSError, ValueError, WatchStateError):
        pass
    finally:
        if stream is not None:
            stream.close()


def state_path() -> Path:
    from .config import load_config
    path = load_config().resolved_state_dir()
    if not path.is_absolute():
        raise WatchStateError("state_unavailable")
    return path / "watch.pid"


def write_status(report: Path) -> int:
    result = {"ok": False, "installed": True, "running": False, "ready": False,
              "pid": None, "executable": None, "error": "", "errorCode": ""}
    try:
        result.update(inspect_watch(state_path()))
        result["ok"] = True
    except Exception as error:
        result["errorCode"] = error.code if isinstance(error, WatchStateError) else "state_unavailable"
        result["error"] = "自动续跑暂时无法确认状态，请稍后重试。"
    _atomic_json(report, result)
    return 0 if result["ok"] else 1


def request_stop() -> int:
    try:
        path = state_path()
        initial = inspect_watch(path)
        if not initial["running"]:
            return 0
        # New instances cannot claim ownership between this final check and the write.
        with _control_gate(path):
            if inspect_watch(path) != initial:
                raise WatchStateError("identity_unverified")
            stop = path.with_name("stop.request")
            _plain(stop)
            stop.write_text("stop\n", encoding="utf-8")
        return 0
    except Exception:
        return 1
