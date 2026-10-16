"""Audit the bundled import component using synthetic records and isolated stores."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from core import mover, sources

ROOT = Path(__file__).resolve().parent


def isolated_env(base: Path) -> dict:
    env = os.environ.copy()
    locations = {
        "HOME": base / "home",
        "USERPROFILE": base / "home",
        "APPDATA": base / "roaming",
        "LOCALAPPDATA": base / "local",
        "XDG_DATA_HOME": base / "data",
        "XDG_CONFIG_HOME": base / "config",
        "XDG_STATE_HOME": base / "state",
        "XDG_CACHE_HOME": base / "cache",
        "CODEX_HOME": base / "codex",
        "COPILOT_HOME": base / "copilot",
        "CLAUDE_CONFIG_DIR": base / "claude",
        "WORKBUDDY_DIR": base / "workbuddy",
        "WORKBUDDY_AI_DIR": base / "workbuddy-ai",
        "QWENWORK_DIR": base / "home" / ".qwenworkcn",
        "DOUBAO_WORK_DIR": base / "doubao",
        "ANTIGRAVITY_DIR": base / "antigravity",
        "COWORK_SESSIONS_DIR": base / "cowork",
        "CURSOR_DESKTOP_USER_DIR": base / "cursor-user",
        "HERMES_HOME": base / "hermes",
    }
    for name, path in locations.items():
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    env["OPENCODE_DB"] = str(locations["XDG_DATA_HOME"] / "opencode" / "opencode.db")
    env["OPENCODE_DISABLE_DEFAULT_PLUGINS"] = "1"
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["NO_COLOR"] = "1"
    env.pop("TXCRIPT_CACHE", None)
    return env


def run(args: list[str], env: dict, base: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(ROOT / "bin" / "txcript.exe"), *args],
        env=env,
        cwd=base,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=mover.CREATE_NO_WINDOW,
    )


def detail(result: subprocess.CompletedProcess, base: Path) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.stderr or result.stdout).strip()
    return text.replace(str(base), "<temporary>")[-1000:]


def main() -> None:
    report = {
        "scope": "synthetic transcript; temporary stores; no model prompts or live imports",
        "gui_targets": list(mover.TARGETS),
        "targets": {},
    }
    bundled = ROOT / "dist" / "对话搬家" / "_internal" / "bin" / "txcript.exe"
    report["packaged_component_matches_source"] = bundled.is_file() and (
        hashlib.sha256(bundled.read_bytes()).digest()
        == hashlib.sha256((ROOT / "bin" / "txcript.exe").read_bytes()).digest()
    )
    snapshots = sources._doubao_snapshots()
    cowork_root = sources._cowork_root()
    account_count = 0
    if cowork_root is not None and cowork_root.is_dir():
        for organization in cowork_root.iterdir():
            try:
                uuid.UUID(organization.name)
            except ValueError:
                continue
            for account in organization.iterdir() if organization.is_dir() else []:
                try:
                    uuid.UUID(account.name)
                except ValueError:
                    continue
                account_count += int(account.is_dir())
    report["cowork_initialized_accounts_on_this_pc"] = account_count
    with tempfile.TemporaryDirectory(prefix="dm-import-audit-") as temporary:
        base = Path(temporary)
        env = isolated_env(base)
        working = base / "destination"
        working.mkdir()
        session_id = str(uuid.uuid4())
        texts = ["Synthetic import audit question", "Synthetic import audit answer"]
        document = base / "input.json"
        document.write_text(json.dumps({
            "id": session_id,
            "title": "Import capability audit",
            "cwd": str(working),
            "messages": [
                {"role": "user", "content": texts[0]},
                {"role": "assistant", "content": texts[1]},
            ],
        }), encoding="utf-8")
        roots = {
            "cursor_desktop": Path(env["CURSOR_DESKTOP_USER_DIR"]),
            "workbuddy": Path(env["WORKBUDDY_DIR"]),
            "workbuddy_ai": Path(env["WORKBUDDY_AI_DIR"]),
            "qwen_work": Path(env["QWENWORK_DIR"]),
            "doubao_work": Path(env["DOUBAO_WORK_DIR"]),
            "claude_code": Path(env["CLAUDE_CONFIG_DIR"]) / "projects",
            "cowork": Path(env["COWORK_SESSIONS_DIR"]),
            "antigravity": Path(env["ANTIGRAVITY_DIR"]),
            "cursor": Path(env["USERPROFILE"]) / ".cursor" / "chats",
            "grok": Path(env["USERPROFILE"]) / ".grok" / "sessions",
            "codex": Path(env["CODEX_HOME"]) / "sessions",
        }
        empty_cowork = run([
            "continue", str(document), "--with", "cowork", "--out", str(roots["cowork"]), "--no-resume",
        ], env, base)
        report["cowork_without_initialized_account"] = {
            "exit": empty_cowork.returncode,
            "detail": detail(empty_cowork, base),
        }
        account = roots["cowork"] / str(uuid.uuid4()) / str(uuid.uuid4())
        account.mkdir(parents=True)
        for target, root in roots.items():
            root.mkdir(parents=True, exist_ok=True)
            result = run([
                "continue", str(document), "--with", target, "--out", str(root), "--no-resume",
            ], env, base)
            entry = {"file_write_exit": result.returncode}
            if result.returncode == 0:
                saved_id = f"local_{session_id}" if target == "cowork" else session_id
                exported = base / f"{target}-roundtrip.json"
                readback = run(["export", saved_id, "--from", target, "--out", str(exported)], env, base)
                entry["readback_exit"] = readback.returncode
                returned = json.loads(exported.read_text(encoding="utf-8")) if readback.returncode == 0 else {}
                entry["text_roundtrip"] = readback.returncode == 0 and all(
                    text in json.dumps(returned) for text in texts
                )
                entry["title_preserved"] = returned.get("title") == "Import capability audit"
                entry["directory_preserved"] = mover.norm(returned.get("cwd") or "") == mover.norm(str(working))
                if readback.returncode != 0:
                    entry["readback_detail"] = detail(readback, base)
            else:
                entry["detail"] = detail(result, base)
            report["targets"][target] = entry
            print(target, json.dumps(entry, ensure_ascii=False), flush=True)

        qwen_database = base / "qwen-agents.db"
        original = sources.read_db(sources._qwen_db())
        copied = sqlite3.connect(qwen_database)
        original.backup(copied)
        original.close()
        copied.close()
        with patch.object(sources, "_qwen_db", return_value=qwen_database), patch.object(
            sources, "home", return_value=Path(env["USERPROFILE"]),
        ):
            listed_ids = {session["id"] for group in sources.qwen_groups() for session in group["sessions"]}
        report["qwen_written_transcript_is_in_desktop_list"] = session_id in listed_ids
        report["qwen_writer_created_desktop_index"] = any(roots["qwen_work"].rglob("agents.db"))
        doubao_base = base / "doubao-profile"
        sessions = doubao_base / ".doubaowork" / "agent_mode" / "workspace" / ".sessions"
        sessions.mkdir(parents=True)
        (sessions / session_id).mkdir()
        with patch.object(sources, "_doubao_base", return_value=doubao_base), patch.object(
            sources, "_doubao_snapshots", return_value=snapshots,
        ):
            listed_ids = {session["id"] for group in sources.doubao_groups() for session in group["sessions"]}
        report["doubao_written_trajectory_is_in_desktop_list"] = session_id in listed_ids
        report["doubao_writer_created_desktop_list"] = any(roots["doubao_work"].rglob("*.leveldb"))

        for target in ("chatgpt", "claude_chat", "hermes", "cowork_remote", "opencode"):
            result = run([
                "continue", str(document), "--with", target, "--out", str(base / target), "--no-resume",
            ], env, base)
            entry = {"file_write_exit": result.returncode, "detail": detail(result, base)}
            report["targets"][target] = entry
            print(target, json.dumps(entry, ensure_ascii=False), flush=True)

        result = run(["continue", str(document), "--with", "opencode", "--no-resume"], env, base)
        entry = {"isolated_native_import_exit": result.returncode}
        if result.returncode == 0:
            database = Path(env["OPENCODE_DB"])
            if database.is_file():
                con = sources.read_db(database)
                saved = con.execute("SELECT id FROM session").fetchone()
                con.close()
                exported = base / "opencode-roundtrip.json"
                readback = run(["export", saved[0], "--from", "opencode", "--out", str(exported)], env, base)
                entry["text_roundtrip"] = readback.returncode == 0 and all(
                    text in exported.read_text(encoding="utf-8") for text in texts
                )
            else:
                entry["expected_isolated_database_found"] = False
        else:
            entry["detail"] = detail(result, base)
        report["opencode_native_import"] = entry
        print("opencode_native_import", json.dumps(entry, ensure_ascii=False), flush=True)
    output = ROOT / "_import_audit.json"
    validations = {
        "packaged_component_matches": report["packaged_component_matches_source"],
        "writable_formats_roundtrip": all(
            entry["file_write_exit"] == 0 and entry.get("text_roundtrip")
            for target, entry in report["targets"].items() if target in roots
        ),
        "read_only_sources_rejected": all(
            report["targets"][target]["file_write_exit"] != 0
            for target in ("chatgpt", "claude_chat", "hermes", "cowork_remote")
        ),
        "opencode_isolated_native_import": report["opencode_native_import"].get("isolated_native_import_exit") == 0
        and report["opencode_native_import"].get("text_roundtrip"),
        "qwen_transcript_does_not_register_desktop_chat": not report["qwen_written_transcript_is_in_desktop_list"],
        "doubao_trajectory_does_not_register_desktop_chat": not report["doubao_written_trajectory_is_in_desktop_list"],
        "cowork_requires_account_tree": report["cowork_without_initialized_account"]["exit"] != 0,
    }
    report["validations"] = validations
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("report", output)
    if not all(validations.values()):
        raise SystemExit("Import audit did not match the documented capability matrix.")


if __name__ == "__main__":
    main()
