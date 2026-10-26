from __future__ import annotations

import threading
from pathlib import Path

from . import memory_store, mover


def library() -> Path:
    return mover.data_dir() / "memory"


class PrepareJob:
    def __init__(self, source: str, sessions: list[dict]):
        self.source = source
        self.target = "memory"
        self.directory = ""
        self.finished = False
        self._lock = threading.Lock()
        self.items = [{"id": s["id"], "title": s.get("title", ""), "state": "waiting", "message": "等待保存历史"} for s in sessions]
        self.sessions = sessions
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            for index, session in enumerate(self.sessions):
                with self._lock: self.items[index].update(state="running", message="读取并保存完整历史…")
                try:
                    source = str(session.get("source") or self.source)
                    document = mover.export_document(source, session)
                    with self._lock: self.items[index]["message"] = "正在整理，方便以后查找…"
                    info = memory_store.ingest(library(), source, session["id"], document, str(session.get("title") or ""))
                    # The source's display title is metadata, not a replacement of its original body.
                    with self._lock:
                        self.items[index].update(state="ok", message="完整旧对话已保存", bundle=info["id"],
                            messages=info["messages"], characters=info["characters"], facts=info["facts"][:100], facts_total=len(info["facts"]))
                except Exception as error:
                    with self._lock:
                        self.items[index].update(state="failed", message=str(error) if isinstance(error, ValueError) else "这条对话暂时没能保存，请返回后重试；目标项目还没有改动。")
        finally:
            with self._lock: self.finished = True

    def snapshot(self):
        return mover.Job.snapshot(self)
