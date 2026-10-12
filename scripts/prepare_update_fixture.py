from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

from update_manifest import generate


def prepare(old: Path, new: Path, tool: Path, output: Path) -> None:
    if output.exists():
        raise RuntimeError("Use a new empty fixture directory; do not overwrite a running test.")
    output.mkdir(parents=True)
    for source, version, name in ((old, "0.3.7", "old"), (new, "0.3.8", "AI-First-Tools")):
        destination = output / name
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("tools", "docs", "THIRD-PARTY-LICENSES", "update-manifest.json"))
        target_tool = destination / "tools" / "dialog-mover-v0.3"
        shutil.copytree(tool, target_tool)
        shutil.copyfile(target_tool / "WorkspaceWindowFixture.exe", target_tool / "对话搬家.exe")
        generate(destination, version)
    (output / "old" / "my-notes.txt").write_text("synthetic user file must survive update", encoding="utf-8")
    settings = output / "settings"
    settings.mkdir()
    (settings / "tools.json").write_text("[]", encoding="utf-8")
    (output / "fixture-setup.exe").write_bytes(b"fixture only; not an installer")
    with zipfile.ZipFile(output / "fixture-portable.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (output / "AI-First-Tools").rglob("*"):
            if path.is_file():
                archive.write(path, "AI-First-Tools/" + path.relative_to(output / "AI-First-Tools").as_posix())
    checksums = []
    for source, name in ((output / "fixture-setup.exe", "AI-First-Tools-Setup-0.3.8.exe"), (output / "fixture-portable.zip", "AI-First-Tools-Portable-0.3.8-win-x64.zip")):
        with source.open("rb") as stream:
            checksums.append(hashlib.file_digest(stream, "sha256").hexdigest() + "  " + name)
    (output / "fixture-checksums.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"Isolated old app: {output / 'old' / 'AI一手工具工作台.exe'}")
    print("Launch with --config settings/tools.json --update-fixture AI-First-Tools (use absolute paths).")
    print("All embedded tools are synthetic WindowFixture processes, not the real mover.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    prepare(arguments.old.resolve(), arguments.new.resolve(), arguments.tool.resolve(), arguments.output.resolve())
