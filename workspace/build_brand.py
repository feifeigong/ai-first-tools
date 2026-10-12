from pathlib import Path
import argparse
import shutil

from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logo", type=Path)
    parser.add_argument("--app-icon", type=Path)
    options = parser.parse_args()
    assets = Path(__file__).resolve().parent / "assets"
    with Image.open(options.app_icon or options.logo) as original:
        image = original.convert("RGBA")
        assets.mkdir(exist_ok=True)
        image.save(assets / "ai-first-logo.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
    if options.logo.resolve() != (assets / "ai-first-logo.jpg").resolve():
        shutil.copyfile(options.logo, assets / "ai-first-logo.jpg")
    if options.app_icon and options.app_icon.resolve() != (assets / "ai-first-app-icon.png").resolve():
        shutil.copyfile(options.app_icon, assets / "ai-first-app-icon.png")


if __name__ == "__main__":
    main()
