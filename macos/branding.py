"""Visible product name; bundle paths and identifiers stay upgrade-compatible."""
from __future__ import annotations

import plistlib
from pathlib import Path

PRODUCT_NAME = 'AI一手工具箱'


def display_name(preview: bool = False) -> str:
    return PRODUCT_NAME + ('预览' if preview else '')


def localize_bundle(bundle: Path, preview: bool = False) -> None:
    # Older installed updaters require the original .app path. Finder supports
    # a localized product name independently of that stable filesystem name.
    info_path = bundle / 'Contents/Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    info['CFBundleName'] = bundle.stem
    info['CFBundleDisplayName'] = bundle.stem
    info['CFBundleDevelopmentRegion'] = 'en'
    info['CFBundleLocalizations'] = ['en', 'zh-Hans', 'zh-Hant']
    info_path.write_bytes(plistlib.dumps(info))
    name = display_name(preview)
    strings = f'"CFBundleName" = "{name}";\n"CFBundleDisplayName" = "{name}";\n'
    for language in ('Base', 'en', 'zh-Hans', 'zh-Hant'):
        directory = bundle / 'Contents/Resources' / (language + '.lproj')
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'InfoPlist.strings').write_text(strings, encoding='utf-8')


def apply_process_name(preview: bool = False) -> None:
    from Foundation import NSProcessInfo
    NSProcessInfo.processInfo().setProcessName_(display_name(preview))
