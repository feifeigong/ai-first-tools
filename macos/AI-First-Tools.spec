import json
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
resources = root / "artifacts" / "macos" / "resources"
version = json.loads((root / "macos" / "version.json").read_text(encoding="utf-8"))
engine = root / "dialog-mover" / "bin" / "txcript"
if not engine.is_file():
    raise RuntimeError("Build the macOS txcript engine first")

analysis = Analysis(
    [str(root / "macos" / "entry.py")],
    pathex=[str(root / "macos"), str(root / "dialog-mover"), str(root / "dialog-mover" / "vendor")],
    binaries=[(str(engine), "bin")],
    datas=[(str(resources / "ui"), "ui"), (str(resources / "version.json"), "."),
           (str(root / "licenses"), "licenses"), (str(root / "LICENSE"), "."), (str(root / "NOTICE"), ".")],
    hiddenimports=["webview.platforms.cocoa", "brotli", "zstd", "ccl_simplesnappy", "Security"] + collect_submodules("ccl_chromium_reader"),
    excludes=["clr", "pythonnet", "webview.platforms.winforms", "webview.platforms.edgechromium"],
)
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True, name="AI First Tools", console=False,
                 upx=False, target_arch=None, codesign_identity=None)
collection = COLLECT(executable, analysis.binaries, analysis.datas, name="AI First Tools", upx=False)
app = BUNDLE(collection, name="AI一手工具工作台.app", icon=str(resources / "ai-first.icns"),
             bundle_identifier="cn.aifirst.tools", version=version["version"],
             info_plist={"CFBundleDisplayName": "AI一手工具工作台", "CFBundleShortVersionString": version["version"],
                         "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "13.0",
                         "NSHumanReadableCopyright": "Apache-2.0; third-party trademarks belong to their owners."})
