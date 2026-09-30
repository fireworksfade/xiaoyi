import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionFactory
from app.main import app
from app.models import AgentRun, HarnessConnection, RunStatus, utc_now
from app.services.harness import assert_run_enabled


def login(client, name="admin", password="admin123"):
    result = client.post("/api/v1/auth/login", json={"username": name, "password": password})
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["data"]["csrf_token"]}


def test_disabled_connections_reject_new_work_and_keep_normal_platform_available():
    with TestClient(app) as client:
        headers = login(client)
        plugin_headers = {**headers, "X-Xiaoyi-Harness-Instance": "disabled-test"}
        assert client.get("/api/v1/auth/me", headers=plugin_headers).status_code == 409
        assert (
            client.post(
                "/api/v1/harness/connections/disabled-test/activate", headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/v1/auth/me", headers=plugin_headers).status_code == 200
        assert (
            client.post(
                "/api/v1/harness/connections/disabled-test/heartbeat", headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/harness/connections/disabled-test/deactivate", headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/v1/auth/me", headers=plugin_headers).status_code == 409
        assert (
            client.post(
                "/api/v1/harness/connections/disabled-test/heartbeat", headers=headers
            ).status_code
            == 409
        )
        assert client.get("/api/v1/auth/me").status_code == 200


def test_connections_are_user_scoped_and_require_csrf():
    with TestClient(app) as admin, TestClient(app) as operator:
        headers = login(admin)
        other_headers = login(operator, "operator", "operator123")
        path = "/api/v1/harness/connections/owner-test/activate"
        assert admin.post(path).status_code == 403
        assert admin.post(path, headers=headers).status_code == 200
        assert (
            operator.get(
                "/api/v1/auth/me", headers={"X-Xiaoyi-Harness-Instance": "owner-test"}
            ).status_code
            == 409
        )
        assert (
            operator.post(
                "/api/v1/harness/connections/owner-test/deactivate", headers=other_headers
            ).status_code
            == 200
        )
        assert (
            admin.get(
                "/api/v1/auth/me", headers={"X-Xiaoyi-Harness-Instance": "owner-test"}
            ).status_code
            == 200
        )


def test_plugin_task_marker_and_shutdown_cancel_only_associated_work(monkeypatch):
    class QuietDispatcher:
        def __init__(self):
            self.stopped = []

        def notify(self, _):
            pass

        async def cancel(self, run_id):
            self.stopped.append(run_id)
            async with SessionFactory() as db:
                run = await db.get(AgentRun, run_id)
                run.status = RunStatus.FAILED
                await db.commit()
            return True

    with TestClient(app) as client:
        dispatcher = QuietDispatcher()
        monkeypatch.setattr(app.state, "run_dispatcher", dispatcher)
        headers = login(client)
        client.post("/api/v1/harness/connections/task-test/activate", headers=headers)
        conversation = client.post("/api/v1/conversations", json={}, headers=headers).json()[
            "data"
        ]["id"]
        plugin_headers = {**headers, "X-Xiaoyi-Harness-Instance": "task-test"}
        first = client.post(
            f"/api/v1/conversations/{conversation}/messages",
            headers=plugin_headers,
            json={"content": "查询设备", "client_message_id": "plugin-test"},
        ).json()["data"]["run_id"]
        second = client.post(
            f"/api/v1/conversations/{conversation}/messages",
            headers=headers,
            json={"content": "普通平台任务", "client_message_id": "normal-test"},
        ).json()["data"]["run_id"]
        result = client.post(
            "/api/v1/harness/connections/task-test/deactivate", headers=headers
        ).json()["data"]
        assert first in result["stopped_run_ids"]
        assert second not in dispatcher.stopped
        denied = client.post(
            f"/api/v1/conversations/{conversation}/messages",
            headers=plugin_headers,
            json={"content": "不应提交", "client_message_id": "denied-test"},
        )
        assert denied.status_code == 409


async def test_runtime_guard_rejects_expired_plugin_lease():
    async with SessionFactory() as db:
        from app.models import Conversation, Message, User, UserRole, new_id

        owner = await db.scalar(select(User).where(User.username == "admin"))
        if owner is None:
            owner = User(username="admin", password_hash="unused", role=UserRole.ADMIN)
            db.add(owner)
            await db.flush()
        instance = new_id()
        db.add(
            HarnessConnection(
                user_id=owner.id,
                instance_id=instance,
                enabled=True,
                lease_until=utc_now() - timedelta(seconds=1),
            )
        )
        conversation = Conversation(user_id=owner.id)
        db.add(conversation)
        await db.flush()
        message = Message(conversation_id=conversation.id, role="user", content="test")
        db.add(message)
        await db.flush()
        run = AgentRun(
            user_id=owner.id,
            conversation_id=conversation.id,
            user_message_id=message.id,
            status=RunStatus.RUNNING,
            runtime_state={"harness_instance": instance},
        )
        db.add(run)
        await db.commit()
    import pytest

    with pytest.raises(asyncio.CancelledError):
        await assert_run_enabled(run.id)
