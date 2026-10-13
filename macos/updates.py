from __future__ import annotations

import json
import platform
import re
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

REPOSITORY = "https://github.com/feifeigong/ai-first-tools"
API_URL = "https://api.github.com/repos/feifeigong/ai-first-tools/releases?per_page=100"
DOWNLOADS_URL = f"{REPOSITORY}/releases"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        raise ValueError("Unexpected update service redirect")


def tls_context():
    import truststore

    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def failure(error: Exception) -> dict:
    code = "network"
    message = "暂时连不上 GitHub，请检查网络或系统代理，也可以在浏览器打开下载页。"
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(error, HTTPError):
        if error.code == 429 or error.code == 403 and (error.headers or {}).get("X-RateLimit-Remaining") == "0":
            code, message = "rate_limit", "GitHub 检查次数达到上限，请稍后再试，或在浏览器打开下载页。"
        else:
            code, message = "http", "GitHub 暂未允许此次更新查询，可以在浏览器打开下载页。"
    elif isinstance(reason, ssl.SSLCertVerificationError):
        code, message = "certificate", "无法验证 GitHub 的安全连接，请检查系统时间或代理证书。也可以在浏览器打开下载页。"
    elif isinstance(reason, ssl.SSLError):
        code, message = "tls", "与 GitHub 的安全连接未能建立，请检查网络或系统代理。也可以在浏览器打开下载页。"
    elif isinstance(reason, (TimeoutError, socket.timeout)):
        code, message = "timeout", "连接 GitHub 超时，请稍后重试，或在浏览器打开下载页。"
    elif isinstance(reason, socket.gaierror):
        code, message = "dns", "无法找到 GitHub 的网络地址，请检查网络或系统代理。也可以在浏览器打开下载页。"
    elif isinstance(error, (ValueError, TypeError)):
        code, message = "response", "GitHub 返回的更新信息不符合要求，未确认是否有新版。可以打开下载页查看。"
    elif isinstance(error, ImportError):
        code, message = "component", "更新组件不完整，请从本项目下载完整的 Mac 应用。"
    return {"error": message, "errorCode": code, "canOpenDownloads": True}


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


def check(current: str, *, token: str | None = None) -> dict:
    headers = {"User-Agent": "AI-First-Tools-macOS", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(API_URL, headers=headers)
    opener = build_opener(NoRedirect(), HTTPSHandler(context=tls_context()))
    with opener.open(request, timeout=15) as response:
        if response.geturl() != API_URL:
            raise ValueError("Unexpected update service redirect")
        body = response.read(4 * 1024 * 1024 + 1)
    if len(body) > 4 * 1024 * 1024:
        raise ValueError("Update response is too large")
    releases = json.loads(body)
    if not isinstance(releases, list):
        raise ValueError("Invalid update response")
    found = choose_release(releases, current, platform.machine())
    assets = next((release.get("assets", []) for release in releases if isinstance(release, dict)
                   and found and release.get("tag_name") == "v" + found["version"]), [])
    return {"available": found is not None, **(found or {}), "assets": assets}
