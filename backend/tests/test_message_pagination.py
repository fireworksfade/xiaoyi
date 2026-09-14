"""消息游标分页测试（specs WP-10 / §9.2、§14.5）。"""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.db import SessionFactory
from app.main import app
from app.models import Message, utc_now
from app.pagination import decode_cursor, encode_cursor


def test_cursor_roundtrip() -> None:
    now = utc_now()
    cursor = encode_cursor(now, "abc")
    decoded = decode_cursor(cursor)
    assert decoded is not None
    decoded_time, decoded_id = decoded
    assert decoded_id == "abc"
    assert decoded_time == now


def test_invalid_cursor_returns_none() -> None:
    assert decode_cursor(None) is None
    assert decode_cursor("") is None
    assert decode_cursor("!!!not-base64!!!") is None
    assert decode_cursor("YWJj") is None  # "abc" 不是合法 JSON


async def _seed_messages(conversation_id: str, count: int) -> None:
    async with SessionFactory() as db:
        base = utc_now() - timedelta(minutes=count + 1)
        for i in range(count):
            db.add(
                Message(
                    conversation_id=conversation_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"消息{i}",
                    metadata_json={},
                    created_at=base + timedelta(minutes=i),
                )
            )
        await db.commit()


def test_pagination_stable_with_duplicate_timestamps() -> None:
    """相同 timestamp 用 id 稳定翻页，无重复/遗漏。"""
    import asyncio

    async def run(client):
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        csrf = login.json()["data"]["csrf_token"]
        conversation = client.post(
            "/api/v1/conversations", json={"title": "分页测试"}, headers={"X-CSRF-Token": csrf}
        ).json()["data"]
        conversation_id = conversation["id"]
        same_time = utc_now()
        async with SessionFactory() as db:
            for i in range(30):
                db.add(
                    Message(
                        conversation_id=conversation_id,
                        role="user",
                        content=f"m{i}",
                        metadata_json={},
                        created_at=same_time,  # 全部相同时间戳
                    )
                )
            await db.commit()

        seen: list[str] = []
        before = ""
        while True:
            response = client.get(
                f"/api/v1/conversations/{conversation_id}/messages",
                params={"limit": 7, **({"before": before} if before else {})},
            )
            data = response.json()["data"]
            seen.extend(item["content"] for item in data["items"])
            if not data["has_more"]:
                break
            before = data["next_cursor"]
        assert len(seen) == 30
        assert len(set(seen)) == 30

    with TestClient(app) as client:
        asyncio.run(run(client))


def test_pagination_500_messages_first_page_only() -> None:
    """500 条消息的对话首屏最多读取配置的一页。"""
    import asyncio
    import time

    async def run(client):
        login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        csrf = login.json()["data"]["csrf_token"]
        conversation = client.post(
            "/api/v1/conversations", json={"title": "长对话"}, headers={"X-CSRF-Token": csrf}
        ).json()["data"]
        conversation_id = conversation["id"]
        base = utc_now() - timedelta(minutes=600)
        async with SessionFactory() as db:
            for i in range(500):
                db.add(
                    Message(
                        conversation_id=conversation_id,
                        role="user",
                        content=f"m{i}",
                        metadata_json={},
                        created_at=base + timedelta(minutes=i),
                    )
                )
            await db.commit()

        started = time.monotonic()
        response = client.get(
            f"/api/v1/conversations/{conversation_id}/messages", params={"limit": 50}
        )
        data = response.json()["data"]
        elapsed = time.monotonic() - started
        assert len(data["items"]) == 50
        assert data["has_more"] is True
        assert data["next_cursor"]
        assert elapsed < 2  # 首屏不扫描全表
        # 完整翻页顺序一致
        seen = [item["content"] for item in data["items"]]
        before = data["next_cursor"]
        while True:
            page = client.get(
                f"/api/v1/conversations/{conversation_id}/messages",
                params={"limit": 50, "before": before},
            ).json()["data"]
            seen.extend(item["content"] for item in page["items"])
            if not page["has_more"]:
                break
            before = page["next_cursor"]
        assert len(seen) == 500
        # 每页升序、翻页向更早推进 → 分块降序：[450..499, 400..449, ..., 0..49]
        expected: list[str] = []
        for start in range(450, -1, -50):
            expected.extend(f"m{i}" for i in range(start, start + 50))
        assert seen == expected

    with TestClient(app) as client:
        asyncio.run(run(client))
