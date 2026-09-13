from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import AdminUser, CsrfProtected, CurrentUser, Db
from app.api.knowledge import active_iot_server, call_tool, envelope
from app.config import get_settings
from app.models import MCPTool, ToolRiskPolicy
from app.services.mcp_catalog import invoke_remote_tool
from app.services.operations import add_audit_log

router = APIRouter(prefix="/fault-cases", tags=["Fault cases"])

LIST_TOOL_NAME = "list_fault_cases"
DELETE_TOOL_NAME = "delete_fault_case"


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
) -> dict[str, object]:
    _, item, _trace = await call_tool(
        db,
        service_id or None,
        LIST_TOOL_NAME,
        {
            "device_type": device_type or None,
            "limit": max(1, min(limit, 200)),
            "offset": max(0, offset),
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
    server = await active_iot_server(db, service_id or None)
    await require_delete_tool(db, server.id)
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
