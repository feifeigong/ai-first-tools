"""Release failure guards with synthetic reports and a completely mocked GitHub."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import release_pair as release

SOURCE = "a" * 40
REQUEST = {"schema": 1, "attempt": 1, "publish": True, "windows_version": "0.4.4",
           "macos_release": "0.4.4-macos-preview.32", "notes": "docs/releases/v0.4.4.md"}


def artifact(name, ident, *, created="2020-01-02T00:00:00Z", content=b"synthetic"):
    return {"id": ident, "name": name, "created_at": created, "expires_at": "2099-01-01T00:00:00Z",
            "expired": False, "size_in_bytes": len(content),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "workflow_run": {"id": 123, "head_sha": SOURCE}}


def archive_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in files:
            archive.writestr(name, content)
    return stream.getvalue()


class ArtifactGitHub:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.run = {"id": 123, "head_sha": SOURCE, "head_branch": "master",
                    "created_at": "2020-01-01T00:00:00Z", "repository": {"full_name": release.REPOSITORY}}
        self.calls = []

    def __call__(self, path, *, method="GET", **kwargs):
        if method != "GET":
            raise AssertionError("Artifact acquisition must be read-only")
        self.calls.append(path)
        if path == "actions/runs/123":
            return copy.deepcopy(self.run)
        prefix = "actions/runs/123/artifacts?per_page=100&page="
        if not path.startswith(prefix):
            raise AssertionError("Unexpected artifact API path")
        start = (int(path.removeprefix(prefix)) - 1) * 100
        return {"total_count": len(self.artifacts), "artifacts": copy.deepcopy(self.artifacts[start:start + 100])}


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

    def native_inventory(self):
        return [artifact(name, index) for index, name in enumerate(release.NATIVE_ARTIFACTS, 1)]

    def download_fixture(self, files, extra=()):
        payloads = {index: archive_bytes(files[name]) for index, name in enumerate(release.NATIVE_ARTIFACTS, 1)}
        inventory = [artifact(name, index, content=payloads[index])
                     for index, name in enumerate(release.NATIVE_ARTIFACTS, 1)]
        github = ArtifactGitHub([*extra, *inventory])
        downloaded = []

        def download(args, *, stdout, **kwargs):
            self.assertEqual(args[:2], ["gh", "api"])
            self.assertEqual(args[-2:], ["--method", "GET"])
            prefix = f"repos/{release.REPOSITORY}/actions/artifacts/"
            self.assertTrue(args[2].startswith(prefix))
            ident = int(args[2].removeprefix(prefix).removesuffix("/zip"))
            downloaded.append(ident)
            stdout.write(payloads[ident])
            return subprocess.CompletedProcess(args, 0)

        return github, download, downloaded

    def test_artifacts_choose_creation_time_even_when_new_id_is_smaller(self):
        inventory = self.native_inventory()
        inventory.extend([artifact("macos-x86_64", 13616080933, created="2020-01-01T11:47:36Z"),
                          artifact("macos-x86_64", 13616080934, created="2020-01-01T11:47:36Z")])
        github = ArtifactGitHub(inventory)
        with patch.object(release, "api", side_effect=github):
            selected = release.select_artifacts(SOURCE, "123")
        self.assertEqual(selected["macos-x86_64"]["id"], 3)
        self.assertEqual(set(selected), set(release.NATIVE_ARTIFACTS))

    def test_artifact_selection_rejects_missing_unknown_expired_or_ambiguous_metadata(self):
        changes = ({"id": 0}, {"id": True}, {"digest": None}, {"size_in_bytes": 0},
                   {"expired": True}, {"expires_at": "2000-01-01T00:00:00Z"},
                   {"created_at": "not-a-time"}, {"created_at": "2020-01-02T00:00:00"},
                   {"created_at": "2999-01-01T00:00:00Z"},
                   {"created_at": "2019-01-01T00:00:00Z"},
                   {"workflow_run": {"id": 124, "head_sha": SOURCE}},
                   {"workflow_run": {"id": 123, "head_sha": "b" * 40}},
                   {"name": "macos-unknown"})
        for change in changes:
            inventory = self.native_inventory()
            inventory[-1].update(change)
            with self.subTest(change=change), patch.object(release, "api", side_effect=ArtifactGitHub(inventory)):
                with self.assertRaises(ValueError):
                    release.select_artifacts(SOURCE, "123")
        for inventory in (self.native_inventory()[:-1],
                          [*self.native_inventory(), artifact("macos-x86_64", 999)]):
            with self.subTest(inventory=inventory), patch.object(release, "api", side_effect=ArtifactGitHub(inventory)):
                with self.assertRaises(ValueError):
                    release.select_artifacts(SOURCE, "123")
        for change in ({"id": 124}, {"head_sha": "b" * 40}, {"head_branch": "other"},
                       {"repository": {"full_name": "other/project"}}):
            github = ArtifactGitHub(self.native_inventory())
            github.run.update(change)
            with self.subTest(run=change), patch.object(release, "api", side_effect=github):
                with self.assertRaises(ValueError):
                    release.select_artifacts(SOURCE, "123")

    def test_artifacts_paginate_and_reject_an_incomplete_inventory(self):
        github = ArtifactGitHub([{"name": "unrelated"}] * 100 + self.native_inventory())
        with patch.object(release, "api", side_effect=github):
            self.assertEqual(len(release.select_artifacts(SOURCE, "123")), 3)
        self.assertTrue(github.calls[-1].endswith("page=2"))
        with patch.object(release, "api", side_effect=[github.run, {"total_count": 4, "artifacts": self.native_inventory()},
                                                       {"total_count": 4, "artifacts": []}]):
            with self.assertRaises(ValueError):
                release.select_artifacts(SOURCE, "123")

    def test_exact_id_download_preserves_windows_and_both_mac_layouts_and_receipt(self):
        files = {"windows-release": [("release/setup.exe", b"synthetic Windows"), ("windows/check.json", b"{}")],
                 "macos-arm64": [("self-test.json", b"synthetic ARM")],
                 "macos-x86_64": [("self-test.json", b"synthetic Intel")]}
        github, download, downloaded = self.download_fixture(files, [
            artifact("macos-x86_64", 999, created="2020-01-01T11:47:36Z")])
        output = self.root / "artifacts/paired/native-artifacts.json"
        with patch.object(release, "ROOT", self.root), patch.object(release, "api", side_effect=github), \
                patch.object(release.subprocess, "run", side_effect=download):
            release.download_artifacts(SOURCE, "123", output)
        self.assertEqual(downloaded, [1, 2, 3])
        self.assertEqual((self.root / "artifacts/release/setup.exe").read_bytes(), b"synthetic Windows")
        self.assertTrue((self.root / "artifacts/windows/check.json").is_file())
        for name, content in (("macos-arm64", b"synthetic ARM"), ("macos-x86_64", b"synthetic Intel")):
            self.assertEqual((self.root / "artifacts/release-stage" / name / "self-test.json").read_bytes(), content)
        saved = json.loads(output.read_text())
        self.assertEqual((saved["source"], saved["run_id"]), (SOURCE, "123"))
        self.assertEqual(saved["artifacts"]["macos-x86_64"]["id"], 3)

    def test_latest_failed_native_report_never_falls_back_or_creates_release(self):
        dmg_name = f"AI-First-Tools-{REQUEST['macos_release']}-macos-arm64.dmg"
        digest = hashlib.sha256(b"synthetic DMG").hexdigest()
        files = {name: [("self-test.json", b'{"passed": false, "checks": {"native": false}}')]
                 for name in release.NATIVE_ARTIFACTS}
        files["macos-arm64"] += [(dmg_name, b"synthetic DMG"),
                                  ("SHA256SUMS-arm64.txt", f"{digest}  {dmg_name}\n")]
        github, download, downloaded = self.download_fixture(files, [
            artifact("macos-arm64", 999, created="2020-01-01T11:47:36Z")])
        with patch.object(release, "ROOT", self.root), patch.object(release, "api", side_effect=github), \
                patch.object(release.subprocess, "run", side_effect=download):
            release.download_artifacts(SOURCE, "123", self.root / "artifacts/paired/native-artifacts.json")
            with patch("verify_windows_release.validated_assets"), patch.object(release, "api") as writes:
                with self.assertRaisesRegex(ValueError, "Native app checks did not pass"):
                    release.prepare(REQUEST, SOURCE, "123", self.root / "receipt.json")
        self.assertNotIn(999, downloaded)
        writes.assert_not_called()

    def test_download_rejects_wrong_digest_or_size_before_any_extraction(self):
        for mutation in ({"digest": "sha256:" + "0" * 64}, {"size_in_bytes": 1}):
            files = {name: [("self-test.json", b"synthetic report")] for name in release.NATIVE_ARTIFACTS}
            github, download, _ = self.download_fixture(files)
            github.artifacts[-1].update(mutation)
            with self.subTest(mutation=mutation), patch.object(release, "ROOT", self.root), \
                    patch.object(release, "api", side_effect=github), \
                    patch.object(release.subprocess, "run", side_effect=download):
                with self.assertRaisesRegex(ValueError, "size or SHA-256 differs"):
                    release.download_artifacts(SOURCE, "123", self.root / "receipt.json")
            self.assertFalse((self.root / "artifacts").exists())
            self.assertFalse((self.root / "receipt.json").exists())

    def test_zip_rejects_unsafe_paths_symlinks_duplicates_and_file_directory_collisions(self):
        link = zipfile.ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases = [[(name, b"synthetic")] for name in ("../escape", "a/../escape", "./escape", "/absolute",
                                                           "C:/absolute", "a\\escape", "a//escape")]
        cases += [[(link, b"target")], [("same", b"file"), ("same/", b"")],
                  [("parent", b"file"), ("parent/child", b"file")]]
        for files in cases:
            with self.subTest(files=files), zipfile.ZipFile(io.BytesIO(archive_bytes(files))) as archive:
                with self.assertRaises(ValueError):
                    release.artifact_members(archive, self.root / "destination")
        destination = self.root / "destination"
        destination.mkdir()
        (destination / "kept").write_text("existing")
        with zipfile.ZipFile(io.BytesIO(archive_bytes([("kept", b"overwrite")]))) as archive:
            with self.assertRaises(ValueError):
                release.artifact_members(archive, destination)
        self.assertEqual((destination / "kept").read_text(), "existing")

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
