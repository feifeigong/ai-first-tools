"""Reproduce a UTF-8 GitHub response on a Windows legacy-codepage process."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WindowsReleaseTests(unittest.TestCase):
    def test_unicode_release_metadata_is_read_without_clobbering_published_assets(self):
        spec = importlib.util.spec_from_file_location("windows_stage", Path(__file__).resolve().parents[1] / "scripts/stage_windows_release.py")
        stage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stage)
        with tempfile.TemporaryDirectory(prefix="ai-first-stage-") as folder:
            root = Path(folder)
            for directory in ("workspace", "artifacts/windows", "artifacts/release"):
                (root / directory).mkdir(parents=True)
            (root / "workspace/AIFirst.Workspace.csproj").write_text("<Project><PropertyGroup><Version>0.3.10</Version></PropertyGroup></Project>")
            (root / "artifacts/windows/installer-test.json").write_text(json.dumps({"passed": True, "version": "0.3.10", "checks": {"synthetic": True}}))
            (root / "artifacts/windows/installed-self-test.json").write_text(json.dumps({"failed": 0, "passed": 67}))
            sums = []
            for filename in ("AI-First-Tools-Setup-0.3.10.exe", "AI-First-Tools-Portable-0.3.10-win-x64.zip"):
                data = b"Synthetic fixture, never executable"
                (root / "artifacts/release" / filename).write_bytes(data)
                sums.append(f"{hashlib.sha256(data).hexdigest()}  {filename}")
            (root / "artifacts/release/SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
            response = json.dumps([{"tag_name": "v0.3.10", "draft": False, "name": "中文发布说明，已公开"}], ensure_ascii=False)
            real_run = subprocess.run

            def fake_gh(arguments, **kwargs):
                self.assertEqual(arguments[:2], ["gh", "api"])
                # A real child process writes the same UTF-8 bytes gh produces.
                # The old text=True implementation fails under cp1252 here.
                if kwargs.get("text"):
                    kwargs["encoding"] = "cp1252"
                return real_run([sys.executable, "-c", "import sys;sys.stdout.buffer.write(" + repr(response.encode("utf-8")) + ")"], **kwargs)

            with patch.object(stage, "__file__", str(root / "scripts/stage_windows_release.py")), \
                    patch.object(sys, "argv", ["stage", "--commit", "a" * 40]), \
                    patch.object(stage.subprocess, "run", side_effect=fake_gh) as requests:
                stage.main()
            self.assertEqual(requests.call_count, 1)  # no tag mutation or upload


if __name__ == "__main__":
    unittest.main()
