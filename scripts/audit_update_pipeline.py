"""Full shipped payload, real helper/reopen, synthetic tools and lifecycle only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
from update_manifest import generate


def run(package: Path, output: Path, report: Path):
    repo = Path(__file__).resolve().parents[1]
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((package / 'update-manifest.json').read_text(encoding='utf-8-sig'))
    payload_bytes = sum(f['size'] for f in manifest['files'])
    assert payload_bytes > 500_000_000, 'Use the full release payload, not a small fixture'
    with (output / 'build.log').open('w', encoding='utf-8') as log:
        def publish(project, destination, version=None):
            args = ['dotnet', 'publish', str(project), '-c', 'Release', '-r', 'win-x64', '--self-contained', 'true', '-o', str(destination)]
            if version:
                args.append('-p:Version=' + version)
            subprocess.run(args, check=True, stdout=log, stderr=log)
        publish(repo / 'workspace/tests/WindowFixture/WindowFixture.csproj', output / 'tool')
        for name, version in (('old', '0.3.7'), ('AI-First-Tools', '0.3.8')):
            target = output / name
            target.mkdir()
            for entry in manifest['files']:
                source, destination = package / entry['path'], target / entry['path']
                assert source.resolve().is_relative_to(package.resolve())
                assert destination.resolve().is_relative_to(target.resolve())
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            publish(repo / 'workspace/AIFirst.Workspace.csproj', target, version)
            tool = target / 'tools/dialog-mover-v0.3'
            shutil.copytree(output / 'tool', tool, dirs_exist_ok=True)
            shutil.copy2(tool / 'WorkspaceWindowFixture.exe', tool / '对话搬家.exe')
            # Never touch the developer's live background or Agent settings.
            (target / 'assets/auto-resume-bundled.ps1').write_text(
                "param([string]$Action)\n'{\"installed\":false,\"running\":false,\"autostart\":false,\"watcherCount\":0,\"error\":\"\"}'\n", encoding='utf-8')
            generate(target, version)
    (output / 'old/my-notes.txt').write_text('synthetic user file must survive update')
    settings = output / 'settings'
    settings.mkdir()
    config = settings / 'tools.json'
    config.write_text('[]')
    (output / 'fixture-setup.exe').write_bytes(b'not executed; portable fixture')
    with zipfile.ZipFile(output / 'fixture-portable.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in (output / 'AI-First-Tools').rglob('*'):
            if path.is_file():
                archive.write(path, 'AI-First-Tools/' + path.relative_to(output / 'AI-First-Tools').as_posix())
    sums = []
    for source, name in (('fixture-setup.exe', 'AI-First-Tools-Setup-0.3.8.exe'), ('fixture-portable.zip', 'AI-First-Tools-Portable-0.3.8-win-x64.zip')):
        with (output / source).open('rb') as stream:
            sums.append(hashlib.file_digest(stream, 'sha256').hexdigest() + '  ' + name)
    (output / 'fixture-checksums.txt').write_text('\n'.join(sums) + '\n')
    handoff_path = output / 'handoff.json'
    start = subprocess.STARTUPINFO()
    start.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    start.wShowWindow = 0
    began = time.monotonic()
    parent = subprocess.Popen([str(output / 'old/AI一手工具工作台.exe'), '--update-handoff-test', '--config', str(config), '--update-fixture', str(output / 'AI-First-Tools'), '--report', str(handoff_path)], startupinfo=start)
    assert parent.wait(timeout=180) == 0
    closed = time.monotonic()
    handoff = json.loads(handoff_path.read_text(encoding='utf-8-sig'))
    assert handoff['handedOff']
    job = Path(handoff['job'])
    deadline = time.monotonic() + 90
    ready = job / 'reopened.json'
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(.1)
    assert ready.exists(), 'The new process did not attach its native tool'
    health = json.loads(ready.read_text(encoding='utf-8-sig'))
    assert health['ready'] and health['attached'] and health['width'] > 0 and health['height'] > 0
    assert (job / 'completed').exists()
    assert json.loads((job / 'progress.json').read_text(encoding='utf-8-sig'))['step'] == 6
    assert (output / 'old/my-notes.txt').read_text() == 'synthetic user file must survive update'
    result = {'passed': True, 'fullPayloadBytes': payload_bytes, 'realHelper': True, 'newToolAttached': True,
              'extraFilePreserved': True, 'parentExitToToolReadyMs': round((time.monotonic() - closed) * 1000),
              'prepareThroughToolReadyMs': round((time.monotonic() - began) * 1000),
              'scope': 'Full shipped bytes, real helper and WPF reopen; synthetic embedded tool and no-op background lifecycle; no user installation or Agent data'}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + '\n')
    (output / 'cleanup.json').write_text(json.dumps({'hostProcess': health['hostProcess'], 'target': str(output / 'old')}))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    run(args.package.resolve(), args.output.resolve(), args.report.resolve())
