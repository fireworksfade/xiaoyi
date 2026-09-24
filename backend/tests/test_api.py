import asyncio
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.runtime import RuntimeEvent
from app.config import Settings, get_settings
from app.db import SessionFactory
from app.main import app
from app.models import (
    Attachment,
    Conversation,
    MCPPurpose,
    MCPServer,
    MCPTool,
    Message,
    ModelConfiguration,
    ToolRiskPolicy,
)
from app.security import decrypt_secret


def test_session_cookie_policy_is_configurable_and_safe() -> None:
    lax = Settings(_env_file=None, session_cookie_secure=False, session_cookie_samesite="lax")
    assert lax.session_cookie_samesite == "lax"

    cross_site = Settings(
        _env_file=None,
        session_cookie_secure=True,
        session_cookie_samesite="none",
    )
    assert cross_site.session_cookie_secure is True

    with pytest.raises(ValueError, match="requires SESSION_COOKIE_SECURE=true"):
        Settings(_env_file=None, session_cookie_secure=False, session_cookie_samesite="none")


def test_comma_separated_list_settings_work_in_container_environment() -> None:
    settings = Settings(
        _env_file=None,
        frontend_origins="http://localhost:3000,https://example.test",
        mcp_allowed_hosts="localhost,iot-diagnosis-mcp",
    )
    assert settings.frontend_origins == ["http://localhost:3000", "https://example.test"]
    assert settings.mcp_allowed_hosts == ["localhost", "iot-diagnosis-mcp"]


def test_login_cookie_uses_configured_policy() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_attachment_and_tool_selection_reach_agent_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class CaptureRuntime:
        async def stream(self, messages, mcp_servers):
            captured["messages"] = messages
            captured["mcp_servers"] = mcp_servers
            yield RuntimeEvent("answer.final", {"content": "已读取附件"})

    monkeypatch.setattr("app.services.runs.build_runtime", lambda _settings: CaptureRuntime())

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login.status_code == 200
        csrf = login.json()["data"]["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        uploaded = client.post(
            "/api/v1/attachments",
            files={"file": ("context.md", b"# Device\nSensor A is healthy.", "text/markdown")},
            headers=headers,
        )
        assert uploaded.status_code == 201
        attachment_id = uploaded.json()["data"]["id"]
        assert "Sensor A is healthy" not in uploaded.text

        conversation = client.post(
            "/api/v1/conversations",
            json={"title": "附件工具测试"},
            headers=headers,
        )
        conversation_id = conversation.json()["data"]["id"]
        submitted = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                "content": "总结附件",
                "client_message_id": f"attachment-{uuid.uuid4().hex}",
                "attachment_ids": [attachment_id],
                "tool_mode": "none",
                "mcp_server_ids": [],
            },
            headers=headers,
        )
        assert submitted.status_code == 202
        run_id = submitted.json()["data"]["run_id"]
        # Dispatcher 异步执行：等待终态后再断言捕获内容
        for _ in range(100):
            detail = client.get(f"/api/v1/agent-runs/{run_id}").json()["data"]
            if detail["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)
        assert detail["status"] == "completed"

    runtime_messages = captured["messages"]
    assert isinstance(runtime_messages, list)
    assert "[附件：context.md]" in runtime_messages[-1]["content"]
    assert "Sensor A is healthy." in runtime_messages[-1]["content"]
    assert captured["mcp_servers"] == []

    async def read_attachment():
        async with SessionFactory() as db:
            return await db.get(Attachment, attachment_id)

    attachment = asyncio.run(read_attachment())
    assert attachment is not None
    assert attachment.message_id is not None


def test_conversation_run_flow() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        assert login.status_code == 200
        csrf = login.json()["data"]["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        created = client.post("/api/v1/conversations", json={"title": "测试对话"}, headers=headers)
        assert created.status_code == 201
        conversation_id = created.json()["data"]["id"]

        submitted = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "你好，小yi", "client_message_id": "test-message-1"},
            headers=headers,
        )
        assert submitted.status_code == 202
        run_id = submitted.json()["data"]["run_id"]

        for _ in range(30):
            run = client.get(f"/api/v1/agent-runs/{run_id}")
            if run.json()["data"]["status"] == "completed":
                break
            time.sleep(0.05)
        assert run.json()["data"]["status"] == "completed"

        messages = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()["data"]["items"]] == ["user", "assistant"]

        replay = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "不会重复", "client_message_id": "test-message-1"},
            headers=headers,
        )
        assert replay.json()["data"] == {"run_id": run_id, "idempotent_replay": True}

        missing_csrf = client.delete(f"/api/v1/agent-runs/{run_id}")
        assert missing_csrf.status_code == 403

        deleted = client.delete(f"/api/v1/agent-runs/{run_id}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"deleted": True, "run_id": run_id}
        assert client.get(f"/api/v1/agent-runs/{run_id}").status_code == 404


def test_conversation_can_be_renamed_and_removed_from_history() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        headers = {"X-CSRF-Token": csrf}

        created = client.post(
            "/api/v1/conversations",
            json={"title": "旧标题"},
            headers=headers,
        )
        conversation_id = created.json()["data"]["id"]

        renamed = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            json={"title": "新标题"},
            headers=headers,
        )
        assert renamed.status_code == 200
        assert renamed.json()["data"]["title"] == "新标题"

        deleted = client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers,
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"deleted": True}

        listed = client.get("/api/v1/conversations")
        assert conversation_id not in {item["id"] for item in listed.json()["data"]["items"]}
        assert client.get(f"/api/v1/conversations/{conversation_id}/messages").status_code == 404


