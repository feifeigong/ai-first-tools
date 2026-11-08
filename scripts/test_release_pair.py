"""Release failure guards with synthetic reports and a completely mocked GitHub."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import release_pair as release

SOURCE = "a" * 40
REQUEST = {"schema": 1, "attempt": 1, "publish": True, "windows_version": "0.4.4",
           "macos_release": "0.4.4-macos-preview.32", "notes": "docs/releases/v0.4.4.md"}


def receipt():
    result = {"schema": 1, "source": SOURCE, "run_id": "123", "request": copy.deepcopy(REQUEST)}
    for platform, ident, field, version in (("windows", 1, "version", REQUEST["windows_version"]),
                                           ("macos", 2, "release", REQUEST["macos_release"])):
        result[platform] = {"passed": True, "source": SOURCE, "releaseId": ident, field: version,
                            "assets": [{"name": name, "bytes": 10, "sha256": "b" * 64}
                                       for name in sorted(release.expected_names(REQUEST, platform))]}
    return result


class OfflineGitHub:
    def __init__(self):
        self.writes = []
        self.fail_windows = False
        self.records = {}
        for platform, report in receipt().items():
            if platform not in ("windows", "macos"):
                continue
            ident = report["releaseId"]
            self.records[ident] = {"id": ident, "tag_name": release.tags(REQUEST)[platform],
                "draft": True, "prerelease": platform == "macos",
                "html_url": f"https://github.com/{release.REPOSITORY}/releases/tag/{release.tags(REQUEST)[platform]}",
                "assets": [{"name": item["name"], "state": "uploaded", "size": item["bytes"],
                            "digest": "sha256:" + item["sha256"]} for item in report["assets"]]}

    def __call__(self, path, *, method="GET", payload=None, optional=False):
        if path.startswith("git/ref/"):
            return {"object": {"type": "commit", "sha": SOURCE}}
        if path == "releases?per_page=100":
            return copy.deepcopy(list(self.records.values()))
        ident = int(path.split("/")[-1])
        if method == "PATCH":
            self.writes.append((ident, copy.deepcopy(payload)))
            if ident == 1 and self.fail_windows:
                raise RuntimeError("Synthetic publish failure")
            self.records[ident].update(payload)
        elif method != "GET":
            raise AssertionError("Unexpected mutation")
        return copy.deepcopy(self.records[ident])


class ReleasePairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="paired-release-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in (".github", "workspace", "macos", "docs/releases"):
            (self.root / directory).mkdir(parents=True)
        (self.root / release.REQUEST_PATH).write_text(json.dumps(REQUEST))
        (self.root / "workspace/AIFirst.Workspace.csproj").write_text(
            "<Project><PropertyGroup><Version>0.4.4</Version></PropertyGroup></Project>")
        (self.root / "macos/version.json").write_text(json.dumps(
            {"version": "0.4.4", "release": REQUEST["macos_release"]}))
        (self.root / REQUEST["notes"]).write_text("Synthetic reviewed release notes")
        process = patch("subprocess.Popen", side_effect=AssertionError("Real processes are forbidden"))
        process.start()
        self.addCleanup(process.stop)

    def test_request_requires_enabled_matching_versions_and_reviewed_notes(self):
        self.assertEqual(release.read_request(self.root), REQUEST)
        for change in ({"publish": False}, {"windows_version": "0.4.3"},
                       {"macos_release": "0.4.4-macos-preview.31"}, {"attempt": 0},
                       {"attempt": True}, {"notes": "../unreviewed.md"}):
            with self.subTest(change=change):
                (self.root / release.REQUEST_PATH).write_text(json.dumps({**REQUEST, **change}))
                with self.assertRaises(ValueError):
                    release.read_request(self.root)

    def test_release_context_requires_exact_master_checkout_and_source_head(self):
        env = {"GITHUB_REPOSITORY": release.REPOSITORY, "GITHUB_REF": "refs/heads/master",
               "GITHUB_SHA": SOURCE, "GITHUB_RUN_ID": "123"}
        with patch.dict(os.environ, env, clear=True), patch.object(release, "command", return_value=SOURCE), \
                patch.object(release, "api", return_value={"object": {"sha": SOURCE}}):
            self.assertEqual(release.validate_context(SOURCE), "123")
            with self.assertRaises(ValueError):
                release.validate_context("c" * 40)
            with patch.object(release, "api", return_value={"object": {"sha": "c" * 40}}):
                with self.assertRaises(ValueError):
                    release.validate_context(SOURCE)
            with patch.dict(os.environ, {"GITHUB_REF": "refs/pull/1/merge"}):
                with self.assertRaises(ValueError):
                    release.validate_context(SOURCE)

    def test_prepare_never_changes_public_releases_or_wrong_tags(self):
        github = OfflineGitHub()
        github.records[1]["draft"] = False
        with patch.object(release, "api", side_effect=github):
            with self.assertRaises(ValueError):
                release.targets(REQUEST, SOURCE)
        self.assertEqual(github.writes, [])
        for reference in ({"type": "tag", "sha": SOURCE}, {"type": "commit", "sha": "c" * 40}):
            def wrong_tag(path, **kwargs):
                return [] if path.startswith("releases?") else {"object": reference}
            with self.subTest(reference=reference), patch.object(release, "api", side_effect=wrong_tag):
                with self.assertRaises(ValueError):
                    release.targets(REQUEST, SOURCE)

    def test_failed_local_validation_cannot_create_tags_or_drafts(self):
        with patch.object(release, "validate_local_artifacts", side_effect=ValueError("Missing native checks")), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.prepare(REQUEST, SOURCE, "123", self.root / "receipt.json")
        api.assert_not_called()

    def test_additional_failed_installer_check_blocks_tag_creation(self):
        directory = self.root / "artifacts/windows"
        directory.mkdir(parents=True)
        (directory / "installer-test.json").write_text(json.dumps({
            "passed": True, "checks": {"silentInstall": True, "additionalNativeCheck": False}}))
        with patch.object(release, "ROOT", self.root), \
                patch("verify_windows_release.validated_assets"), \
                patch("stage_macos_release.validated_assets"), patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.prepare(REQUEST, SOURCE, "123", self.root / "receipt.json")
        api.assert_not_called()

    def test_failed_independent_download_cannot_create_publication_receipt(self):
        github = OfflineGitHub()
        output = self.root / "receipt.json"
        with patch.object(release, "ROOT", self.root), \
                patch.object(release, "validate_local_artifacts"), \
                patch.object(release, "api", side_effect=github), \
                patch.object(release, "command", side_effect=subprocess.CalledProcessError(1, "verification")):
            with self.assertRaises(subprocess.CalledProcessError):
                release.prepare(REQUEST, SOURCE, "123", output)
        self.assertFalse(output.exists())
        self.assertTrue(all(value["draft"] is True for _, value in github.writes))

    def test_receipt_requires_exact_run_source_version_and_all_3_plus_23_assets(self):
        self.assertEqual(len(release.expected_names(REQUEST, "windows")), 3)
        self.assertEqual(len(release.expected_names(REQUEST, "macos")), 23)
        release.validate_receipt(receipt(), REQUEST, SOURCE, "123")
        variants = []
        for key, value in (("source", "c" * 40), ("run_id", "124")):
            item = receipt()
            item[key] = value
            variants.append(item)
        for platform in ("windows", "macos"):
            for field, value in (("passed", False), ("source", "c" * 40), ("assets", [])):
                item = receipt()
                item[platform][field] = value
                variants.append(item)
            missing = receipt()
            missing[platform]["assets"].pop()
            variants.append(missing)
        wrong_version = receipt()
        wrong_version["macos"]["release"] = "0.4.4-macos-preview.31"
        variants.append(wrong_version)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(ValueError):
                release.validate_receipt(item, REQUEST, SOURCE, "123")

    def test_remote_asset_mutation_blocks_both_publications(self):
        for mutation in ("digest", "size", "state", "missing"):
            github = OfflineGitHub()
            if mutation == "missing":
                github.records[2]["assets"].pop()
            else:
                github.records[2]["assets"][0][mutation] = "changed"
            with self.subTest(mutation=mutation), patch.object(release, "api", side_effect=github):
                with self.assertRaises(ValueError):
                    release.publish(receipt(), REQUEST, SOURCE, "123", self.root / "result.json")
            self.assertEqual(github.writes, [])

    def test_partial_publish_retry_never_reuploads_or_rewrites_public_mac(self):
        github = OfflineGitHub()
        github.fail_windows = True
        output = self.root / "result.json"
        with patch.object(release, "api", side_effect=github):
            with self.assertRaises(RuntimeError):
                release.publish(receipt(), REQUEST, SOURCE, "123", output)
            partial = json.loads(output.read_text())
            self.assertFalse(partial["passed"])
            self.assertEqual(set(partial["published"]), {"macos"})
            github.fail_windows = False
            github.writes.clear()
            release.publish(receipt(), REQUEST, SOURCE, "123", output)
        self.assertEqual([ident for ident, _ in github.writes], [1])
        self.assertEqual(github.writes[0][1]["make_latest"], "true")
        self.assertTrue(json.loads(output.read_text())["passed"])

    def test_macos_gate_skips_only_known_enabled_master_release_request(self):
        event = self.root / "event.json"
        event.write_text(json.dumps({"before": "b" * 40}))
        env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": release.REPOSITORY,
               "GITHUB_REF": "refs/heads/master", "GITHUB_EVENT_PATH": str(event)}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(release, "command", return_value=release.REQUEST_PATH + "\n"), \
                patch.object(release, "read_request", return_value=REQUEST):
            self.assertFalse(release.macos_gate())
            with patch.dict(os.environ, {"PAIRED_RELEASE": "true"}):
                self.assertTrue(release.macos_gate())
            with patch.dict(os.environ, {"GITHUB_REF": "refs/heads/feature"}):
                self.assertTrue(release.macos_gate())
            with patch.object(release, "read_request", side_effect=ValueError("Disabled request")):
                self.assertTrue(release.macos_gate())
            with patch.object(release, "command", side_effect=subprocess.CalledProcessError(1, "git")):
                self.assertTrue(release.macos_gate())


if __name__ == "__main__":
    unittest.main()
