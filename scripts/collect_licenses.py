from __future__ import annotations

import argparse
import ast
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from strings(item)


def collect_python(toc: Path, destination: Path):
    bundled = {str(Path(item).resolve()).casefold() for item in strings(ast.literal_eval(toc.read_text(encoding="utf-8"))) if Path(item).is_absolute()}
    notices = []
    for distribution in importlib.metadata.distributions():
        files = distribution.files or []
        name = distribution.metadata.get("Name", "unknown")
        included = any(str(Path(distribution.locate_file(item)).resolve()).casefold() in bundled for item in files)
        if not included and name.casefold() != "pyinstaller":
            continue
        output = destination / "python-packages" / f"{name}-{distribution.version}"
        output.mkdir(parents=True, exist_ok=True)
        notices.append({"name": name, "version": distribution.version, "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"), "homepage": distribution.metadata.get("Home-page")})
        for item in files:
            if any(word in item.name.casefold() for word in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    shutil.copy2(source, output / item.name)
        metadata = distribution.read_text("METADATA")
        if metadata:
            (output / "METADATA.txt").write_text(metadata, encoding="utf-8")
    (destination / "python-components.json").write_text(json.dumps(notices, ensure_ascii=False, indent=2), encoding="utf-8")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        python_license = Path(__file__).resolve().parent.parent / "licenses" / "Python-LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("Python license file is required")
    shutil.copy2(python_license, destination / "Python-LICENSE.txt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--toc", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--nsis", type=Path, required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    destination = arguments.package / "THIRD-PARTY-LICENSES"
    destination.mkdir(parents=True, exist_ok=True)
    collect_python(arguments.toc, destination)
    shutil.copytree(root / "licenses", destination / "project", dirs_exist_ok=True)
    shutil.copy2(arguments.nsis / "COPYING", destination / "NSIS-COPYING.txt")
    nuget = Path.home() / ".nuget" / "packages"
    for package_name in ("microsoft.netcore.app.runtime.win-x64", "microsoft.windowsdesktop.app.runtime.win-x64"):
        candidates = sorted((nuget / package_name).glob("*"))
        if not candidates:
            raise RuntimeError(f"Runtime license not found: {package_name}")
        output = destination / package_name
        output.mkdir(exist_ok=True)
        for source in candidates[-1].rglob("*"):
            if source.is_file() and any(word in source.name.casefold() for word in ("license", "notice")):
                shutil.copy2(source, output / source.name)
    (destination / "Microsoft-runtime-links.txt").write_text("Microsoft Visual C++ runtime components: https://visualstudio.microsoft.com/license-terms/\nMicrosoft WebView2 runtime and SDK: https://www.microsoft.com/en-us/legal/terms-of-use\nWebView2 runtime distribution: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution\nThe WebView2 runtime installer presents/operates under Microsoft's own terms.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
