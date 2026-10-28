from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import default_codex_home, default_state_dir, tool_root

DEFAULT_PROMPT = (
    "继续完成上一轮因 usage limit 中断的任务。"
    "先检查当前工作区状态，避免重复执行已经完成的修改或命令，然后从未完成步骤继续。"
    "保留原有任务范围，不要停下来等人确认。"
)
LEGACY_PROMPT = (
    "继续完成上一轮因 usage limit 中断的任务。"
    "先检查当前工作区状态，避免重复执行已经完成的修改或命令，然后从未完成步骤继续。"
    "保留原有任务范围；需要我提供信息或审批时停下来询问。"
)


@dataclass
class AppConfig:
    enabled: bool = True
    auto_discover: bool = True
    lookback_hours: float = 36
    poll_seconds: float = 30
    reset_buffer_seconds: float = 45
    # 旧版把这个数当成一条对话的终身续跑次数，额度再回来也不会续。
    # 现在只表示同一轮中断最多自动续几次；新的一轮 usage limit 会再续。
    max_auto_windows: int = 1
    ready_used_percent: float = 99.0
    recovery_drop_percent: float = 20.0
    resume_prompt: str = DEFAULT_PROMPT
    skip_git_repo_check: bool = True
    prefer_queue_if_busy: bool = True
    extra_resume_args: list[str] = field(default_factory=list)
    auto_redeem_weekly_reset: bool = False
    auto_start_five_hour: bool = False
    reset_credit_cooldown_seconds: float = 600
    codex_home: str = ""
    codex_bin: str = ""
    state_dir: str = ""

    def resolved_codex_home(self) -> Path:
        return Path(self.codex_home).expanduser() if self.codex_home else default_codex_home()

    def resolved_state_dir(self) -> Path:
        return Path(self.state_dir).expanduser() if self.state_dir else default_state_dir()


def config_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    data: dict = {}
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
    known = {k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__}
    cfg = AppConfig(**known)
    if not cfg.codex_home:
        cfg.codex_home = str(default_codex_home())
    if not cfg.state_dir:
        cfg.state_dir = str(target.parent if path else default_state_dir())
    if cfg.resume_prompt.strip() == LEGACY_PROMPT:
        cfg.resume_prompt = DEFAULT_PROMPT
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path(cfg.resolved_state_dir())
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(cfg)
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    example = tool_root() / "config.example.json"
    if not getattr(sys, "frozen", False) and not example.exists():
        example.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
