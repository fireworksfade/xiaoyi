from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import AdminUser, CsrfProtected, Db
from app.config import get_settings
from app.models import MCPServer, MCPTool, MCPPurpose, ToolRiskPolicy
from app.schemas import VerifiedFaultCaseCreate
from app.services.mcp_catalog import invoke_remote_tool
from app.services.operations import add_audit_log


router = APIRouter(prefix="/diagnosis-services", tags=["IoT diagnosis"])


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


async def active_diagnosis_server(db: Db, service_id: str) -> MCPServer:
    server = await db.scalar(
        select(MCPServer).where(
            MCPServer.id == service_id,
            MCPServer.purpose == MCPPurpose.IOT,
            MCPServer.enabled.is_(True),
            MCPServer.connection_status == "connected",
            MCPServer.deleted_at.is_(None),
        )
    )
    if not server:
        raise HTTPException(status_code=503, detail="MCP_UNAVAILABLE")
    return server


async def require_verified_case_tool(db: Db, server_id: str) -> None:
    tool = await db.scalar(
        select(MCPTool).where(
            MCPTool.server_id == server_id,
            MCPTool.original_name == "add_verified_fault_case",
            MCPTool.enabled.is_(True),
            MCPTool.risk_policy == ToolRiskPolicy.APPROVAL_REQUIRED,
        )
    )
    if not tool:
        raise HTTPException(status_code=409, detail="VERIFIED_CASE_TOOL_NOT_APPROVED")


def unwrap(result: dict[str, object]) -> object:
    if result.get("ok") is True:
        return result.get("data")
    error = result.get("error")
    code = error.get("code") if isinstance(error, dict) else "MCP_TOOL_FAILED"
    raise HTTPException(status_code=422, detail=str(code))


@router.post("/{service_id}/fault-cases", status_code=status.HTTP_201_CREATED)
async def add_verified_fault_case(
    service_id: str,
    payload: VerifiedFaultCaseCreate,
    request: Request,
    db: Db,
    admin: AdminUser,
    _: CsrfProtected,
) -> dict[str, object]:
    if payload.verified is not True:
        raise HTTPException(status_code=422, detail="CASE_NOT_VERIFIED")
    server = await active_diagnosis_server(db, service_id)
    await require_verified_case_tool(db, server.id)
    arguments = payload.model_dump()
    arguments["verified_by"] = admin.username
    try:
        result = await invoke_remote_tool(
            server,
            get_settings(),
            "add_verified_fault_case",
            arguments,
            read_only=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    item = unwrap(result)
    fault_id = item.get("fault_id") if isinstance(item, dict) else None
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="verified_fault_case.created",
        resource_type="fault_case",
        resource_id=str(fault_id) if fault_id else None,
        request_id=request.state.request_id,
        details={"server_id": server.id, "device_id": payload.device_id},
    )
    await db.commit()
    return envelope(request, item)
