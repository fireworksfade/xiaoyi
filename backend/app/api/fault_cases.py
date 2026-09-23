from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AdminUser, CsrfProtected, CurrentUser, Db
from app.api.knowledge import call_tool, envelope
from app.config import get_settings
from app.models import MCPTool, ToolRiskPolicy
from app.services.mcp_capabilities import resolve_mcp_server
from app.services.mcp_catalog import invoke_remote_tool
from app.services.operations import add_audit_log

router = APIRouter(prefix="/fault-cases", tags=["Fault cases"])

LIST_TOOL_NAME = "list_fault_cases"
DELETE_TOOL_NAME = "delete_fault_case"
LIFECYCLE_TOOL_NAME = "update_fault_case_lifecycle"


class LifecycleUpdate(BaseModel):
    lifecycle_status: str = Field(pattern="^(candidate|verified|trusted|deprecated|invalid)$")
    reason: str | None = Field(default=None, max_length=1000)


async def require_delete_tool(db: Db, server_id: str) -> None:
    tool = await db.scalar(
        select(MCPTool).where(
            MCPTool.server_id == server_id,
            MCPTool.original_name == DELETE_TOOL_NAME,
            MCPTool.enabled.is_(True),
            MCPTool.risk_policy == ToolRiskPolicy.APPROVAL_REQUIRED,
        )
    )
    if not tool:
        raise HTTPException(status_code=409, detail="FAULT_CASE_DELETE_TOOL_NOT_APPROVED")


@router.get("")
async def list_fault_cases(
    request: Request,
    db: Db,
    user: CurrentUser,
    service_id: str = "",
    device_type: str = "",
    limit: int = 50,
    offset: int = 0,
    lifecycle_status: str = "",
    cluster_id: str = "",
    fault_type: str = "",
    min_reliability: float | None = None,
) -> dict[str, object]:
    _, item, _trace = await call_tool(
        db,
        service_id or None,
        LIST_TOOL_NAME,
        {
            "device_type": device_type or None,
            "limit": max(1, min(limit, 200)),
            "offset": max(0, offset),
            "lifecycle_status": lifecycle_status or None,
            "cluster_id": cluster_id or None,
            "fault_type": fault_type or None,
            "min_reliability": min_reliability,
        },
        read_only=True,
        request_id=request.state.request_id,
    )
    return envelope(request, item)


@router.delete("/{fault_id}", status_code=status.HTTP_200_OK)
async def remove_fault_case(
    fault_id: str,
    request: Request,
    db: Db,
    admin: AdminUser,
    _: CsrfProtected,
    service_id: str = "",
) -> dict[str, object]:
    server = await resolve_mcp_server(
        db,
        required_tools={DELETE_TOOL_NAME},
        explicit_server_id=service_id or None,
        require_policy={DELETE_TOOL_NAME: ToolRiskPolicy.APPROVAL_REQUIRED},
    )
    try:
        result = await invoke_remote_tool(
            server,
            get_settings(),
            DELETE_TOOL_NAME,
            {"fault_id": fault_id},
            read_only=False,
            extra_headers={"X-Request-Id": request.state.request_id},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    if result.get("ok") is not True:
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else "MCP_TOOL_FAILED"
        raise HTTPException(status_code=422, detail=str(code))
    item = result.get("data")
    trace_id = result.get("trace_id")
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="fault_case.deleted",
        resource_type="fault_case",
        resource_id=fault_id,
        request_id=request.state.request_id,
        details={"server_id": server.id, "trace_id": trace_id},
    )
    await db.commit()
    return envelope(request, {**(item if isinstance(item, dict) else {}), "trace_id": trace_id})


@router.patch("/{fault_id}/lifecycle")
async def update_fault_case_lifecycle(
    fault_id: str,
    payload: LifecycleUpdate,
    request: Request,
    db: Db,
    admin: AdminUser,
    _: CsrfProtected,
    service_id: str = "",
) -> dict[str, object]:
    server = await resolve_mcp_server(
        db,
        required_tools={LIFECYCLE_TOOL_NAME},
        explicit_server_id=service_id or None,
        require_policy={LIFECYCLE_TOOL_NAME: ToolRiskPolicy.APPROVAL_REQUIRED},
    )
    try:
        result = await invoke_remote_tool(
            server,
            get_settings(),
            LIFECYCLE_TOOL_NAME,
            {
                "fault_id": fault_id,
                "lifecycle_status": payload.lifecycle_status,
                "reason": payload.reason,
            },
            read_only=False,
            extra_headers={"X-Request-Id": request.state.request_id},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    if result.get("ok") is not True:
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else "MCP_TOOL_FAILED"
        raise HTTPException(status_code=422, detail=str(code))
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="fault_case.lifecycle_changed",
        resource_type="fault_case",
        resource_id=fault_id,
        request_id=request.state.request_id,
        details={"lifecycle_status": payload.lifecycle_status, "server_id": server.id},
    )
    await db.commit()
    return envelope(request, result.get("data"))
