"""Inline image conversion without reading files or fetching remote URLs."""
from __future__ import annotations

import base64
import binascii

MAX_IMAGE_BYTES = 32 * 1024 * 1024


def attachment(source: dict, number: int = 1) -> dict:
    if not isinstance(source, dict) or source.get("type") != "base64":
        raise ValueError("图片不是内嵌格式，无法完整搬入 Copilot。")
    mime, data = source.get("media_type"), source.get("data")
    extensions = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
    if not isinstance(mime, str) or mime not in extensions or not isinstance(data, str) or not data or len(data) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise ValueError("图片格式或大小无法由 Copilot 接收，未写入残缺记录。")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("来源图片编码损坏，未写入 Copilot。") from error
    valid = {"image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"), "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
             "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
             "image/webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"}
    if not valid[mime] or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("来源图片与声明格式不符，未写入 Copilot。")
    return {"type": "blob", "mimeType": mime, "data": data, "displayName": f"图片 {number}.{extensions[mime]}"}


def image_block(value: dict) -> dict:
    source = {"type": "base64", "media_type": value.get("mimeType"), "data": value.get("data")}
    attachment(source)  # Validate the persisted shape too; never follow a path.
    return {"type": "image", "source": source}
