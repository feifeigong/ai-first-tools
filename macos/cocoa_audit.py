"""Navigation diagnostics for isolated frozen-app audits only; never record URLs."""
from __future__ import annotations


def observe_navigation(window):
    from objc import super as objc_super
    from webview.platforms.cocoa import BrowserView

    window._ai_first_navigation = {"installed": False, "events": []}

    def note(view, event, error=None):
        state = view.pywebview_window._ai_first_navigation
        state["events"].append(event)
        if error is not None:
            state["failure"] = {"domain": str(error.domain()), "code": int(error.code())}

    class AIFirstAuditNavigationDelegate(BrowserView.BrowserDelegate):
        def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, handler):
            note(view, "policy")
            try:
                objc_super(AIFirstAuditNavigationDelegate, self).webView_decidePolicyForNavigationAction_decisionHandler_(view, action, handler)
                note(view, "policyReturned")
            except Exception as error:
                view.pywebview_window._ai_first_navigation["policyError"] = type(error).__name__
                raise

        def webView_didStartProvisionalNavigation_(self, view, navigation):
            note(view, "started")

        def webView_didCommitNavigation_(self, view, navigation):
            note(view, "committed")

        def webView_didFinishNavigation_(self, view, navigation):
            note(view, "finished")
            objc_super(AIFirstAuditNavigationDelegate, self).webView_didFinishNavigation_(view, navigation)

        def webView_didFailProvisionalNavigation_withError_(self, view, navigation, error):
            note(view, "provisionalFailure", error)

        def webView_didFailNavigation_withError_(self, view, navigation, error):
            note(view, "navigationFailure", error)

        def webViewWebContentProcessDidTerminate_(self, view):
            note(view, "contentProcessTerminated")

    host = BrowserView.instances[window.uid]
    host._ai_first_audit_delegate = AIFirstAuditNavigationDelegate.alloc().init()
    host.webview.setNavigationDelegate_(host._ai_first_audit_delegate)
    window._ai_first_navigation["installed"] = True
