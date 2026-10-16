from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
from urllib.request import urlopen


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / 'auto-resume/codex-runtime.lock.json').read_text(encoding='utf-8'))
    cache = root / 'artifacts/build-tools'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / ('codex-' + lock['version'] + '.tgz')
    algorithm, expected = lock['integrity'].split('-', 1)
    if algorithm != 'sha512' or not lock['url'].startswith('https://registry.npmjs.org/@openai/codex/-/'):
        raise ValueError('Untrusted Codex distribution')
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        with urlopen(lock['url'], timeout=120) as source, temporary.open('wb') as destination:
            shutil.copyfileobj(source, destination)
        temporary.replace(archive)
    with archive.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha512').digest()
    if digest != base64.b64decode(expected):
        raise ValueError('Codex archive integrity mismatch')
    output = root / 'auto-resume/bin'
    output.mkdir(parents=True, exist_ok=True)
    written = []
    with tarfile.open(archive, 'r:gz') as package:
        for entry in package.getmembers():
            parts = PurePosixPath(entry.name).parts
            if not parts or parts[0] != 'package' or '..' in parts or entry.issym() or entry.islnk():
                raise ValueError('Unsafe Codex package member')
            if not entry.isfile():
                continue
            relative = Path(*parts[1:])
            destination = output / relative
            if not destination.resolve().is_relative_to(output.resolve()):
                raise ValueError('Codex package escaped output directory')
            destination.parent.mkdir(parents=True, exist_ok=True)
            stream = package.extractfile(entry)
            if stream is None:
                raise ValueError('Missing Codex package content')
            with stream, destination.open('wb') as target:
                shutil.copyfileobj(stream, target)
            written.append(relative.as_posix())
    for name, digest in lock['notices'].items():
        with urlopen('https://raw.githubusercontent.com/openai/codex/' + lock['sourceCommit'] + '/' + name, timeout=30) as source:
            data = source.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Codex notice integrity mismatch')
        (output / name).write_bytes(data)
        written.append(name)
    executable = output / 'vendor/x86_64-pc-windows-msvc/bin/codex.exe'
    if not executable.is_file() or not any('LICENSE' in name.upper() for name in written):
        raise ValueError('Codex native runtime or license is missing')
    (output / 'distribution.json').write_text(json.dumps(lock, indent=2), encoding='utf-8')
    print(json.dumps({'verified': True, 'version': lock['version'], 'files': written}))


if __name__ == '__main__':
    main()
