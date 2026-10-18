"""Native draft-guard audit against our own synthetic WebView, never Copilot."""
import json
import time
from pathlib import Path
import webview
from .copilot_refresh import _has_draft


def run(report: Path):
    window = webview.create_window('Synthetic composer guard audit', html='<div role="textbox" contenteditable="true" aria-label="Message">synthetic unsent draft</div>', width=450, height=200)
    result = {'passed': False, 'draftDetected': False, 'emptyAccepted': False}

    def check():
        try:
            # The packaging runner starts processes hidden. UIA can only audit
            # the synthetic composer after this test window is actually shown.
            window.show()
            window.restore()
            handle = window.native.Handle.ToInt64()
            deadline = time.monotonic() + 10
            while _has_draft(handle) is not True and time.monotonic() < deadline:
                time.sleep(.1)
            result['draftDetected'] = _has_draft(handle) is True
            window.evaluate_js('document.querySelector("[role=textbox]").textContent = ""')
            deadline = time.monotonic() + 5
            while _has_draft(handle) is not False and time.monotonic() < deadline:
                time.sleep(.1)
            result['emptyAccepted'] = _has_draft(handle) is False
            result['passed'] = result['draftDetected'] and result['emptyAccepted']
        finally:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result), encoding='utf-8')
            window.destroy()
    window.events.loaded += check
    webview.start()
    return 0 if result['passed'] else 1
