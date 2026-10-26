import json
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
resources = root / "artifacts" / "macos" / "resources"
version = json.loads((resources / "version.json").read_text(encoding="utf-8"))
engine = root / "dialog-mover" / "bin" / "txcript"
native = root / 'artifacts/macos/auto-resume-native'
reset = root / 'artifacts/macos/reset-news'
native_binaries = []
native_data = []
for path in native.rglob('*'):
    if path.is_file():
        item = (str(path), 'auto-resume-native/' + path.parent.relative_to(native).as_posix())
        (native_binaries if path.stat().st_mode & 0o111 else native_data).append(item)
if not native_binaries:
    raise RuntimeError('Prepare the pinned auto-resume runtime before packaging')
if not (reset / 'AI.First.ResetBridge').is_file() or not (reset / 'parity.json').is_file():
    raise RuntimeError('Prepare and test the shared reset rules before packaging')
for path in reset.rglob('*'):
    if path.is_file():
        item = (str(path), 'reset-news/' + path.parent.relative_to(reset).as_posix())
        (native_binaries if path.stat().st_mode & 0o111 else native_data).append(item)
if not engine.is_file():
    raise RuntimeError("Build the macOS txcript engine first")

analysis = Analysis(
    [str(root / "macos" / "entry.py")],
    pathex=[str(root / "macos"), str(root / "dialog-mover"), str(root / "dialog-mover" / "vendor"), str(root / 'auto-resume/src')],
    binaries=[(str(engine), "bin"), *native_binaries],
    datas=[(str(resources / "ui"), "ui"), (str(resources / "version.json"), "."),
           (str(root / "licenses"), "licenses"), (str(root / "LICENSE"), "."), (str(root / "NOTICE"), "."), *native_data],
    hiddenimports=["webview.platforms.cocoa", "brotli", "zstd", "zstandard", "ccl_simplesnappy", "Security", "_scproxy", "truststore._macos"] + collect_submodules("ccl_chromium_reader"),
    excludes=["clr", "pythonnet", "webview.platforms.winforms", "webview.platforms.edgechromium"],
)
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True, name="AI First Tools", console=False,
                 upx=False, target_arch=None, codesign_identity=None)
collection = COLLECT(executable, analysis.binaries, analysis.datas, name="AI First Tools", upx=False)
app = BUNDLE(collection, name="AI一手工具工作台.app", icon=str(resources / "ai-first.icns"),
             bundle_identifier="cn.aifirst.tools.preview" if version.get('developmentPreview') else "cn.aifirst.tools", version=version["version"],
             info_plist={"CFBundleDisplayName": "AI一手工具工作台 · 本地预览" if version.get('developmentPreview') else "AI一手工具工作台", "CFBundleShortVersionString": version["version"],
                         "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "13.0",
                         "NSHumanReadableCopyright": "Apache-2.0; third-party trademarks belong to their owners."})
