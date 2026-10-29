"""Pin an actual previously published updater; never use an installed user app."""
import hashlib,json,platform,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def prepare(architecture):
    if sys.platform!='darwin' or platform.machine()!=architecture:raise RuntimeError('Use the matching native Mac runner')
    lock=json.loads((ROOT/'macos/legacy-update.lock.json').read_text(encoding='utf8'))
    folder=ROOT/'artifacts/macos/legacy-update';folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'published-{architecture}.dmg';expected=lock[architecture]
    def matches():
        if not target.is_file() or target.stat().st_size!=expected['size']:return False
        with target.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==expected['sha256']
    if not matches():
        version=lock['release']
        url=f'https://github.com/feifeigong/ai-first-tools/releases/download/v{version}/AI-First-Tools-{version}-macos-{architecture}.dmg'
        subprocess.run(['/usr/bin/curl','--fail','--location','--silent','--show-error','--retry','3','--connect-timeout','15','--max-time','180','--output',str(target),url],check=True,timeout=200)
    if not matches():raise RuntimeError('Published updater fixture digest mismatch')
    return target
