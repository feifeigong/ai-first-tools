"""Export this dirty source snapshot locally for Mac continuation, never publish/install."""
from __future__ import annotations
import argparse
import hashlib
import json
import stat
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def package(output: Path, report: Path):
    if output.exists(): raise RuntimeError('Choose a fresh output ZIP; existing files are preserved')
    verification=json.loads(report.read_text(encoding='utf-8'))
    if verification.get('passed') is not True or verification.get('nativeMacVerified') is not False:
        raise RuntimeError('A passing source report with the correct native-validation boundary is required')
    for name, expected in verification['sourceSha256'].items():
        path=ROOT/name
        if not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Source changed after verification')
    names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode('utf-8').split('\0')
    mode_entries=subprocess.check_output(['git','ls-files','-s','-z'],cwd=ROOT).decode('utf-8').split('\0')
    executable={entry.split('\t',1)[1] for entry in mode_entries if entry.startswith('100755 ')}
    files={}
    forbidden_names={'auth.json','cookies.json','.env','tools.json','state.json','monitor-owner.json'}
    forbidden_suffixes={'.exe','.dll','.pdb','.dylib','.so','.pyd','.pyc','.db','.sqlite','.sqlite3','.log','.jsonl','.dmg','.zip','.tgz'}
    for name in sorted(set(names)):
        if not name: continue
        path=ROOT/name
        if not path.is_file(): continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT): raise RuntimeError('Source link is not permitted in the snapshot')
        if path.name.lower() in forbidden_names or path.suffix.lower() in forbidden_suffixes or path.name.startswith('.env.'):
            raise RuntimeError('Private/generated files must not enter the development snapshot: '+name)
        files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    for required in ('AGENTS.md','macos/ResetBridge/Program.cs','workspace/ResetNewsService.cs','dialog-mover/core/memory_deploy.py','txcript/Cargo.toml','docs/MACOS-WINDOWS-PARITY.md'):
        if required not in files: raise RuntimeError('Development snapshot is incomplete')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest={'kind':'uncommitted-macos-parity-development-snapshot','baseline':head,'createdAt':datetime.now(timezone.utc).isoformat(),
              'nativeMacVerified':False,'sourceValidationPassed':True,
              'functionalParityComplete':verification.get('functionalParityComplete',False),
              'parityGaps':verification.get('parityGaps',[]),'modelRequests':0,'files':files}
    introduction=('这是 Mac 同步的接续开发包，不是功能对等已经验收的 Mac 安装包。\n\n'
        '请解压到新的独立文件夹，保留已有项目和正式安装。打开 ai-first-tools/docs/MACOS-HANDOFF.md，'
        '把顶部的接续说明交给 Mac 上的 Codex，让它继续匹配芯片的构建和原生验证。\n\n'
        '完整原档/智能搬家、自动续跑与重置提醒的源码已大部分接入。复核发现 Copilot 自动刷新列表仍缺少 Mac 适配，智能搬家自动打开也受此影响；应优先补齐并实测。'
        '包内包含功能清单、源码校验清单和 Windows 合成验证报告。'
        '真实 Cocoa、系统通知、登录自启、目标客户端和 Mac 运行包仍须在 Mac 验收。\n'
        '不需要新 API Key；不要调用模型或用真实私有聊天测试。未经明确授权，不提交、推送或发布。\n')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in files:
            info=zipfile.ZipInfo('ai-first-tools/'+name)
            info.create_system=3
            info.external_attr=(stat.S_IFREG|(0o755 if name in executable else 0o644))<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,(ROOT/name).read_bytes())
        archive.writestr('ai-first-tools/DEVELOPMENT-SNAPSHOT.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        archive.writestr('先看这里.txt',introduction)
        archive.writestr('validation/windows-source-checks.json',report.read_bytes())
        preview=ROOT/'artifacts/development/macos-parity-ui/calendar-wide.png'
        if preview.is_file(): archive.writestr('validation/页面预览（Windows浏览器合成数据）.png',preview.read_bytes())
    with zipfile.ZipFile(output) as archive:
        for name,expected in files.items():
            if hashlib.sha256(archive.read('ai-first-tools/'+name)).hexdigest()!=expected:
                raise RuntimeError('Snapshot verification failed')
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('Source changed while exporting the snapshot')
    fingerprint=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256').write_text(fingerprint+'  '+output.name+'\n',encoding='utf-8')
    print(json.dumps({'created':True,'files':len(files),'bytes':output.stat().st_size,'sha256':fingerprint,'nativeMacVerified':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    arguments=parser.parse_args()
    package(arguments.output.resolve(),arguments.report.resolve())
