import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_auto_resume.config import AppConfig
from codex_auto_resume.window_request import request_args, start_window


class WindowRequestTests(unittest.TestCase):
    def test_args_require_ephemeral_read_only_subscription_and_empty_context(self):
        args=request_args(['synthetic-native'],'synthetic-empty','low')
        self.assertIn('--ephemeral',args);self.assertIn('--ignore-user-config',args)
        self.assertIn('read-only',args);self.assertIn('forced_login_method="chatgpt"',args)
        self.assertIn('features.shell_tool=false',args)
        self.assertIn('project_doc_max_bytes=0',args)
        self.assertNotIn('resume',args);self.assertNotIn('queue',args)

    def test_catalog_without_light_model_and_api_only_account_never_send(self):
        for account,models in (({'type':'apiKey'},{}),({'type':'chatgpt'},{'data':[]})):
            client=Mock();client.request.side_effect=[{'account':account},models]
            context=Mock();context.__enter__=Mock(return_value=client);context.__exit__=Mock(return_value=False)
            with patch('codex_auto_resume.window_request.resolve_codex_command',return_value=['synthetic']), \
                 patch('codex_auto_resume.window_request.AppServerClient',return_value=context), \
                 patch('codex_auto_resume.window_request.hidden_popen') as launch:
                self.assertFalse(start_window(AppConfig(),lambda:False))
            launch.assert_not_called()

    def test_plain_ok_can_complete_without_persisting_a_session_or_exposing_api_keys(self):
        client=Mock();client.request.side_effect=[{'account':{'type':'chatgpt'}},
            {'data':[{'model':'gpt-6-luna','hidden':False,'supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]}]
        client.read_rate_limits.return_value={'rateLimits':{'limitId':'codex','primary':{'usedPercent':0,'windowDurationMins':300,'resetsAt':9000},'secondary':{'usedPercent':20,'windowDurationMins':10080,'resetsAt':90000}}}
        context=Mock();context.__enter__=Mock(return_value=client);context.__exit__=Mock(return_value=False)
        process=Mock();process.returncode=0;process.poll.return_value=0
        process.communicate.return_value=(b'{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}\n{"type":"turn.completed"}\n',None)
        with tempfile.TemporaryDirectory(prefix='window-request-synthetic-') as temporary:
            cfg=AppConfig(codex_home=temporary)
            with patch('codex_auto_resume.window_request.resolve_codex_command',return_value=['synthetic']), \
                 patch('codex_auto_resume.window_request.AppServerClient',return_value=context), \
                 patch('codex_auto_resume.window_request.hidden_popen',return_value=process) as launch, \
                 patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic-never-used','CODEX_API_KEY':'synthetic-never-used'}):
                self.assertTrue(start_window(cfg,lambda:False))
                self.assertNotIn('OPENAI_API_KEY',launch.call_args.kwargs['env'])
                self.assertNotIn('CODEX_API_KEY',launch.call_args.kwargs['env'])
                self.assertEqual(list(Path(temporary).iterdir()),[])
        process.terminate.assert_not_called()
