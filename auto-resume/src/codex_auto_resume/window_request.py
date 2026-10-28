"""A subscription-backed, ephemeral OK turn; never open an existing user thread."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .app_server import AppServerClient
from .paths import resolve_codex_command
from .procutil import hidden_popen

LIGHT_MODEL = 'gpt-6-luna'


def request_args(command, empty, effort):
    args = [*command, 'exec', '--ephemeral', '--ignore-user-config', '--skip-git-repo-check',
        '--model', LIGHT_MODEL, '--sandbox', 'read-only', '--json', '-C', empty]
    settings = {'model_provider':'openai', 'forced_login_method':'chatgpt',
        'project_doc_max_bytes':0, 'web_search':'disabled', 'skills.include_instructions':False,
        'model_reasoning_effort':effort, 'model_verbosity':'low', 'service_tier':'default', 'tools.update_plan':False,
        'tools.experimental_request_user_input':False}
    for key in ('shell_tool','unified_exec','plugins','apps','view_image','image_generation','multi_agent','js_repl','code_mode','token_budget','sleep_tool'):
        settings['features.'+key] = False
    for key,value in settings.items():
        args += ['-c',key+'='+json.dumps(value)]
    args.append('只回复 OK。不要调用工具、读取文件或执行其他操作。')
    return args


def _select_effort(command, env, should_stop):
    with AppServerClient(command, env=env, timeout=18) as client:
        account = client.request('account/read', {'refreshToken':False}).get('account')
        if not isinstance(account, dict) or account.get('type') != 'chatgpt' or should_stop():
            return None
        models = client.request('model/list', {'limit':100, 'includeHidden':False})
        selected = next((m for m in models.get('data', []) if m.get('model') == LIGHT_MODEL and m.get('hidden') is False), None)
        if selected is None or should_stop():
            return None
        efforts = {x.get('reasoningEffort') for x in selected.get('supportedReasoningEfforts', [])}
        effort = next((x for x in ('none', 'minimal', 'low') if x in efforts), None)
        from .quota import parse_quota_payload
        from .window_timer import _usable
        fresh = parse_quota_payload(client.read_rate_limits(include_credits=False), source='app-server')
        if not _usable(fresh) or (fresh.primary.resets_at or 0) > time.time() or should_stop():
            return None
        return effort


def start_window(cfg, should_stop) -> bool | None:
    env = os.environ.copy()
    env['CODEX_HOME'] = str(cfg.resolved_codex_home())
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'):
        env.pop(key, None)
    try:
        command = resolve_codex_command(cfg.codex_bin or None)
        effort = _select_effort(command, env, should_stop)
    except Exception:
        return None  # Preflight failed: definitely no model request was submitted.
    if effort is None or should_stop():
        return None
    with tempfile.TemporaryDirectory(prefix='ai-first-quota-empty-') as temporary:
        empty = str(Path(temporary).resolve())
        if should_stop():
            return None
        proc = hidden_popen(request_args(command, empty, effort), cwd=empty, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output = b''
        deadline = time.monotonic() + 40
        try:
            while time.monotonic() < deadline and not should_stop():
                try:
                    output,_ = proc.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            else:
                return False
            if proc.returncode != 0 or len(output) > 65536:
                return False
            events = [json.loads(line) for line in output.decode('utf8').splitlines() if line.strip()]
            items = [e['item'] for e in events if e.get('type') == 'item.completed' and isinstance(e.get('item'),dict)]
            if any(i.get('type') not in {'agent_message','reasoning'} for i in items):
                return False
            return any(e.get('type') == 'turn.completed' for e in events) and any(
                i.get('type') == 'agent_message' and i.get('text','').strip().strip('.。') == 'OK' for i in items)
        finally:
            if proc.poll() is None:
                # Only our own short empty ephemeral request can be stopped here.
                proc.terminate()
                try: proc.wait(timeout=3)
                except subprocess.TimeoutExpired: proc.kill();proc.wait(timeout=3)
