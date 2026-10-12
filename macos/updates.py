from __future__ import annotations

import json
import platform
import re
from urllib.request import Request, urlopen

REPOSITORY = "https://github.com/feifeigong/ai-first-tools"
API_URL = "https://api.github.com/repos/feifeigong/ai-first-tools/releases?per_page=100"


def release_key(value: str) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-macos-preview\.(\d+))?", value)
    if match is None:
        return None
    return (*map(int, match.group(1, 2, 3)), int(match.group(4)) if match.group(4) else 1_000_000)


def choose_release(releases: list, current: str, architecture: str) -> dict | None:
    current_key = release_key(current)
    if current_key is None or architecture not in ("arm64", "x86_64"):
        return None
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = str(release.get("tag_name", ""))
        key = release_key(tag)
        if key is None or key <= current_key:
            continue
        filename = f"AI-First-Tools-{tag.removeprefix('v')}-macos-{architecture}.dmg"
        url = f"{REPOSITORY}/releases/tag/{tag}"
        assets = release.get("assets", [])
        if not isinstance(assets, list):
            continue
        valid = any(isinstance(asset, dict) and asset.get("name") == filename and asset.get("state") == "uploaded"
                    and isinstance(asset.get("size"), int) and asset["size"] > 0
                    and asset.get("browser_download_url") == f"{REPOSITORY}/releases/download/{tag}/{filename}"
                    for asset in assets)
        if valid and release.get("html_url") == url:
            candidates.append((key, {"version": tag.removeprefix("v"), "url": url}))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def check(current: str) -> dict:
    request = Request(API_URL, headers={"User-Agent": "AI-First-Tools-macOS", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=15) as response:
        if response.geturl() != API_URL:
            raise ValueError("Unexpected update service redirect")
        body = response.read(4 * 1024 * 1024 + 1)
    if len(body) > 4 * 1024 * 1024:
        raise ValueError("Update response is too large")
    releases = json.loads(body)
    if not isinstance(releases, list):
        raise ValueError("Invalid update response")
    found = choose_release(releases, current, platform.machine())
    return {"available": found is not None, **(found or {})}
