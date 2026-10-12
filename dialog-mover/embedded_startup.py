from __future__ import annotations

import ctypes
import json
import os
import re
import tempfile
import threading
from pathlib import Path


class EmbeddedStartup:
    def __init__(self, ready_file: Path, host_process: int) -> None:
        self.ready_file = ready_file
        self.host_process = host_process
        self.window = None
        self.closed = threading.Event()

    @classmethod
    def from_environment(cls):
        filename = os.environ.get("AI_FIRST_WORKSPACE_READY_FILE", "")
        host = os.environ.get("AI_FIRST_WORKSPACE_HOST_PID", "")
        if not filename or not host.isdecimal() or int(host) <= 0:
            return None
        ready_file = Path(filename).resolve()
        if ready_file.name != "window.json" or not re.fullmatch(r"ai-first-startup-[0-9a-f]{32}", ready_file.parent.name):
            return None
        if ready_file.parent.parent != Path(tempfile.gettempdir()).resolve() or not ready_file.parent.is_dir():
            return None
        return cls(ready_file, int(host))

    def bind(self, window) -> None:
        self.window = window
        window.events.before_show += self.before_show
        window.events.loaded += self.loaded
        window.events.closed += self.closed.set

    def before_show(self) -> None:
        user = self.user_api()
        handle = self.window.native.Handle.ToInt64()
        style = user.GetWindowLongPtrW(handle, -20)
        user.SetWindowLongPtrW(handle, -20, (style & ~0x00040000) | 0x00000080)
        threading.Thread(target=self.watch_host, daemon=True).start()

    @staticmethod
    def user_api():
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        return user

    def loaded(self) -> None:
        self.window.focus = True
        if not self.ready_file.parent.is_dir():
            self.restore()
            return
        try:
            temporary = self.ready_file.with_suffix(".tmp")
            temporary.write_text(json.dumps({"processId": os.getpid(), "window": self.window.native.Handle.ToInt64()}), encoding="utf-8")
            temporary.replace(self.ready_file)
        except OSError:
            self.restore()
            return

    def watch_host(self) -> None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        process = kernel.OpenProcess(0x00100000, False, self.host_process)
        if not process:
            self.restore()
            return
        try:
            while not self.closed.wait(0.25):
                if not self.ready_file.parent.is_dir() or kernel.WaitForSingleObject(process, 0) != 0x00000102:
                    self.restore()
                    return
        finally:
            kernel.CloseHandle(process)

    def restore(self) -> None:
        if self.closed.is_set():
            return
        self.window.focus = True
        native = self.window.native
        from System import Action

        def show() -> None:
            user = self.user_api()
            handle = native.Handle.ToInt64()
            user.SetWindowLongPtrW(handle, -20, (user.GetWindowLongPtrW(handle, -20) & ~(0x08000000 | 0x00000080)) | 0x00040000)
            native.ShowInTaskbar = True
            self.window.show()

        native.BeginInvoke(Action(show))
