import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionFactory
from app.main import app
from app.models import (
    AgentRun,
    MCPPurpose,
    MCPServer,
    MCPTool,
    RunEvent,
    RunStatus,
    ToolRiskPolicy,
    User,
)
from app.services import harness_native
from app.services.harness import stop_connection_runs


def activate(client, instance="native-test", username="admin", password="admin123"):
    login = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    ).json()["data"]
    headers = {"X-CSRF-Token": login["csrf_token"]}
    assert (
        client.post(f"/api/v1/harness/connections/{instance}/activate", headers=headers).status_code
        == 200
    )
    return {**headers, "X-Xiaoyi-Harness-Instance": instance}


async def seed_tools():
    async with SessionFactory() as db:
        server = MCPServer(
            server_key="native-fixture",
            name="Native fixture",
            url="http://iot-mcp:9000/mcp",
            purpose=MCPPurpose.IOT,
            enabled=True,
            connection_status="connected",
        )
        db.add(server)
        await db.flush()
        specs = [
            ("list_devices", ToolRiskPolicy.READ_ONLY),
            ("diagnose_fault", ToolRiskPolicy.READ_ONLY),
            ("execute_device_action", ToolRiskPolicy.PROPOSAL_ONLY),
            ("decide_remediation_proposal", ToolRiskPolicy.APPROVAL_REQUIRED),
            ("disabled_tool", ToolRiskPolicy.DISABLED),
        ]
        ids = {}
        for name, policy in specs:
            tool = MCPTool(
                server_id=server.id,
                original_name=name,
                model_alias=f"fixture__{name}",
                enabled=True,
                risk_policy=policy,
                input_schema={"type": "object", "properties": {}},
            )
            db.add(tool)
            await db.flush()
            ids[name] = tool.id
        await db.commit()
    return ids


def test_native_main_chat_never_starts_backend_model_and_keeps_approval_and_lease_fences(
    monkeypatch,
):
    with TestClient(app) as client:
        headers = activate(client)
        ids = asyncio.run(seed_tools())
        monkeypatch.setattr(
            app.state.run_dispatcher,
            "notify",
            lambda *_: (_ for _ in ()).throw(AssertionError("no dispatch")),
        )
        remote_calls = []

        async def invoke(server, settings, name, arguments, **kwargs):
            remote_calls.append((name, arguments))
            if name == "diagnose_fault":
                return {
                    "ok": True,
                    "data": {"device_id": "ESP32_01", "diagnosis_id": "DIA_20260930_1234ABCD"},
                }
            return {"ok": True, "data": {"devices": ["ESP32_01"]}}

        monkeypatch.setattr(harness_native, "invoke_remote_tool", invoke)
        catalog = client.get("/api/v1/harness/native/tools", headers=headers).json()["data"][
            "items"
        ]
        assert {s["original_name"] for s in catalog} == {
            "list_devices",
            "diagnose_fault",
            "execute_device_action",
        }
        run = client.post(
            "/api/v1/harness/native/runs", headers=headers, json={"context_key": "main-chat:1"}
        ).json()["data"]["run_id"]
        path = f"/api/v1/harness/native/runs/{run}/call"

        def call(name, args, key):
            return client.post(
                path,
                headers=headers,
                json={"tool_id": ids[name], "arguments": args, "call_id": key},
            )

        assert call("list_devices", {}, "call-1").json()["data"]["result"]["data"]["devices"] == [
            "ESP32_01"
        ]
        assert call("list_devices", {}, "call-1").status_code == 409
        assert call("decide_remediation_proposal", {}, "call-2").status_code == 403
        assert call("execute_device_action", {"device_id": "ESP32_01"}, "call-3").status_code == 409
        assert (
            call(
                "diagnose_fault", {"device_id": "ESP32_01", "query": "diagnose"}, "call-4"
            ).status_code
            == 200
        )

        async def state():
            async with SessionFactory() as db:
                item = await db.get(AgentRun, run)
                events = (await db.scalars(select(RunEvent).where(RunEvent.run_id == run))).all()
                return item, events

        item, events = asyncio.run(state())
        assert item.runtime_state["harness_native"] is True
        assert item.status == RunStatus.RUNNING
        assert any(e.event_type == "tool.finished" for e in events)
        assert (
            client.post(
                "/api/v1/harness/connections/native-test/deactivate", headers=headers
            ).status_code
            == 200
        )
        assert call("list_devices", {}, "call-5").status_code == 409
        assert asyncio.run(state())[0].status == RunStatus.FAILED
        assert [c[0] for c in remote_calls] == ["list_devices", "diagnose_fault"]


def test_disabling_native_connection_cancels_inflight_tool(monkeypatch):
    with TestClient(app) as client:
        headers = activate(client)
        ids = asyncio.run(seed_tools())
        run_id = client.post(
            "/api/v1/harness/native/runs", headers=headers, json={"context_key": "cancel:1"}
        ).json()["data"]["run_id"]

        async def check():
            entered = asyncio.Event()

            async def invoke(*args, **kwargs):
                entered.set()
                await asyncio.Event().wait()

            monkeypatch.setattr(harness_native, "invoke_remote_tool", invoke)
            async with SessionFactory() as db:
                user = await db.scalar(select(User).where(User.username == "admin"))
            task = asyncio.create_task(
                harness_native.execute_native_tool(
                    app, user, "native-test", run_id, ids["list_devices"], {}, "cancel-call"
                )
            )
            await asyncio.wait_for(entered.wait(), 5)
            stopped = await stop_connection_runs(app, user.id, "native-test")
            assert stopped["stopped_run_ids"] == [run_id]
            assert task.cancelled()
            assert run_id not in app.state.harness_native_tasks
            async with SessionFactory() as db:
                run = await db.get(AgentRun, run_id)
                assert run.status == RunStatus.FAILED
                assert run.error_code == "RUN_STOPPED"

        asyncio.run(check())


def test_native_runs_are_owned_and_close_is_idempotent():
    with TestClient(app) as client, TestClient(app) as other:
        headers = activate(client)
        other_headers = activate(other, username="operator", password="operator123")
        run = client.post(
            "/api/v1/harness/native/runs", headers=headers, json={"context_key": "main-chat:1"}
        ).json()["data"]["run_id"]
        assert (
            client.post(
                "/api/v1/harness/native/runs", headers=headers, json={"context_key": "main-chat:1"}
            ).json()["data"]["run_id"]
            == run
        )
        path = f"/api/v1/harness/native/runs/{run}/close"
        assert other.post(path, headers=other_headers, json={}).status_code == 404
        assert client.post(path, headers=headers, json={}).status_code == 200
        assert client.post(path, headers=headers, json={}).status_code == 200
        assert (
            client.post(
                path, headers={"X-Xiaoyi-Harness-Instance": "native-test"}, json={}
            ).status_code
            == 403
        )
