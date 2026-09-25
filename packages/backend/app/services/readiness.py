"""就绪探针（specs WP-12 / §11.1、§16.1、§16.2）。

探针契约：status ∈ ready|degraded|not_ready；checks 按组件报告
ok|degraded|failed 与稳定错误码。必需组件失败 → not_ready（HTTP 503）；
仅可选组件失败 → degraded（HTTP 200）。/live 只验证进程存活，恒 200。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text

from app.config import Settings, get_settings
from app.migrations import RevisionStatus, check_revision
from app.models import MCPServer

logger = logging.getLogger("xiaoyi.readiness")

DB_BEHIND = "DATABASE_SCHEMA_BEHIND"
DB_AHEAD = "DATABASE_SCHEMA_AHEAD"
DB_EMPTY = "DATABASE_NOT_INITIALIZED"
DISPATCHER_NOT_RUNNING = "DISPATCHER_NOT_RUNNING"
MCP_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


@dataclass
class ProbeReport:
    status: str  # ready | degraded | not_ready
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def http_status(self) -> int:
        return 503 if self.status == "not_ready" else 200


def _required_failed(checks: dict[str, dict[str, Any]], name: str) -> bool:
    return checks.get(name, {}).get("status") == "failed"


async def probe_readiness(
    *,
    dispatcher: Any = None,
    settings: Settings | None = None,
) -> ProbeReport:
    """执行就绪检查：数据库、schema 版本、Dispatcher、必需 MCP 服务。"""
    settings = settings or get_settings()
    checks: dict[str, dict[str, Any]] = {}

    # 1. 数据库连通性
    try:
        from app.db import SessionFactory

        async with SessionFactory() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "error_code": None}
    except Exception as exc:
        logger.warning(
            "readiness database check failed",
            extra={"event": "readiness_check_failed", "error_code": DB_BEHIND},
        )
        checks["database"] = {
            "status": "failed",
            "error_code": "DEPENDENCY_UNAVAILABLE",
            "detail": str(exc)[:200],
        }

    # 2. schema 版本
    try:
        revision = check_revision()
    except Exception:
        revision = None
        checks["schema"] = {"status": "failed", "error_code": "DEPENDENCY_UNAVAILABLE"}
    else:
        if revision == RevisionStatus.OK:
            checks["schema"] = {"status": "ok", "error_code": None}
        elif revision == RevisionStatus.AHEAD:
            checks["schema"] = {"status": "failed", "error_code": DB_AHEAD}
        elif revision == RevisionStatus.BEHIND:
            checks["schema"] = {"status": "failed", "error_code": DB_BEHIND}
        else:
            checks["schema"] = {"status": "failed", "error_code": DB_EMPTY}

    # 3. Dispatcher（dispatcher 模式下为必需组件）
    if settings.run_dispatcher_mode == "dispatcher":
        running = dispatcher is not None and getattr(dispatcher, "running", False)
        checks["run_dispatcher"] = {
            "status": "ok" if running else "failed",
            "error_code": None if running else DISPATCHER_NOT_RUNNING,
        }

    # 4. 必需 MCP 服务（未声明必需依赖时不检查；可选 MCP 故障表现为 degraded）
    required_keys = settings.mcp_required_server_keys
    if required_keys:
        try:
            from app.db import SessionFactory as _SF

            async with _SF() as db:
                rows = (
                    await db.scalars(
                        select(MCPServer).where(
                            MCPServer.deleted_at.is_(None),
                            MCPServer.server_key.in_(required_keys),
                        )
                    )
                ).all()
            by_key = {row.server_key: row for row in rows}
            for key in required_keys:
                server = by_key.get(key)
                connected = (
                    server is not None
                    and server.enabled
                    and server.connection_status == "connected"
                )
                checks[f"mcp:{key}"] = {
                    "status": "ok" if connected else "failed",
                    "error_code": None if connected else MCP_UNAVAILABLE,
                }
        except Exception as exc:
            for key in required_keys:
                checks[f"mcp:{key}"] = {
                    "status": "failed",
                    "error_code": MCP_UNAVAILABLE,
                    "detail": str(exc)[:200],
                }

    # 必需组件失败 → not_ready；无可失败但有降级 → degraded
    status = "ready"
    for check in checks.values():
        if check["status"] == "failed":
            status = "not_ready"
            break
    if status == "ready" and any(c["status"] == "degraded" for c in checks.values()):
        status = "degraded"
    return ProbeReport(status=status, checks=checks)
