"""Repeatable source validation; this never pretends to be a Mac native-package test."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint():
    sources={}
    paths=[]
    for parent in ('macos','dialog-mover/core','dialog-mover/ui','auto-resume/src'):
        paths.extend((ROOT/parent).rglob('*'))
    paths.extend((ROOT/'dialog-mover').glob('test_*.py'))
    paths.extend(ROOT/'dialog-mover'/name for name in ('main.py','memory_service.py'))
    paths.extend((ROOT/'auto-resume/tests').glob('test_*.py'))
    paths.extend(ROOT/'workspace'/name for name in ('ResetNewsService.cs','ResetNewsDiscovery.cs','ResetNewsPresentation.cs','ResetCalendarModel.cs'))
    paths.append(ROOT/'workspace/assets/whats-new.json')
    paths.extend(ROOT/'dialog-mover'/name for name in ('requirements.txt','requirements-dev.txt','对话搬家.spec'))
    paths.extend(ROOT/'scripts'/name for name in ('check_macos_parity.py','package_macos.py','prepare_macos.py',
        'stage_macos_release.py','verify_macos_release.py','package_macos_development.py'))
    paths.extend(ROOT/'.github/workflows'/name for name in ('check.yml','macos.yml'))
    for path in sorted(paths):
        if path.is_file() and path.suffix in {'.py','.js','.css','.html','.cs','.csproj','.spec','.txt','.yml','.json'} and not any(part in {'bin','obj','__pycache__'} for part in path.relative_to(ROOT).parts):
            sources[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return sources


def run(report: Path, ui: bool = False):
    work = report.parent
    work.mkdir(parents=True, exist_ok=True)
    results = []
    initial_sources=fingerprint()
    def check(name, command, directory=ROOT, environment=None):
        print(name, flush=True)
        log = work / (name + '.log')
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT,
                env={**os.environ, 'PYTHONUTF8':'1', **(environment or {})}, timeout=600,
                creationflags=0x08000000 if sys.platform=='win32' else 0)
        output=log.read_text(encoding='utf-8',errors='replace')
        count=re.search(r'Ran (\d+) tests?',output)
        skipped=re.search(r'skipped=(\d+)',output)
        results.append({'name':name,'passed':result.returncode==0,'tests':int(count[1]) if count else None,
                        'skipped':int(skipped[1]) if skipped else 0,'log':log.name})
        if result.returncode: raise RuntimeError('Check failed: '+name)
    try:
        check('build-shared-reset',['dotnet','build','macos/ResetBridge/ResetBridge.csproj','-c','Release','--nologo'])
        shared=work/'shared-reset-rules.json'
        check('shared-reset-rules',['dotnet',str(ROOT/'macos/ResetBridge/bin/Release/net8.0/AI.First.ResetBridge.dll'),'--self-test','--report',str(shared)])
        value=json.loads(shared.read_text(encoding='utf-8'))
        if value.get('passed') is not True or not value.get('checks') or any(c.get('passed') is not True for c in value['checks']):
            raise RuntimeError('Shared rule report did not pass')
        results[-1]['tests']=len(value['checks'])
        check('shared-and-mac-backend',[sys.executable,'-m','unittest',
            'test_memory','test_codex_sources','test_codex_compressed','test_chatgpt','test_close_safety','test_copilot_import','test_copilot_refresh','test_macos_copilot_refresh',
            'test_codex_history','test_macos','test_macos_updater','test_macos_resume','test_macos_reset','test_macos_memory',
            'test_macos_parity_release','test_macos_history','test_release_highlights','-v'],ROOT/'dialog-mover')
        check('resume-safety',[sys.executable,'-m','unittest','discover','-s','tests','-v'],ROOT/'auto-resume',{'PYTHONPATH':'src'})
        if ui:
            check('shared-and-mac-ui',[sys.executable,'-m','unittest','test_memory_ui','test_codex_sources_ui','test_agent_icons',
                'test_import_ui','test_ui_polish','test_macos_ui','test_macos_resume_ui','test_macos_reset_ui','test_release_highlights_ui','-v'],ROOT/'dialog-mover')
        if fingerprint() != initial_sources: raise RuntimeError('Sources changed during checks')
        failure=None
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        failure=type(error).__name__
    passed=failure is None and all(item['passed'] for item in results)
    # Passing source tests are not an assertion that every user-facing Mac flow
    # is implemented. This explicit gap was found by the functional recheck.
    parity_gaps = [{'feature':'copilotDesktopAutoRefresh',
        'detail':'The Mac adapter only accepts explicit labelled native reload commands with task/draft/identity guards. The signed-out official runner cannot verify the logged-in command or resulting sidebar; this must still be checked on an initialized Mac client.'}]
    report.write_text(json.dumps({'passed':passed,'checks':results,'errorType':failure,'host':platform.system(),
        'functionalParityComplete':False,'parityGaps':parity_gaps,
        'nativeMacVerified':False,'uiChecked':ui,'modelRequests':0,'syntheticOnly':True,'sourceSha256':initial_sources,
        'scope':'Shared rules, source safety and optional browser UI; real Cocoa, launchd and Mac DMG checks remain separate'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':passed,'tests':sum(item['tests'] or 0 for item in results),'nativeMacVerified':False}),flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/macos-parity-source/report.json')
    parser.add_argument('--ui',action='store_true')
    arguments=parser.parse_args()
    raise SystemExit(run(arguments.report.resolve(),arguments.ui))
