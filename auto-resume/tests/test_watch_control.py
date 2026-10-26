from __future__ import annotations

import json
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_auto_resume import watch_control as watch
from codex_auto_resume.procutil import hidden_kwargs


ROOT = Path(__file__).resolve().parents[1]


class WatchControlTests(unittest.TestCase):
    def test_mac_birth_time_is_kernel_metadata_not_time_zone_formatted_ps(self):
        executable = self.root / 'AI一手工具工作台.app/Contents/MacOS/AI First Tools'
        replies = [str(executable), str(executable) + ' --auto-resume-watch']
        with patch.object(watch.sys, 'platform', 'darwin'), \
                patch.object(watch, '_darwin_process_start', return_value=1792994400123456), \
                patch.object(watch, '_darwin_process_path', return_value=executable.resolve()), \
                patch.object(watch.subprocess, 'check_output', side_effect=replies) as ps:
            value = watch._inspect_process(123)
        self.assertEqual(value['started_at'], 1792994400123456)
        self.assertEqual(value['argv'][1:], ['--auto-resume-watch'])
        self.assertFalse(any('lstart=' in call.args[0] for call in ps.call_args_list))

    def test_mac_owner_uses_kernel_image_and_still_rejects_different_command_image(self):
        image = self.root / 'AI一手工具工作台.app/Contents/MacOS/AI First Tools'
        command_image = self.root / 'different/AI First Tools'
        with patch.object(watch.sys, 'platform', 'darwin'), \
                patch.object(watch, '_darwin_process_start', return_value=123456), \
                patch.object(watch, '_darwin_process_path', return_value=image.resolve()), \
                patch.object(watch.subprocess, 'check_output', side_effect=[str(command_image),str(command_image)+' --auto-resume-watch']):
            value = watch._inspect_process(123)
            self.assertEqual(value['executable'],str(image.resolve()))
            self.assertEqual(value['argv'][0],str(command_image.resolve()))
            self.assertFalse(watch._watcher(value))

    def test_mac_kernel_image_requires_complete_absolute_path(self):
        from unittest.mock import Mock
        query = Mock()
        data = os.fsencode(str(self.root / 'AI First Tools'))
        def kernel(pid, buffer, size):
            buffer.value = data
            return len(data)
        query.side_effect = kernel
        with patch.object(watch.ctypes, 'CDLL', return_value=Mock(proc_pidpath=query)):
            self.assertEqual(watch._darwin_process_path(123), Path(os.fsdecode(data)).resolve())
            for returned in (0,4096,len(data)+1):
                query.side_effect = None; query.return_value = returned
                with patch.object(watch.ctypes, 'get_errno', return_value=1):
                    with self.assertRaises(watch.WatchStateError): watch._darwin_process_path(123)
            query.side_effect = lambda pid,buffer,size: (setattr(buffer,'value',b'relative') or 8)
            with self.assertRaises(watch.WatchStateError): watch._darwin_process_path(123)

    def test_mac_kernel_birth_time_requires_complete_matching_process_metadata(self):
        from unittest.mock import Mock
        query = Mock()
        def kernel(pid, flavor, argument, pointer, size):
            info = pointer._obj
            info.pid = pid; info.seconds = 1792994400; info.microseconds = 123456
            return size
        query.side_effect = kernel
        with patch.object(watch.ctypes, 'CDLL', return_value=Mock(proc_pidinfo=query)):
            self.assertEqual(watch._darwin_process_start(123), 1792994400123456)
            for returned in (0, 4):
                query.side_effect = None; query.return_value = returned
                with patch.object(watch.ctypes, 'get_errno', return_value=1):
                    with self.assertRaises(watch.WatchStateError): watch._darwin_process_start(123)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resume-owner-test-")
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.pid = self.state / "watch.pid"
        self.report = self.root / "status.json"

    def tearDown(self):
        watch.release(self.pid)
        self.temporary.cleanup()

    def package(self, name="package-a"):
        root = self.root / name
        executable = root / "tools/auto-resume/AI一手续跑后台.exe"
        for path in [executable, root / "AI一手工具工作台.exe", root / "assets/auto-resume-bundled.ps1",
                     root / "assets/auto-resume-control.ps1"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic fixture; never executed", encoding="utf-8")
        (root / "assets/tool-catalog.json").write_text(json.dumps([{"id": "auto-resume", "nativePage": "auto-resume"}]), encoding="utf-8")
        return executable

    def identity(self, executable=None, pid=98765, started=1001):
        executable = executable or self.package()
        return {"pid": pid, "executable": str(executable), "started_at": started,
                "argv": [str(executable), "watch", "--quiet"]}

    def snapshot(self):
        return {str(path.relative_to(self.state)): path.read_bytes() for path in self.state.rglob("*") if path.is_file()}

    def test_legacy_watcher_requires_actual_full_package_and_exact_command(self):
        identity = self.identity()
        self.pid.write_text("98765\n", encoding="utf-8")
        before = self.snapshot()
        with patch.object(watch, "_inspect_process", return_value=identity):
            value = watch.inspect_watch(self.pid)
        self.assertTrue(value["running"] and value["ready"])
        self.assertEqual(value["executable"], identity["executable"])
        self.assertEqual(self.snapshot(), before)
        for argv in [[identity["executable"], "--version"], [identity["executable"], "watch", "--quiet", "extra"]]:
            with patch.object(watch, "_inspect_process", return_value={**identity, "argv": argv}):
                self.assertFalse(watch.inspect_watch(self.pid)["running"])

    def test_same_named_executable_without_workbench_is_not_adopted(self):
        executable = self.root / "unrelated/AI一手续跑后台.exe"
        executable.parent.mkdir()
        executable.touch()
        self.pid.write_text("98765\n", encoding="utf-8")
        with patch.object(watch, "_inspect_process", return_value=self.identity(executable)):
            self.assertFalse(watch.inspect_watch(self.pid)["running"])

    def test_cross_package_status_returns_verified_owner_not_current_package(self):
        owner = self.identity(self.package("previous-package"))
        other = self.package("new-package")
        self.pid.write_text("98765\n", encoding="utf-8")
        with patch.object(watch, "_inspect_process", return_value=owner), patch.object(watch, "state_path", return_value=self.pid), patch("sys.executable", str(other)):
            self.assertEqual(watch.write_status(self.report), 0)
        value = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertTrue(value["ok"] and value["running"] and value["ready"])
        self.assertEqual(value["executable"], owner["executable"])

    def test_unrelated_reused_pid_does_not_block_start(self):
        self.pid.write_text("98765\n", encoding="utf-8")
        unrelated = {"pid": 98765, "executable": str(self.root / "editor.exe"), "started_at": 1, "argv": [str(self.root / "editor.exe")]}
        current = self.identity(pid=os.getpid())
        with patch.object(watch, "_inspect_process", side_effect=lambda pid: unrelated if pid == 98765 else current):
            self.assertFalse(watch.inspect_watch(self.pid)["running"])
            self.assertTrue(watch.claim(self.pid))
        self.assertEqual(self.pid.read_text().strip(), str(os.getpid()))

    def test_new_owner_requires_matching_start_time_and_held_os_lock(self):
        current = self.identity(pid=os.getpid())
        with patch.object(watch, "_inspect_process", return_value=current):
            self.assertTrue(watch.claim(self.pid))
            self.assertTrue(watch.inspect_watch(self.pid)["ready"])
        with patch.object(watch, "_inspect_process", return_value={**current, "started_at": 1002}):
            with self.assertRaises(watch.WatchStateError):
                watch.inspect_watch(self.pid)
        # A metadata file alone must never prove a live watcher.
        stream = watch._held.pop(watch._key(self.pid))
        stream.close()
        with patch.object(watch, "_inspect_process", return_value=current):
            with self.assertRaises(watch.WatchStateError):
                watch.inspect_watch(self.pid)

    def test_status_does_not_create_state_or_write_config(self):
        nonexistent = self.root / "absent/watch.pid"
        with patch.object(watch, "state_path", return_value=nonexistent):
            self.assertEqual(watch.write_status(self.report), 0)
        self.assertFalse(nonexistent.parent.exists())
        self.assertFalse(json.loads(self.report.read_text())["running"])

    def test_status_failure_is_explicit_and_does_not_expose_raw_error(self):
        before = self.snapshot()
        with patch.object(watch, "state_path", side_effect=OSError("private-path-canary")):
            self.assertEqual(watch.write_status(self.report), 1)
        text = self.report.read_text(encoding="utf-8")
        self.assertNotIn("private-path-canary", text)
        self.assertFalse(json.loads(text)["ok"])
        self.assertEqual(self.snapshot(), before)

    def test_stop_writes_only_after_verifying_actual_owner_twice(self):
        owner = self.identity()
        self.pid.write_text("98765\n", encoding="utf-8")
        with patch.object(watch, "state_path", return_value=self.pid), patch.object(watch, "_inspect_process", return_value=owner) as inspect:
            self.assertEqual(watch.request_stop(), 0)
            self.assertEqual(inspect.call_count, 2)
        self.assertEqual((self.state / "stop.request").read_text(), "stop\n")
        self.assertEqual(self.pid.read_text(), "98765\n")

    def test_stop_rejects_changed_owner_and_leaves_no_stop_file(self):
        owner = self.identity()
        self.pid.write_text("98765\n", encoding="utf-8")
        with patch.object(watch, "state_path", return_value=self.pid), patch.object(watch, "_inspect_process", side_effect=[owner, None]):
            self.assertEqual(watch.request_stop(), 1)
        self.assertFalse((self.state / "stop.request").exists())

    def test_stop_does_not_target_unrelated_pid(self):
        unrelated = {"pid": 98765, "executable": str(self.root / "editor.exe"), "started_at": 1, "argv": [str(self.root / "editor.exe")]}
        self.pid.write_text("98765\n", encoding="utf-8")
        with patch.object(watch, "state_path", return_value=self.pid), patch.object(watch, "_inspect_process", return_value=unrelated):
            self.assertEqual(watch.request_stop(), 0)
        self.assertFalse((self.state / "stop.request").exists())

    def test_current_process_identity_comes_from_os(self):
        actual = watch._inspect_process(os.getpid())
        self.assertEqual(actual["pid"], os.getpid())
        expected = Path(sys.executable)
        if sys.platform == 'darwin':
            # Framework Python's launcher can exec Python.app. Independently
            # verify ps identity against the kernel, not the launcher's pathname.
            # https://github.com/apple-oss-distributions/xnu/blob/main/libsyscall/wrappers/libproc/libproc.h
            library = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
            library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            library.proc_pidpath.restype = ctypes.c_int
            buffer = ctypes.create_string_buffer(4096)
            self.assertGreater(library.proc_pidpath(os.getpid(),buffer,len(buffer)),0)
            expected = Path(buffer.value.decode('utf-8'))
        self.assertEqual(watch._key(Path(actual["executable"])), watch._key(expected))
        self.assertTrue(actual["started_at"])
        self.assertTrue(actual["argv"])

    def test_os_lock_excludes_other_process_and_recovers_after_release(self):
        script = "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from codex_auto_resume.watch_control import claim,release; p=Path(sys.argv[2]); print(claim(p),flush=True); sys.stdin.readline(); release(p)"
        child = subprocess.Popen([sys.executable, "-c", script, str(ROOT / "src"), str(self.pid)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, **hidden_kwargs())
        try:
            self.assertEqual(child.stdout.readline().strip(), "True")
            self.assertFalse(watch.claim(self.pid))
            child.communicate("stop\n", timeout=10)
            self.assertEqual(child.returncode, 0)
            self.assertTrue(watch.claim(self.pid))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_cli_status_and_stop_do_not_enter_cli_or_create_config(self):
        # Source entry is exercised with isolated state and no watch/model command.
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(self.root / "isolated-local")
        env["APPDATA"] = str(self.root / "isolated-roaming")
        env["XDG_DATA_HOME"] = str(self.root / "isolated-xdg")
        for args in [["--watch-status", str(self.report)], ["--request-stop"]]:
            process = subprocess.run([sys.executable, str(ROOT / "run.py"), *args], env=env,
                                     capture_output=True, timeout=10, **hidden_kwargs())
            self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        self.assertFalse((self.root / "isolated-local").exists())
        self.assertFalse((self.root / "isolated-xdg").exists())
