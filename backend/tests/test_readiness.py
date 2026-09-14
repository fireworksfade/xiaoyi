"""就绪探针测试（specs WP-12 / §11.1、§16.1、§16.7）。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services import readiness


def _settings(**overrides) -> Settings:
    base = Settings(_env_file=None)
    values = {"run_dispatcher_mode": base.run_dispatcher_mode, "mcp_required_server_keys": []}
    values.update(overrides)
    return SimpleNamespace(**values)


class _BrokenSession:
    def __call__(self):
        raise RuntimeError("db down")

    async def __aenter__(self):  # pragma: no cover
        raise RuntimeError("db down")

    async def __aexit__(self, *args):
        return False


async def test_healthy_probe_is_ready() -> None:
    class _Running:
        running = True

    report = await readiness.probe_readiness(
        dispatcher=_Running(),
        settings=_settings(run_dispatcher_mode="dispatcher"),
    )

    assert report.status == "ready"
    assert report.checks["database"]["status"] == "ok"
    assert report.checks["schema"]["status"] == "ok"
    assert report.checks["run_dispatcher"]["status"] == "ok"
    assert report.http_status() == 200


async def test_dispatcher_not_running_fails_ready(monkeypatch) -> None:
    report = await readiness.probe_readiness(
        dispatcher=None,
        settings=_settings(run_dispatcher_mode="dispatcher"),
    )

    assert report.status == "not_ready"
    assert report.checks["run_dispatcher"]["error_code"] == readiness.DISPATCHER_NOT_RUNNING
    assert report.http_status() == 503


async def test_database_failure_is_not_ready(monkeypatch) -> None:
    # readiness 内部在调用时从 app.db 解析 SessionFactory，替换源即可生效
    import app.db as app_db

    monkeypatch.setattr(app_db, "SessionFactory", _BrokenSession())

    report = await readiness.probe_readiness(
        dispatcher=None,
        settings=_settings(run_dispatcher_mode="legacy"),
    )

    assert report.status == "not_ready"
    assert report.checks["database"]["status"] == "failed"
    assert report.checks["database"]["error_code"] == "DEPENDENCY_UNAVAILABLE"


async def test_schema_ahead_and_behind_reject_ready(monkeypatch) -> None:
    from app.migrations import RevisionStatus

    monkeypatch.setattr(readiness, "check_revision", lambda: RevisionStatus.AHEAD)
    ahead = await readiness.probe_readiness(
        dispatcher=None, settings=_settings(run_dispatcher_mode="legacy")
    )
    assert ahead.checks["schema"] == {"status": "failed", "error_code": "DATABASE_SCHEMA_AHEAD"}

    monkeypatch.setattr(readiness, "check_revision", lambda: RevisionStatus.BEHIND)
    behind = await readiness.probe_readiness(
        dispatcher=None, settings=_settings(run_dispatcher_mode="legacy")
    )
    assert behind.checks["schema"]["error_code"] == "DATABASE_SCHEMA_BEHIND"
    assert behind.status == "not_ready"


async def test_required_mcp_disconnected_blocks_ready() -> None:
    # 未声明必需依赖 → 不检查任何 MCP，离线服务不影响探针
    optional = await readiness.probe_readiness(
        dispatcher=None, settings=_settings(run_dispatcher_mode="legacy")
    )
    assert not any(name.startswith("mcp:") for name in optional.checks)

    # 声明为必需但服务不存在/离线 → not_ready
    report = await readiness.probe_readiness(
        dispatcher=None,
        settings=_settings(
            run_dispatcher_mode="legacy", mcp_required_server_keys=["missing-service"]
        ),
    )
    assert report.status == "not_ready"
    assert report.checks["mcp:missing-service"]["status"] == "failed"
    assert report.checks["mcp:missing-service"]["error_code"] == "DEPENDENCY_UNAVAILABLE"


async def test_legacy_mode_without_dispatcher_is_ready() -> None:
    report = await readiness.probe_readiness(
        dispatcher=None, settings=_settings(run_dispatcher_mode="legacy")
    )
    assert "run_dispatcher" not in report.checks  # legacy 模式不检查 Dispatcher
    assert report.status == "ready"


def test_live_and_ready_http_endpoints() -> None:
    with TestClient(app) as client:
        live = client.get("/live")
        assert live.status_code == 200
        assert live.json()["data"]["status"] == "alive"

        ready = client.get("/ready")
        assert ready.status_code == 200
        body = ready.json()["data"]
        assert body["status"] in {"ready", "degraded"}
        assert body["checks"]["database"]["status"] == "ok"

        # 兼容端点保持存活语义
        health = client.get("/health")
        assert health.status_code == 200


def test_metrics_endpoint_exposes_counters() -> None:
    with TestClient(app) as client:
        client.get("/api/v1/conversations")
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        body = metrics.text
        assert "xiaoyi_http_requests_total" in body
