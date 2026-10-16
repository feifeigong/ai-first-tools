# -*- mode: python ; coding: utf-8 -*-
a = Analysis(['run.py'], pathex=['src'], binaries=[], datas=[('bin', 'bin')], hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['tkinter', 'numpy', 'pandas', 'webview'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AI一手续跑后台', debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False, disable_windowed_traceback=True, icon=['../workspace/assets/ai-first-logo.ico'])
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AI一手续跑后台')
