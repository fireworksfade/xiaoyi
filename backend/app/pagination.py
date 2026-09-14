"""通用游标分页（specs WP-10 / §3.4）。

不透明 URL-safe Base64 游标，编码 {created_at, id}；
查询按 (created_at DESC, id DESC) 取最近一页，返回前反转为升序。
前端不解析游标内容。
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from typing import Any


def encode_cursor(created_at: datetime, item_id: str) -> str:
    # SQLite 返回 naive datetime（按 UTC 存储）；直接标记为 UTC，不做本地时区换算
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    payload = {"created_at": created_at.isoformat(), "id": item_id}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, str(payload["id"])
    except (ValueError, binascii.Error, KeyError, TypeError, UnicodeDecodeError):
        return None


def page_window(
    items: list[dict[str, Any]],
    *,
    limit: int,
    created_at_key: str = "created_at",
    id_key: str = "id",
) -> dict[str, Any]:
    """输入为升序一页 + 是否有更早数据；输出分页信封字段。"""
    if not items:
        return {"items": [], "next_cursor": None, "has_more": False}
    oldest = items[0]
    next_cursor = encode_cursor(oldest[created_at_key], oldest[id_key])
    return {"items": items, "next_cursor": next_cursor, "has_more": True}
