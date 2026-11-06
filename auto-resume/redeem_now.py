"""立即用掉一张重置卡（供工具箱的「定时用卡」调用）。

和 redeem_at_5am.py 的区别：这里不做基准卡数校验，是一次明确的、用户主动安排的消费。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from codex_auto_resume.config import load_config          # noqa: E402
from codex_auto_resume.daemon import LiveQuota           # noqa: E402
from codex_auto_resume.quota import parse_quota_payload  # noqa: E402

LOG = ROOT / "redeem-scheduled.log"


def log(message: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    try:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def main() -> int:
    quota = LiveQuota(load_config())
    try:
        payload = quota._live_payload()
        snapshot = parse_quota_payload(payload, source="app-server", fetched_at=time.time())
        if snapshot is None:
            log("失败：读不到额度快照")
            return 1
        count = snapshot.reset_credit_count
        log(f"可用重置卡 {count}")
        if not count:
            log("失败：没有可用的重置卡")
            return 1
        result = quota.client.consume_reset_credit(None)
        log("已用卡：" + json.dumps(result, ensure_ascii=False)[:400])
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"失败：{exc}")
        return 1
    finally:
        try:
            quota.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
