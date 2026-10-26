"""Build a fresh local mover preview; preserve the verified shell and other tools."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from collect_licenses import collect_python

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--base-package',type=Path,default=ROOT/'artifacts/memory-repeat-compatible-preview/package')
    parser.add_argument('--build-directory',type=Path,default=ROOT/'artifacts/codex-compatible-preview')
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        raise RuntimeError('Use a fresh independent output directory outside the checkout')
    work = args.build_directory.resolve()
    if not work.is_relative_to(ROOT/'artifacts'):
        raise RuntimeError('Build evidence must stay under the checkout artifacts directory')
    if work.exists(): raise RuntimeError('Preserve previous build evidence; choose a new build directory in the script')
    work.mkdir(parents=True)
    previous = args.base_package.resolve()
    if not (previous/'development-preview.json').is_file(): raise RuntimeError('Use an existing independent development preview as the base')
    def run(name,command,cwd=ROOT,timeout=300):
        print(name,flush=True)
        with (work/(name+'.log')).open('w',encoding='utf-8') as output:
            value = subprocess.run([str(p) for p in command],cwd=cwd,stdout=output,stderr=subprocess.STDOUT,
                timeout=timeout,env={**os.environ,'PYTHONUTF8':'1'},creationflags=0x08000000 if sys.platform=='win32' else 0)
        if value.returncode: raise RuntimeError('Failed: '+name)
    def sources():
        names = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard','--','dialog-mover'],cwd=ROOT).decode('utf-8').split('\0')
        return {name:sha(ROOT/name) for name in names if name and (ROOT/name).is_file()}
    source_hashes = sources()
    run('previous-package-check',[sys.executable,ROOT/'scripts/check_release.py','--package',previous])
    run('build-mover',[sys.executable,'-m','PyInstaller','--noconfirm','--distpath',work/'mover',
        '--workpath',work/'mover-cache','对话搬家.spec'],ROOT/'dialog-mover',600)
    package = work/'package'
    def exclude(directory,names):
        return ['dialog-mover-v0.3'] if Path(directory)==previous/'tools' else []
    shutil.copytree(previous,package,ignore=exclude)
    shutil.copytree(work/'mover/对话搬家',package/'tools/dialog-mover-v0.3')
    runtime = package/'tools/dialog-mover-v0.3/_internal'
    for name in ('MSVCP140.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll'):
        shutil.copy2(runtime/name,runtime/'bin'/name)
    for name in ('txcript.exe','AI一手记忆服务.exe'):
        if sha(runtime/'bin'/name)!=sha(previous/'tools/dialog-mover-v0.3/_internal/bin'/name):
            raise RuntimeError('An unrelated bundled component changed')
    # Collect newly bundled dependencies, retaining notices for other unchanged tools.
    new_notices = work/'mover-licenses'
    new_notices.mkdir()
    collect_python(work/'mover-cache/对话搬家/Analysis-00.toc',new_notices)
    notices = package/'THIRD-PARTY-LICENSES'
    components = { (row['name'],row['version']):row for row in json.loads((notices/'python-components.json').read_text(encoding='utf-8')) }
    components.update({(row['name'],row['version']):row for row in json.loads((new_notices/'python-components.json').read_text(encoding='utf-8'))})
    shutil.copytree(new_notices,notices,dirs_exist_ok=True)
    (notices/'python-components.json').write_text(json.dumps(list(components.values()),ensure_ascii=False,indent=2),encoding='utf-8')
    # No shell, controls, reset-calendar, resume-runtime or notification binary is rebuilt.
    preserved = {}
    for path in previous.rglob('*'):
        if not path.is_file(): continue
        name = path.relative_to(previous).as_posix()
        if name.startswith(('tools/dialog-mover-v0.3/','docs/')) or name in {'development-preview.json','update-manifest.json','THIRD-PARTY-LICENSES/python-components.json'}: continue
        if sha(package/name)!=sha(path): raise RuntimeError('Unrelated package file changed')
        preserved[name] = sha(path)
    shutil.copytree(ROOT/'docs',package/'docs',dirs_exist_ok=True)
    marker = json.loads((package/'development-preview.json').read_text(encoding='utf-8'))
    marker['source_sha256'] = {**{name:value for name,value in marker['source_sha256'].items() if not name.startswith('dialog-mover/')},**source_hashes}
    marker.update(compatibilityPreview='compressed-project-history-v1',preservedPackageFiles=preserved,
                  nativeContinuationVerified=False,modelRequests=0)
    (package/'development-preview.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding='utf-8')
    mover = package/'tools/dialog-mover-v0.3/对话搬家.exe'
    for label,flag in (('codex-import','--codex-import-self-test'),('memory','--memory-self-test')):
        report = work/(label+'-checks.json')
        run('frozen-'+label,[mover,flag,report],timeout=120)
        value = json.loads(report.read_text(encoding='utf-8-sig'))
        checks = value.get('checks') or []
        outcomes = list(checks.values()) if isinstance(checks,dict) else [check.get('passed') for check in checks]
        if value.get('passed') is not True or len(outcomes)<(7 if label=='codex-import' else 15) or any(result is not True for result in outcomes):
            raise RuntimeError('Frozen checks did not pass: '+label)
    run('workspace-self-check',[package/'AI一手工具工作台.exe','--self-test','--report',work/'workspace-checks.json'],timeout=180)
    workspace = json.loads((work/'workspace-checks.json').read_text(encoding='utf-8'))
    if workspace.get('failed')!=0 or not workspace.get('tests') or any(t.get('passed') is not True for t in workspace['tests']):
        raise RuntimeError('Workspace checks did not pass')
    if sources()!=source_hashes: raise RuntimeError('Sources changed while building')
    run('update-manifest',[sys.executable,ROOT/'scripts/update_manifest.py','--package',package,'--version','0.3.16'])
    run('package-check',[sys.executable,ROOT/'scripts/check_release.py','--package',package])
    shutil.copytree(package,destination)
    run('delivered-package-check',[sys.executable,ROOT/'scripts/check_release.py','--package',destination])
    (work/'build-report.json').write_text(json.dumps({'passed':True,'sourceFiles':len(source_hashes),
        'preservedFiles':len(preserved),'modelRequests':0,'nativeContinuationVerified':False,
        'scope':'Frozen converter, synthetic memory audit, existing WPF checks and package consistency; no real chat or model'},indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'preservedFiles':len(preserved),'nativeContinuationVerified':False}),flush=True)


if __name__=='__main__': main()
