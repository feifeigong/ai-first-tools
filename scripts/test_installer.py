from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import winreg


INSTALLER = None
ROOT = Path(__file__).resolve().parent.parent
INSTALL = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "AI First Tools"
REGISTRY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIFirstTools"


def execute(binary: Path, *arguments):
    result = subprocess.run([str(binary), *arguments], timeout=180, capture_output=True, env=os.environ.copy())
    return result.returncode


def uninstall(directory: Path):
    command = subprocess.list2cmdline([str(INSTALL / "Uninstall.exe"), "/S"]) + f" _?={directory}"
    return subprocess.run(command, timeout=180, capture_output=True, env=os.environ.copy()).returncode


class InstallerTests(unittest.TestCase):
    def test_install_runtime_update_guards_and_safe_uninstall(self):
        self.assertFalse(INSTALL.exists(), "Refuse to modify an existing installation")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            desktop = Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0]))
        self.assertFalse((desktop / "AI一手工具工作台.lnk").exists(), "Refuse to replace an existing shortcut")
        self.assertEqual(execute(INSTALLER, "/S"), 0)
        executable = INSTALL / "AI一手工具工作台.exe"
        self.assertTrue(executable.is_file())
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY) as key:
            self.assertEqual(winreg.QueryValueEx(key, "DisplayVersion")[0], "0.3.5")
            self.assertEqual(Path(winreg.QueryValueEx(key, "InstallLocation")[0]), INSTALL)
        report = ROOT / "artifacts" / "installed-self-test.json"
        environment = os.environ.copy()
        environment["DOTNET_ROOT"] = str(ROOT / "artifacts" / "absent-dotnet")
        environment["DOTNET_MULTILEVEL_LOOKUP"] = "0"
        result = subprocess.run([str(executable), "--self-test", "--report", str(report)], env=environment, timeout=120)
        self.assertEqual(result.returncode, 0)
        checks = json.loads(report.read_text(encoding="utf-8-sig"))
        self.assertEqual(checks["failed"], 0)
        engine = INSTALL / "tools" / "dialog-mover-v0.3" / "_internal" / "bin" / "txcript.exe"
        self.assertEqual(execute(engine, "--version"), 0)
        original_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateMutexW(None, False, "Local\\AI_FIRST_TOOLS_RUNNING")
        self.assertTrue(handle)
        try:
            self.assertEqual(execute(INSTALLER, "/S"), 1603)
            self.assertEqual(uninstall(INSTALL), 1603)
            self.assertEqual(hashlib.sha256(executable.read_bytes()).hexdigest(), original_hash)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(execute(INSTALLER, "/S"), 0)
        keep = INSTALL / "user-added-file.txt"
        keep.write_text("Installer fixture: retain user-added files", encoding="utf-8")
        unsafe = ROOT / "artifacts" / "not-the-installation"
        unsafe.mkdir(exist_ok=True)
        sentinel = unsafe / "sentinel.txt"
        sentinel.write_text("Installer fixture: wrong path must be rejected", encoding="utf-8")
        self.assertEqual(uninstall(unsafe), 1603)
        self.assertTrue(sentinel.is_file())
        self.assertTrue(executable.is_file())
        self.assertEqual(uninstall(INSTALL), 0)
        self.assertFalse(executable.exists())
        self.assertTrue(keep.is_file())
        keep.unlink()
        remaining_uninstaller = INSTALL / "Uninstall.exe"
        if remaining_uninstaller.exists():
            remaining_uninstaller.unlink()
        INSTALL.rmdir()
        with self.assertRaises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY)
        print(f"Install, bundled runtime ({checks['passed']} checks), update, running guard, path guard and safe uninstall: OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    arguments = parser.parse_args()
    INSTALLER = arguments.installer.resolve()
    unittest.main(argv=["test_installer"], verbosity=2)
