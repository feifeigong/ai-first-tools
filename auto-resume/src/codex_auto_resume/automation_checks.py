"""Offline checks shared by the real Windows/Mac frozen-runtime release gates."""
from __future__ import annotations

import tempfile
from pathlib import Path


def run() -> dict[str, bool]:
    from .automation import control
    from .config import AppConfig
    from .quota import QuotaSnapshot, QuotaWindow
    from .window_request import request_args
    from .window_timer import tick_timer, timer_summary
    with tempfile.TemporaryDirectory(prefix='automation-frozen-synthetic-') as temporary:
        root=Path(temporary)
        assert not AppConfig().auto_start_five_hour and not AppConfig().auto_redeem_weekly_reset
        control('timer-on',root);control('resume-on',root);control('credit-on',root);control('resume-off',root)
        policy=control('status',root)
        assert policy['autoStartWindow'] and not policy['resumeEnabled'] and not policy['autoRedeem']
        assert not control('resume-on',root)['autoRedeem']
        control('resume-off',root)
        before=QuotaSnapshot(primary=QuotaWindow(0,9000,300),secondary=QuotaWindow(20,90000,10080),limit_id='codex',source='app-server')
        after=QuotaSnapshot(primary=QuotaWindow(1,28000,300),secondary=QuotaWindow(20,90000,10080),limit_id='codex',source='app-server')
        class Reader:
            sends=0
            def read(self, now): return before if self.sends==0 else after
            def start_window(self, stop): self.sends+=1;return not stop()
        reader=Reader()
        cfg=AppConfig(enabled=False,auto_start_five_hour=True,state_dir=str(root))
        tick_timer(cfg,reader,before,10000)
        assert timer_summary(root)=={'timerStatus':'started','nextResetAt':28000}
        tick_timer(cfg,reader,before,10030)
        assert reader.sends==1
        args=request_args(['synthetic'],str(root),'low')
        assert all(x in args for x in ('--ephemeral','--ignore-user-config','read-only','forced_login_method="chatgpt"','features.shell_tool=false'))
        assert 'resume' not in args and 'queue' not in args
    return {'independentAutomationPolicy':True,'ephemeralTimerWriteAhead':True,'ephemeralRequestSafety':True}