def test_admin_can_manage_mcp_configuration_without_exposing_credentials() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        key = f"test-{uuid.uuid4().hex[:8]}"
        created = client.post(
            "/api/v1/mcp-servers",
            json={
                "server_key": key,
                "name": "测试 MCP",
                "url": "http://127.0.0.1:9001/mcp",
                "purpose": "generic",
                "credential": "secret-token",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201
        body = created.json()["data"]
        assert body["credential_configured"] is True
        assert "secret-token" not in created.text

        server_id = body["id"]
        updated = client.patch(
            f"/api/v1/mcp-servers/{server_id}",
            json={"enabled": True},
            headers={"X-CSRF-Token": csrf},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["enabled"] is True


def test_operator_cannot_manage_mcp_servers() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "operator", "password": "operator123"}
        )
        assert login.status_code == 200
        response = client.get("/api/v1/mcp-servers")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_user_can_store_private_model_configuration() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "operator", "password": "operator123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        user_id = login.json()["data"]["user"]["id"]
        saved = client.put(
            "/api/v1/model-config",
            json={
                "provider_name": "自定义兼容服务",
                "base_url": "https://models.example.com/v1",
                "model_name": "example-chat-model",
                "api_mode": "chat_completions",
                "api_key": "private-model-key-1234",
                "enabled": True,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert saved.status_code == 200
        assert saved.json()["data"]["api_key_configured"] is True
        assert saved.json()["data"]["api_key_hint"] == "••••1234"
        assert "private-model-key-1234" not in saved.text

        async def read_config():
            async with SessionFactory() as db:
                return await db.scalar(
                    select(ModelConfiguration).where(ModelConfiguration.user_id == user_id)
                )

        config = asyncio.run(read_config())
        assert config is not None
        assert config.api_key_ciphertext != "private-model-key-1234"
        assert (
            decrypt_secret(config.api_key_ciphertext, get_settings().app_secret_key)
            == "private-model-key-1234"
        )


def test_admin_can_add_only_verified_fault_case(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        captured.update(arguments)
        assert tool_name == "add_verified_fault_case"
        return {
            "ok": True,
            "data": {"fault_id": "FTEST001", "verified": True, "indexed": True},
            "error": None,
        }

    monkeypatch.setattr("app.api.diagnosis.invoke_remote_tool", fake_invoke)

    async def seed_server() -> str:
        async with SessionFactory() as db:
            server = MCPServer(
                server_key=f"diagnosis-{uuid.uuid4().hex[:8]}",
                name="诊断测试服务",
                url="http://127.0.0.1:9001/mcp",
                purpose=MCPPurpose.IOT,
                enabled=True,
                connection_status="connected",
            )
            db.add(server)
            await db.flush()
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name="add_verified_fault_case",
                    model_alias=f"{server.server_key}__add_verified_fault_case",
                    enabled=True,
                    risk_policy=ToolRiskPolicy.APPROVAL_REQUIRED,
                )
            )
            await db.commit()
            return server.id

    server_id = asyncio.run(seed_server())
    payload = {
        "device_id": "ESP32_05",
        "fault_type": "mqtt_timeout",
        "fault_name": "MQTT 心跳超时",
        "symptoms": ["频繁掉线"],
        "logs": ["MQTT keep alive timeout"],
        "cause": "心跳配置异常",
        "solution": "检查 Keep Alive 与 Broker 超时",
        "verified": True,
    }

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        rejected = client.post(
            f"/api/v1/diagnosis-services/{server_id}/fault-cases",
            json={**payload, "verified": False},
            headers={"X-CSRF-Token": csrf},
        )
        assert rejected.status_code == 422

        response = client.post(
            f"/api/v1/diagnosis-services/{server_id}/fault-cases",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201
        assert response.json()["data"]["fault_id"] == "FTEST001"
        assert captured["verified"] is True
        assert captured["verified_by"] == "admin"


def test_unbound_attachment_can_be_deleted_then_is_gone() -> None:
    """WP-11 §9.3：上传成功但发送失败时，前端可显式删除未绑定附件。"""
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        uploaded = client.post(
            "/api/v1/attachments",
            files={"file": ("to-delete.txt", b"hello", "text/plain")},
            headers={"X-CSRF-Token": csrf},
        )
        assert uploaded.status_code == 201
        attachment_id = uploaded.json()["data"]["id"]

        deleted = client.delete(
            f"/api/v1/attachments/{attachment_id}", headers={"X-CSRF-Token": csrf}
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"]["deleted"] is True

        # 已删除后再删 → 404
        again = client.delete(
            f"/api/v1/attachments/{attachment_id}", headers={"X-CSRF-Token": csrf}
        )
        assert again.status_code == 404


def test_bound_attachment_cannot_be_deleted_via_endpoint() -> None:
    """已绑定消息的附件属于对话历史，端点不回收。"""
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
        )
        csrf = login.json()["data"]["csrf_token"]
        uploaded = client.post(
            "/api/v1/attachments",
            files={"file": ("bound.txt", b"keep", "text/plain")},
            headers={"X-CSRF-Token": csrf},
        )
        attachment_id = uploaded.json()["data"]["id"]

        async def bind():
            async with SessionFactory() as db:
                item = await db.get(Attachment, attachment_id)
                message = await db.scalar(select(Message).limit(1))
                if message is None:
                    conversation = Conversation(user_id=item.user_id, title="绑定删除测试")
                    db.add(conversation)
                    await db.flush()
                    message = Message(conversation_id=conversation.id, role="user", content="m")
                    db.add(message)
                    await db.flush()
                item.message_id = message.id
                await db.commit()

        asyncio.run(bind())

        deleted = client.delete(
            f"/api/v1/attachments/{attachment_id}", headers={"X-CSRF-Token": csrf}
        )
        assert deleted.status_code == 404
