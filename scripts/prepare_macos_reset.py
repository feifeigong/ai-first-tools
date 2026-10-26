"""Build the shared Windows reset rules as a self-contained Mac component."""
from __future__ import annotations
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ('ResetNewsService.cs', 'ResetNewsDiscovery.cs', 'ResetNewsPresentation.cs', 'ResetCalendarModel.cs')


def prepare(architecture: str) -> Path:
    if sys.platform != 'darwin' or platform.machine() != architecture or architecture not in {'arm64', 'x86_64'}:
        raise RuntimeError('Build the shared reset component on the matching real Mac architecture')
    destination = ROOT / 'artifacts/macos/reset-news'
    destination.mkdir(parents=True, exist_ok=True)
    rid = 'osx-arm64' if architecture == 'arm64' else 'osx-x64'
    subprocess.run(['dotnet', 'publish', str(ROOT / 'macos/ResetBridge/ResetBridge.csproj'), '-c', 'Release', '-r', rid,
                    '--self-contained', 'true', '-p:PublishSingleFile=false', '-o', str(destination)], check=True)
    sources = {name: hashlib.sha256((ROOT / 'workspace' / name).read_bytes()).hexdigest() for name in SHARED}
    (destination / 'parity.json').write_text(json.dumps({'architecture': architecture, 'sharedWindowsSources': sources}), encoding='utf-8')
    report = ROOT / 'artifacts/macos' / architecture / 'reset-rules-test.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(destination / 'AI.First.ResetBridge'), '--self-test', '--report', str(report)], check=True, timeout=120)
    result = json.loads(report.read_text(encoding='utf-8'))
    if result.get('passed') is not True or not result.get('checks') or any(item.get('passed') is not True for item in result['checks']):
        raise RuntimeError('Shared Windows reset rule checks failed')
    result['details'] = result['checks']
    result['checks'] = {item['name']: item['passed'] for item in result['details']}
    result['architecture'] = architecture
    result['version'] = json.loads((ROOT / 'macos/version.json').read_text(encoding='utf-8'))
    result['sharedWindowsSources'] = sources
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--architecture', choices=('arm64', 'x86_64'), required=True)
    prepare(parser.parse_args().architecture)
