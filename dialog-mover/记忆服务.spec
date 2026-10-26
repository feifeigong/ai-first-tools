# -*- mode: python ; coding: utf-8 -*-
a = Analysis(['memory_service.py'], pathex=[], binaries=[], datas=[], hiddenimports=[],
             hookspath=[], runtime_hooks=[], excludes=['webview', 'tkinter', 'numpy', 'pandas'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='AI一手记忆服务', console=True,
          debug=False, strip=False, upx=False, icon=['ui/icon.ico'])
