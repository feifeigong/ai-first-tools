"""Real Windows installer audit, restricted to an empty GitHub runner profile."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'AI First Auto Resume'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stage', choices=('start','reinstall','uninstall'), default='start')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Refuse to change a non-CI user installation or startup preference')
    package = args.package.resolve()
    expected = Path(os.environ['LOCALAPPDATA']) / 'Programs/AI First Tools'
    if package != expected.resolve():
        raise RuntimeError('Installer audit target must be the clean runner installation')
    shell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    binary = package / 'tools/auto-resume/AI一手续跑后台.exe'
    env = os.environ.copy()
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    env.pop('PYTHONPATH',None)
    env.pop('CODEX_BIN',None)
    def action(name):
        result = subprocess.run([str(shell),'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(package / 'assets/auto-resume-control.ps1'),'-Action',name],env=env,capture_output=True,timeout=50)
        value = json.loads(result.stdout.decode('utf-8-sig').strip())
        if result.returncode or value.get('error'):
            raise RuntimeError('Packaged controller operation failed: '+name)
        return value
    def require(value):
        if not value:
            raise AssertionError('Bundled runtime audit assertion failed')
    def read_run():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
                return winreg.QueryValueEx(key,RUN_NAME)[0]
        except FileNotFoundError:
            return None
    checks = {}
    if args.stage == 'start':
        require(read_run() is None)
        initial = action('status')
        require(initial['installed'] and not initial['running'] and not initial['autostart'])
        state = Path(env['LOCALAPPDATA']) / 'vibcoding/codex-auto-resume'
        require(not (state / 'config.json').exists())
        state.mkdir(parents=True,exist_ok=True)
        synthetic_home = Path(tempfile.mkdtemp(prefix='ai-first-installer-codex-'))
        (state / 'config.json').write_text(json.dumps({'enabled':False,'codex_home':str(synthetic_home),'state_dir':str(state),'poll_seconds':5,'auto_redeem_weekly_reset':False}),encoding='utf-8')
        require(action('start')['watcherCount'] == 1)
        require(action('start')['watcherCount'] == 1)
        checks['singlePackagedWatcherWithoutExternalRuntime'] = True
        value = action('autostart-on')
        require(value['running'] and value['autostart'] and read_run() == '"'+str(binary)+'" watch --quiet')
        require(action('autostart-off')['running'])
        stopped = action('stop')
        require(not stopped['running'] and not stopped['autostart'] and read_run() is None)
        time.sleep(2)
        require(not action('status')['running'])
        probe_env = env.copy()
        probe_env.pop('AI_FIRST_MANUAL_WATCH',None)
        require(subprocess.run([str(binary),'watch','--quiet'],env=probe_env,timeout=10).returncode == 0)
        require(not action('status')['running'])
        checks['stopBlocksStartupRelaunch'] = True
        require(action('start')['running'])
        before = action('autostart-on')
        helper = package / 'assets/auto-resume-bundled.ps1'
        for operation in ('prepare-update','finish-update'):
            result = subprocess.run([str(shell),'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(helper),'-Action',operation],env=env,capture_output=True,timeout=50)
            value = json.loads(result.stdout.decode('utf-8-sig'))
            require(result.returncode == 0 and not value.get('error'))
            require(value['running'] == (operation == 'finish-update'))
        require(before['autostart'] and action('status')['autostart'])
        checks['upgradeHandoffPreservesRunningAndStartup'] = True
    elif args.stage == 'reinstall':
        value = action('status')
        require(value['running'] and value['autostart'] and value['watcherCount'] == 1)
        checks['realReinstallRestoredBackground'] = True
    else:
        if binary.exists() or read_run() is not None:
            raise AssertionError('Uninstall incomplete: ' + json.dumps({'packagedExecutablePresent': binary.exists(), 'startupEntryPresent': read_run() is not None}))
        query = "@(Get-CimInstance Win32_Process -Filter \"Name='AI一手续跑后台.exe'\" | Where-Object { $_.ExecutablePath -eq '" + str(binary).replace("'","''") + "' }).Count"
        result = subprocess.run([str(shell),'-NoProfile','-NonInteractive','-Command',query],capture_output=True,timeout=30)
        require(result.returncode == 0 and result.stdout.strip() == b'0')
        checks['realUninstallRemovedBackgroundAndStartup'] = True
    existing = json.loads(args.report.read_text(encoding='utf-8')) if args.report.exists() else {'passed':True,'checks':{},'scope':'clean Windows GitHub runner; synthetic disabled workload, no model or user account'}
    existing['checks'].update(checks)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(existing,indent=2),encoding='utf-8')
    print(json.dumps(existing))


if __name__ == '__main__':
    main()
