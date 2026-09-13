import asyncio
import uuid

from fastapi.testclient import TestClient

from app.api.knowledge import MAX_KNOWLEDGE_CHARS
from app.db import SessionFactory
from app.main import app
from app.migrations import upgrade_to_head
from app.models import MCPPurpose, MCPServer, MCPTool, ToolRiskPolicy


def _login(client) -> str:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return login.json()["data"]["csrf_token"]


def _seed_server() -> str:
    upgrade_to_head()

    async def seed() -> str:
        async with SessionFactory() as db:
            server = MCPServer(
                server_key=f"knowledge-{uuid.uuid4().hex[:8]}",
                name="知识测试服务",
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
                    original_name="ingest_knowledge_text",
                    model_alias=f"{server.server_key}__ingest_knowledge_text",
                    enabled=True,
                    risk_policy=ToolRiskPolicy.APPROVAL_REQUIRED,
                )
            )
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name="list_knowledge_documents",
                    model_alias=f"{server.server_key}__list_knowledge_documents",
                    enabled=True,
                    risk_policy=ToolRiskPolicy.READ_ONLY,
                )
            )
            db.add(
                MCPTool(
                    server_id=server.id,
                    original_name="delete_knowledge_document",
                    model_alias=f"{server.server_key}__delete_knowledge_document",
                    enabled=True,
                    risk_policy=ToolRiskPolicy.APPROVAL_REQUIRED,
                )
            )
            await db.commit()
            return server.id

    return asyncio.run(seed())


def test_upload_knowledge_document_ingests_via_mcp(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        captured["tool_name"] = tool_name
        captured.update(arguments)
        return {
            "ok": True,
            "data": {
                "source": arguments["source"],
                "document_id": arguments["document_id"],
                "chunk_count": 2,
                "mysql_saved": True,
                "vector_indexed": True,
                "sync_status": "complete",
            },
            "error": None,
        }

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fake_invoke)
    server_id = _seed_server()

    with TestClient(app) as client:
        csrf = _login(client)
        rejected = client.post(
            "/api/v1/knowledge-documents",
            files={"file": ("notes.docx", b"binary", "application/octet-stream")},
            data={"source": "mqtt_docs"},
            headers={"X-CSRF-Token": csrf},
        )
        assert rejected.status_code == 415

        too_long = client.post(
            "/api/v1/knowledge-documents",
            files={"file": ("big.md", ("x" * (MAX_KNOWLEDGE_CHARS + 1)).encode(), "text/markdown")},
            data={"source": "mqtt_docs"},
            headers={"X-CSRF-Token": csrf},
        )
        assert too_long.status_code == 413
        assert too_long.json()["error"]["code"] == "KNOWLEDGE_TEXT_TOO_LARGE"

        response = client.post(
            "/api/v1/knowledge-documents",
            files={
                "file": ("mqtt guide.md", "# MQTT 指南\n\n保持心跳。".encode(), "text/markdown")
            },
            data={"source": "mqtt_docs", "service_id": server_id},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["chunk_count"] == 2
        assert data["vector_indexed"] is True
        assert captured["tool_name"] == "ingest_knowledge_text"
        # 文件名含空格仍可作为合法 document_id；标题从文件名推导
        assert captured["title"] == "mqtt guide"
        assert captured["source"] == "mqtt_docs"


def test_upload_requires_ingest_tool_policy(monkeypatch) -> None:
    async def fake_invoke(*_args, **_kwargs):  # pragma: no cover - 不应被调用
        raise AssertionError("invoke_remote_tool should not run")

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fake_invoke)

    upgrade_to_head()

    async def seed() -> str:
        async with SessionFactory() as db:
            server = MCPServer(
                server_key=f"knowledge-disabled-{uuid.uuid4().hex[:8]}",
                name="未批准工具服务",
                url="http://127.0.0.1:9001/mcp",
                purpose=MCPPurpose.IOT,
                enabled=True,
                connection_status="connected",
            )
            db.add(server)
            await db.commit()
            return server.id

    server_id = asyncio.run(seed())

    with TestClient(app) as client:
        csrf = _login(client)
        response = client.post(
            "/api/v1/knowledge-documents",
            files={"file": ("doc.md", "内容".encode(), "text/markdown")},
            data={"source": "mqtt_docs", "service_id": server_id},
            headers={"X-CSRF-Token": csrf},
        )
        # WP-09：策略不符在能力路由阶段即拒绝（MISMATCH），不向远端发起调用
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MCP_CAPABILITY_MISMATCH"


def test_list_knowledge_documents_calls_read_only_tool(monkeypatch) -> None:
    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        assert tool_name == "list_knowledge_documents"
        assert arguments == {}
        return {
            "ok": True,
            "data": {"items": [], "total": 0, "limit": 100, "offset": 0},
            "error": None,
        }

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fake_invoke)
    server_id = _seed_server()

    with TestClient(app) as client:
        _login(client)
        response = client.get("/api/v1/knowledge-documents", params={"service_id": server_id})
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0


def test_delete_knowledge_document_calls_delete_tool(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_invoke(_server, _settings, tool_name, arguments, **_kwargs):
        captured["tool_name"] = tool_name
        captured.update(arguments)
        return {
            "ok": True,
            "data": {
                "source": arguments["source"],
                "document_id": arguments["document_id"],
                "deleted_chunks": 2,
                "mysql_saved": True,
                "vector_deleted": True,
                "sync_status": "complete",
            },
            "error": None,
            "trace_id": "trace-test-1234",
        }

    monkeypatch.setattr("app.api.knowledge.invoke_remote_tool", fake_invoke)
    server_id = _seed_server()

    with TestClient(app) as client:
        csrf = _login(client)
        response = client.delete(
            "/api/v1/knowledge-documents/mqtt_docs/modbus-sensor-diagnosis",
            headers={"X-CSRF-Token": csrf},
            params={"service_id": server_id},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_chunks"] == 2
        assert data["trace_id"]
        assert captured["tool_name"] == "delete_knowledge_document"

        forbidden = client.delete(
            "/api/v1/knowledge-documents/mqtt_docs/x", params={"service_id": server_id}
        )
        assert forbidden.status_code == 403
