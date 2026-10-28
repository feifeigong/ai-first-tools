"""Local UI policy only. No account, chat or model access in this module."""
from __future__ import annotations

import json
from pathlib import Path

from .config import AppConfig, config_path
from .paths import default_state_dir

OPERATIONS = {'status', 'resume-on', 'resume-off', 'credit-on', 'credit-off', 'timer-on', 'timer-off'}
FIELDS = {'enabled', 'auto_redeem_weekly_reset', 'auto_start_five_hour'}


def read_policy(directory: Path | None = None) -> dict:
    target = config_path(directory)
    if not target.exists():
        return {}
    if target.is_symlink() or not target.is_file() or target.stat().st_size > 1024 * 1024:
        raise ValueError('Invalid automation settings')
    value = json.loads(target.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or any(k in value and type(value[k]) is not bool for k in FIELDS):
        raise ValueError('Invalid automation settings')
    return value


def permitted(cfg: AppConfig, field: str) -> bool:
    """Recheck switches at the irreversible boundary, including during quota I/O."""
    try:
        return read_policy(cfg.resolved_state_dir()).get(field, getattr(cfg, field)) is True
    except (OSError, ValueError):
        return False


def control(operation: str, directory: Path | None = None) -> dict:
    if operation not in OPERATIONS:
        raise ValueError('Unknown automation operation')
    directory = directory or default_state_dir()
    raw = read_policy(directory)
    if operation != 'status':
        field = {'resume': 'enabled', 'credit': 'auto_redeem_weekly_reset', 'timer': 'auto_start_five_hour'}[operation.split('-')[0]]
        raw[field] = operation.endswith('-on')
        # First opt-in must never implicitly enable spending or the new timer.
        raw.setdefault('auto_redeem_weekly_reset', False)
        raw.setdefault('auto_start_five_hour', False)
        directory.mkdir(parents=True, exist_ok=True)
        target = config_path(directory)
        temporary = target.with_suffix('.policy.tmp')
        temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        temporary.replace(target)
    from .window_timer import timer_summary
    return {'resumeEnabled': raw.get('enabled', True),
            'autoRedeem': raw.get('auto_redeem_weekly_reset', False),
            'autoStartWindow': raw.get('auto_start_five_hour', False), **timer_summary(directory)}


def write_control(operation: str, report: Path) -> int:
    try:
        result = {'ok': True, **control(operation)}
    except (OSError, ValueError):
        result = {'ok': False, 'error': '自动化设置暂时无法读取，原设置已保留。'}
    report.write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')
    return 0 if result['ok'] else 1
