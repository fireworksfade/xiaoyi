"""公共时间工具函数。"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    """将 datetime 转换为 ISO 8601 字符串。"""
    return (value or utc_now()).isoformat()
