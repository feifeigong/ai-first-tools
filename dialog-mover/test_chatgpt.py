from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import chatgpt
from core.common import make_session


STAMP = 1791600000000


def local_session(thread_id: str, stamp: int = STAMP) -> dict:
    session = make_session(thread_id, thread_id, stamp, source="chatgpt_work", kind="codex")
    session["key"] = f"codex:thread:local:{thread_id}"
    return session


def project(project_id: str, title: str = "同名项目", pinned: bool = False) -> dict:
    return {"id": project_id, "key": f"codex:project:{project_id}", "title": title, "kind": "project", "path": "D:\\project", "sessions": [], "pinned": pinned, "keepEmpty": True}


def web_project(project_id: str, name: str = "同名项目") -> dict:
    return {"gizmo": {"gizmo": {"id": project_id, "display": {"name": name}}}}


def empty_local() -> dict:
    return {"projects": [], "pinned": [], "recent": [], "mirrors": {}}


class SidebarTests(unittest.TestCase):
    def test_unified_order_not_legacy_project_order(self):
        local = empty_local()
        local["projects"] = [project("old"), project("second"), project("first")]
        atoms = {"unified-sidebar-project-order-v1": ["codex:project:first", "codex:project:second"]}
        groups = chatgpt.build_groups({"items": [], "projects": []}, local, {"project-order": ["old"]}, atoms, {})
        self.assertEqual([group["id"] for group in groups], ["first", "second", "old"])
        self.assertTrue(all(group["keepEmpty"] for group in groups))

    def test_same_name_different_ids_are_not_merged(self):
        local = empty_local()
        local["projects"] = [project("local")]
        web = {"items": [], "projects": [web_project("g-p-one"), web_project("g-p-two")]}
        groups = chatgpt.build_groups(web, local, {}, {}, {})
        self.assertEqual(len(groups), 3)
        self.assertEqual(len({group["key"] for group in groups}), 3)

    def test_pinned_mixed_manual_order(self):
        local = empty_local()
        local["projects"] = [project("pin", pinned=True)]
        web = {"projects": [], "items": [{"id": "first", "title": "first", "update_time": STAMP - 100, "is_starred": True}, {"id": "second", "title": "second", "update_time": STAMP, "is_starred": True}]}
        sidebar = {"pinnedConversations": [{"conversation": {"id": "first"}}, {"conversation": {"id": "second"}}]}
        atoms = {"unified-sidebar-pinned-order-v1": ["chatgpt:conversation:second", "codex:project:pin", "chatgpt:conversation:first"]}
        groups = chatgpt.build_groups(web, local, {}, atoms, sidebar)
        self.assertEqual([group["sessions"][0]["id"] if group["sessions"] else group["id"] for group in groups], ["second", "pin", "first"])

    def test_custom_gpts_and_retired_project_chats_stay_recent(self):
        items = [{"id": "gpt", "gizmo_id": "g-custom", "update_time": STAMP}, {"id": "retired", "gizmo_id": "g-p-retired", "update_time": STAMP - 1}]
        local = empty_local()
        local["mirrors"] = {"g-p-retired": [local_session("mirror")]}
        groups = chatgpt.build_groups({"items": items, "projects": []}, local, {}, {}, {})
        self.assertEqual(len(groups), 1)
        self.assertEqual({item["id"] for item in groups[0]["sessions"]}, {"gpt", "retired", "mirror"})

    def test_cloud_and_local_mirror_merge_by_project_id(self):
        local = empty_local()
        local["mirrors"] = {"g-p-one": [local_session("local")]}
        web = {"items": [{"id": "cloud", "gizmo_id": "g-p-one", "update_time": STAMP + 1}], "projects": [web_project("g-p-one")]}
        groups = chatgpt.build_groups(web, local, {}, {}, {})
        self.assertEqual(len(groups), 1)
        self.assertEqual([item["id"] for item in groups[0]["sessions"]], ["cloud", "local"])

    def test_archived_temporary_filtered_and_work_classification(self):
        web = {"projects": [], "items": [{"id": "archived", "is_archived": True}, {"id": "temporary", "is_temporary_chat": True}, {"id": "work", "trial_conversation_type": "work"}]}
        groups = chatgpt.build_groups(web, empty_local(), {}, {}, {})
        self.assertEqual([item["id"] for group in groups for item in group["sessions"]], ["work"])
        self.assertEqual(groups[0]["sessions"][0]["kind"], "work")

    def test_custom_section_preserves_children_once(self):
        local = empty_local()
        folder = project("folder")
        folder["sessions"] = [local_session("child")]
        local["projects"] = [folder]
        sidebar = {"customSections": {"sections": [{"id": "custom", "name": "收藏", "itemKeys": ["codex:thread:local:child"]}], "sectionOrder": ["custom", "threads", "chats"]}}
        groups = chatgpt.build_groups({"items": [], "projects": []}, local, {}, {}, sidebar)
        self.assertEqual([item["id"] for group in groups for item in group["sessions"]], ["child"])
        self.assertEqual(groups[0]["section"], "custom")
        self.assertEqual(groups[1]["sessions"], [])

    def test_list_mode_and_manual_chats(self):
        local = empty_local()
        folder = project("folder")
        folder["sessions"] = [local_session("older", STAMP - 100)]
        local["projects"] = [folder]
        local["recent"] = [local_session("newer", STAMP)]
        atoms = {"flat-project-sidebar-preferences-v1": {"mode": "list", "chatSortMode": "manual", "manualSortVersion": 1}, "unified-sidebar-chat-order-v1": ["codex:thread:local:older", "codex:thread:local:newer"]}
        groups = chatgpt.build_groups({"items": [], "projects": []}, local, {}, atoms, {})
        self.assertEqual(len(groups), 1)
        self.assertEqual([item["id"] for item in groups[0]["sessions"]], ["older", "newer"])

    def test_legacy_priority_is_migrated_like_native_app(self):
        for mode in ("priority", "created_at", "manual"):
            self.assertEqual(chatgpt.sort_mode({"flat-project-sidebar-preferences-v1": {"chatSortMode": mode}}, "chatSortMode"), "updated_at")
        self.assertEqual(chatgpt.sort_mode({"flat-project-sidebar-preferences-v1": {"chatSortMode": "manual", "manualSortVersion": 1}}, "chatSortMode"), "manual")


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.old_cache = copy.deepcopy(chatgpt._WEB_CACHE)
        chatgpt._WEB_CACHE.update(stamp=0, data=None)

    def tearDown(self):
        chatgpt._WEB_CACHE.update(self.old_cache)

    def test_all_pages_despite_inaccurate_total(self):
        seen = []
        def get(path):
            seen.append(path)
            if "/conversations?" in path:
                offset = int(parse_qs(urlparse(path).query)["offset"][0])
                count = 100 if offset < 200 else 3
                return {"items": [{"id": str(offset + index)} for index in range(count)], "total": offset + count + 1}
            return {"items": [], "cursor": None}
        data = chatgpt.fetch_web(get, pages_hint=2)
        self.assertEqual(len(data["items"]), 203)
        self.assertEqual(data["pages"], 3)
        self.assertGreaterEqual(len(seen), 4)  # pages beyond the end may be asked for, but never trusted

    def test_batches_share_connections_and_failures_are_retried_alone(self):
        batches, singles = [], []
        def one(path):
            if path.startswith("/backend-api/conversations?"):
                offset = int(parse_qs(urlparse(path).query)["offset"][0])
                return {"items": [{"id": str(offset + index)} for index in range(100 if offset < 200 else 3)]}
            if "/sidebar?" in path:
                return {"items": [web_project("g-p-one")], "cursor": None}
            return {"items": [{"id": "project-chat"}], "cursor": None}
        def get(path):
            singles.append(path)
            return one(path)
        def many(paths):
            batches.append(list(paths))
            return [None if "offset=100" in path else one(path) for path in paths]  # one request fails in its batch
        get.many = many
        data = chatgpt.fetch_web(get, pages_hint=2)
        self.assertEqual(len(data["items"]), 204)
        self.assertTrue(batches)
        self.assertTrue(any("offset=100" in path for path in singles))  # asked again on its own
        self.assertLessEqual(len(singles), 2)

    def test_failed_page_is_not_cached_as_complete(self):
        def get(path):
            if "/sidebar?" in path:
                return {"items": [], "cursor": None}
            return {"items": [{"id": str(index)} for index in range(100)]} if "offset=0" in path else None
        with self.assertRaisesRegex(RuntimeError, "第 2 页"):
            chatgpt.web_data(get)
        self.assertIsNone(chatgpt._WEB_CACHE["data"])

    def test_project_cursor_and_supplementary_conversations(self):
        def get(path):
            if path.startswith("/backend-api/conversations"):
                return {"items": []}
            if "/sidebar?" in path:
                self.assertIn("owned_only=false", path)
                return {"items": [web_project("g-p-two" if "cursor=" in path else "g-p-one")], "cursor": None if "cursor=" in path else "next"}
            self.assertIn("limit=20", path)
            return {"items": [{"id": "two" if "g-p-two" in path else "one"}], "cursor": None}
        data = chatgpt.fetch_web(get)
        self.assertEqual(len(data["projects"]), 2)
        self.assertEqual({item["gizmo_id"] for item in data["items"]}, {"g-p-one", "g-p-two"})

    def test_repeated_page_fails_instead_of_looping(self):
        with self.assertRaisesRegex(RuntimeError, "重复"):
            chatgpt.fetch_web(lambda path: {"items": [{"id": str(index)} for index in range(100)]})

    def test_saved_copy_answers_at_once_and_refreshes_in_background(self):
        import threading
        import time
        with tempfile.TemporaryDirectory(prefix="dm-swr-") as directory:
            old_file, old_refresh = chatgpt._cache_file, dict(chatgpt._REFRESH)
            chatgpt._cache_file = lambda: Path(directory) / "cache.json"
            try:
                chatgpt._save_disk(time.time() - 3600, {"items": [{"id": "old"}], "projects": [], "pages": 1})
                chatgpt._WEB_CACHE.update(stamp=0, data=None, force=False)
                release = threading.Event()
                def get(path):
                    release.wait(10)
                    return {"items": [{"id": "new"}], "cursor": None} if "/conversations?" in path else {"items": [], "cursor": None}
                started = time.time()
                first = chatgpt.web_data(get, allow_stale=True)
                self.assertLess(time.time() - started, 2)
                self.assertEqual([item["id"] for item in first["items"]], ["old"])
                self.assertTrue(chatgpt.info()["refreshing"])
                release.set()
                deadline = time.time() + 10
                while chatgpt.info()["refreshing"] and time.time() < deadline:
                    time.sleep(0.05)
                self.assertEqual([item["id"] for item in chatgpt.web_data(get, allow_stale=True)["items"]], ["new"])
                self.assertEqual(chatgpt._load_disk()[1]["items"][0]["id"], "new")  # the saved copy moved on too
            finally:
                chatgpt._cache_file = old_file
                chatgpt._REFRESH.update(old_refresh)

    def test_explicit_refresh_waits_for_the_real_answer(self):
        with tempfile.TemporaryDirectory(prefix="dm-force-") as directory:
            old_file = chatgpt._cache_file
            chatgpt._cache_file = lambda: Path(directory) / "cache.json"
            try:
                chatgpt._save_disk(1.0, {"items": [{"id": "old"}], "projects": [], "pages": 1})
                chatgpt._WEB_CACHE.update(stamp=0, data=None, force=False)
                chatgpt.invalidate()
                get = lambda path: {"items": [{"id": "fresh"}], "cursor": None} if "/conversations?" in path else {"items": [], "cursor": None}
                self.assertEqual([item["id"] for item in chatgpt.web_data(get, allow_stale=True)["items"]], ["fresh"])
            finally:
                chatgpt._cache_file = old_file


