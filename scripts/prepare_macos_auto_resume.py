"""Prepare checksum-pinned native runtime; ordinary users install only the app."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

def prepare(architecture: str) -> Path:
    lock = json.loads((ROOT / 'auto-resume/codex-macos.lock.json').read_text())
    package = lock['packages'][architecture]
    cache = ROOT / 'artifacts/build-tools'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / ('codex-' + package['version'] + '.tgz')
    if not archive.exists():
        with urlopen('https://registry.npmjs.org/@openai/codex/-/' + archive.name, timeout=120) as source, archive.with_suffix('.download').open('wb') as target:
            shutil.copyfileobj(source, target)
        archive.with_suffix('.download').replace(archive)
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha512').digest() != base64.b64decode(package['integrity'].split('-',1)[1]):
            raise ValueError('Native Codex checksum mismatch')
    output = ROOT / 'artifacts/macos/auto-resume-native'
    output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != 'package' or '..' in parts or member.issym() or member.islnk():
                raise ValueError('Unsafe native package path')
            if not member.isfile():
                continue
            target = output.joinpath(*parts[1:])
            if not target.resolve().is_relative_to(output.resolve()):
                raise ValueError('Native package escaped target')
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, target.open('wb') as stream:
                shutil.copyfileobj(source, stream)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    for name, expected in lock['notices'].items():
        with urlopen('https://raw.githubusercontent.com/openai/codex/' + lock['sourceCommit'] + '/' + name, timeout=30) as source:
            data = source.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Native component notice checksum mismatch')
        (output / name).write_bytes(data)
    executable = output / 'vendor' / package['triple'] / 'bin/codex'
    if not executable.is_file():
        raise ValueError('Native Codex executable missing')
    executable.chmod(0o755)
    (output / 'distribution.json').write_text(json.dumps(package, indent=2))
    return output

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--architecture', choices=('arm64','x86_64'), required=True)
    print(prepare(parser.parse_args().architecture))
