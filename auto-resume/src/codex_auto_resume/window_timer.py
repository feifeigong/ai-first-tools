"""One short ephemeral turn per observed five-hour cycle. Fail closed on ambiguity."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .automation import permitted
from .quota import weekly_window

FORMAT = 'ai-first-window-timer-v1'
STATES = {'waiting', 'started', 'normal-use', 'pending', 'unconfirmed', 'unavailable', 'quota-blocked', 'activity', 'error'}


def _load(directory):
    path = directory / 'window-timer.json'
    if not path.exists():
        return {'format': FORMAT, 'status': 'waiting', 'attemptedCycle': '', 'observedResetAt': 0, 'nextResetAt': 0, 'attemptAt': 0}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError('Invalid timer state')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if (not isinstance(value, dict) or set(value) != {'format','status','attemptedCycle','observedResetAt','nextResetAt','attemptAt'}
            or value['format'] != FORMAT or value['status'] not in STATES or not isinstance(value['attemptedCycle'], str)
            or any(type(value[k]) not in (float, int) or not math.isfinite(value[k]) or not 0 <= value[k] <= 4102444800
                   for k in ('observedResetAt','nextResetAt','attemptAt'))):
        raise ValueError('Invalid timer state')
    return value


def _save(directory, value):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'window-timer.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf8')
    temporary.replace(path)


def timer_summary(directory):
    try:
        value = _load(directory)
        return {'timerStatus': value['status'], 'nextResetAt': value['nextResetAt']}
    except (OSError, ValueError):
        return {'timerStatus': 'error', 'nextResetAt': 0}


def _usable(snapshot):
    if snapshot is None or snapshot.source != 'app-server' or snapshot.ambiguous_bucket or snapshot.limit_id != 'codex':
        return False
    primary = snapshot.primary
    weekly = weekly_window(snapshot)
    return bool(primary and primary.window_minutes == 300 and primary.used_percent is not None
        and math.isfinite(primary.used_percent) and 0 <= primary.used_percent < 100
        and not snapshot.rate_limit_reached_type and not snapshot.spend_control_reached
        and snapshot.ordinary_usage_allowed is not False
        and weekly is not None and weekly.window_minutes == 10080 and weekly.used_percent is not None
        and math.isfinite(weekly.used_percent) and 0 <= weekly.used_percent < 100)


def tick_timer(cfg, reader, snapshot, now, *, activity=False, should_stop=lambda: False):
    directory = cfg.resolved_state_dir()
    if not cfg.auto_start_five_hour or not permitted(cfg, 'auto_start_five_hour') or should_stop():
        return
    try:
        state = _load(directory)
    except (OSError, ValueError):
        return  # Never erase an uncertain write-ahead marker and send again.
    def note(status):
        state['status'] = status
        _save(directory, state)
    if activity:
        note('activity')
        return
    if snapshot is None or snapshot.source != 'app-server':
        note('unavailable')
        return
    primary = snapshot.primary
    if primary is None or primary.window_minutes != 300 or snapshot.ambiguous_bucket or snapshot.limit_id != 'codex':
        note('unavailable')
        return
    reset = primary.resets_at or 0
    if not _usable(snapshot):
        note('quota-blocked')
        return
    if reset > now:
        verified = state['status'] == 'started' and state['nextResetAt'] == reset
        state['observedResetAt'] = reset
        state['nextResetAt'] = reset
        # A future official window already exists: no artificial request needed.
        note('started' if verified
             else 'normal-use' if (primary.used_percent or 0) > 0 else 'waiting')
        return
    cycle = str(reset or state['observedResetAt'] or 'initial')
    if not state['attemptedCycle'] and state['attemptAt'] and now - state['attemptAt'] < 600:
        return
    if state['attemptedCycle'] == cycle:
        if state['status'] == 'pending': note('unconfirmed')
        return
    if state['attemptedCycle'] and str(state['observedResetAt']) != cycle:
        note('unconfirmed')
        return  # A different stale timestamp is not evidence of another cycle.
    # Reread just before submission: a user or resumed task may have started it.
    fresh = reader.read(time.time())
    if should_stop() or not permitted(cfg, 'auto_start_five_hour'):
        return
    if not _usable(fresh):
        note('quota-blocked')
        return
    if (fresh.primary.resets_at or 0) > now:
        state['observedResetAt'] = fresh.primary.resets_at
        state['nextResetAt'] = fresh.primary.resets_at
        note('normal-use')
        return
    state.update(attemptedCycle=cycle, attemptAt=now, status='pending', nextResetAt=0,
                 observedResetAt=reset or state['observedResetAt'])
    _save(directory, state)  # Crash/timeout = no automatic duplicate of this cycle.
    if should_stop() or not permitted(cfg, 'auto_start_five_hour'):
        note('unconfirmed')
        return
    try:
        completed = reader.start_window(lambda: should_stop() or not permitted(cfg, 'auto_start_five_hour'))
        if completed is None:
            state['attemptedCycle'] = ''
            note('unavailable')
            return
        after = reader.read(time.time())
    except Exception:
        note('unconfirmed')
        return
    stamp = after.primary.resets_at if after and after.primary else 0
    if (completed and _usable(after) and stamp and now < stamp <= now + 18600
            and stamp > reset):
        state.update(observedResetAt=stamp, nextResetAt=stamp)
        note('started')
    else:
        note('unconfirmed')