class NativeDataTests(unittest.TestCase):
    def test_paths_tombstones_projectless_and_missing_body(self):
        with tempfile.TemporaryDirectory(prefix="dm-chatgpt-test-") as directory:
            root = Path(directory)
            (root / "sessions").mkdir()
            (root / "sqlite").mkdir()
            state = {"local-projects": {"folder": {"name": "文件夹", "rootPaths": ["D:\\project"]}}, "projectless-thread-ids": ["loose"], "project-order": ["folder"], "electron-persisted-atom-state": {}}
            (root / ".codex-global-state.json").write_text(json.dumps(state), encoding="utf-8")
            connection = sqlite3.connect(root / "state_5.sqlite")
            connection.executescript("CREATE TABLE projects(id TEXT,name TEXT,position INTEGER); CREATE TABLE project_roots(project_id TEXT,path TEXT,position INTEGER); CREATE TABLE threads(id TEXT,source TEXT,thread_source TEXT,cwd TEXT,title TEXT,name TEXT,recency_at_ms INTEGER,archived INTEGER,rollout_path TEXT,created_at_ms INTEGER DEFAULT 0);")
            for thread_id, provenance, archived in [("assigned", "user", 0), ("loose", "user", 0), ("deleted", "user", 0), ("archived", "user", 1), ("subagent", "subagent", 0)]:
                connection.execute("INSERT INTO threads(id,source,thread_source,cwd,title,name,recency_at_ms,archived,rollout_path) VALUES (?,?,?,?,?,?,?,?,?)", (thread_id, "vscode", provenance, "\\\\?\\D:\\project", thread_id, thread_id, STAMP, archived, str(root / "not-downloaded.jsonl")))
            connection.commit()
            connection.close()
            connection = sqlite3.connect(root / "sqlite" / "codex-dev.db")
            connection.executescript("CREATE TABLE local_thread_catalog_sync_state(host_id TEXT,initial_build_complete INTEGER); INSERT INTO local_thread_catalog_sync_state VALUES ('local',1); CREATE TABLE local_thread_catalog(host_id TEXT,thread_id TEXT,display_title TEXT,source_kind TEXT,source_recency_at REAL,source_created_at REAL,missing_candidate INTEGER);")
            connection.execute("INSERT INTO local_thread_catalog VALUES ('local','deleted','deleted','vscode',0,0,1)")
            connection.commit()
            connection.close()
            data = chatgpt.local_data(root)
            self.assertEqual([item["id"] for item in data["projects"][0]["sessions"]], ["assigned"])
            self.assertEqual([item["id"] for item in data["recent"]], ["loose"])
            self.assertFalse(data["projects"][0]["sessions"][0]["movable"])

    def test_project_only_the_database_knows_stays_in_recent_like_the_app(self):
        with tempfile.TemporaryDirectory(prefix="dm-dbonly-") as directory:
            root = Path(directory)
            (root / "sessions").mkdir()
            state = {"local-projects": {"known": {"name": "已有", "rootPaths": ["D:\\known"]}}, "electron-persisted-atom-state": {}}
            (root / ".codex-global-state.json").write_text(json.dumps(state), encoding="utf-8")
            connection = sqlite3.connect(root / "state_5.sqlite")
            connection.executescript("CREATE TABLE projects(id TEXT,name TEXT,position INTEGER); CREATE TABLE project_roots(project_id TEXT,path TEXT,position INTEGER); CREATE TABLE threads(id TEXT,source TEXT,thread_source TEXT,cwd TEXT,title TEXT,name TEXT,recency_at_ms INTEGER,archived INTEGER,rollout_path TEXT,created_at_ms INTEGER DEFAULT 0,project_id TEXT,originator TEXT);")
            connection.execute("INSERT INTO projects VALUES('db-only','导入的文件夹',5)")
            connection.execute("INSERT INTO project_roots VALUES('db-only','D:\\imported',0)")
            for thread_id, cwd, project_id in (("imported", "D:\\imported", "db-only"), ("inside", "D:\\known", None)):
                connection.execute("INSERT INTO threads(id,source,thread_source,cwd,title,name,recency_at_ms,archived,rollout_path,project_id,originator) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (thread_id, "vscode", "user", cwd, thread_id, thread_id, STAMP, 0, "", project_id, "codex_work_desktop"))
            connection.commit()
            connection.close()
            data = chatgpt.local_data(root)
            self.assertEqual([item["title"] for item in data["projects"]], ["已有"])
            self.assertEqual([item["id"] for item in data["projects"][0]["sessions"]], ["inside"])
            self.assertEqual([item["id"] for item in data["recent"]], ["imported"])

    def test_native_extended_unc_and_case_normalization(self):
        self.assertEqual(chatgpt._norm("\\\\?\\D:\\Project\\"), chatgpt._norm("d:/project"))
        self.assertEqual(chatgpt._norm("\\\\?\\UNC\\server\\share"), chatgpt._norm("\\\\server\\share"))

    def test_account_selects_current_sidebar_not_previous_account(self):
        with tempfile.TemporaryDirectory(prefix="dm-account-test-") as directory:
            root = Path(directory)
            (root / "auth.json").write_text(json.dumps({"tokens": {"account_id": "current"}}), encoding="utf-8")
            atoms = {"chatgpt-sidebar-state-v2": {"previous": {"projects": ["wrong"]}, "current": {"projects": ["right"]}}}
            (root / ".codex-global-state.json").write_text(json.dumps({"electron-persisted-atom-state": atoms}), encoding="utf-8")
            self.assertEqual(chatgpt.native_state(root)[2]["projects"], ["right"])


if __name__ == "__main__":
    unittest.main()
