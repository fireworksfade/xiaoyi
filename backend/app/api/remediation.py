from fastapi import APIRouter, HTTPException, Request

from app.api.deps import AdminUser, CsrfProtected, CurrentUser, Db
from app.config import get_settings
from app.models import MCPServer, ToolRiskPolicy
from app.schemas import RemediationDecisionCreate
from app.services.mcp_capabilities import resolve_mcp_server
from app.services.mcp_catalog import invoke_remote_tool
from app.services.operations import add_audit_log

router = APIRouter(prefix="/remediation-proposals", tags=["IoT remediation"])


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


async def active_control_server(db: Db) -> MCPServer:
    """按能力路由选择 IoT Control MCP（WP-09）：必须具备审批决策工具。"""
    return await resolve_mcp_server(
        db,
        required_tools={"decide_remediation_proposal"},
        default_kind="control",
        require_policy={"decide_remediation_proposal": ToolRiskPolicy.APPROVAL_REQUIRED},
    )


async def call_control_tool(db: Db, tool_name: str, arguments: dict[str, object]) -> object:
    server = await active_control_server(db)
    try:
        result = await invoke_remote_tool(
            server,
            get_settings(),
            tool_name,
            arguments,
            read_only=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    if result.get("ok") is not True:
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else "MCP_TOOL_FAILED"
        raise HTTPException(status_code=422, detail=str(code))
    return result.get("data")


@router.get("")
async def list_proposals(
    request: Request,
    db: Db,
    _: CurrentUser,
    proposal_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    if proposal_status not in (None, "pending", "approved", "rejected", "expired"):
        raise HTTPException(status_code=422, detail="INVALID_STATUS")
    data = await call_control_tool(
        db,
        "list_remediation_proposals",
        {
            "status": proposal_status,
            "limit": max(1, min(limit, 200)),
            "offset": max(0, offset),
        },
    )
    return envelope(request, data)


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: str, request: Request, db: Db, _: CurrentUser
) -> dict[str, object]:
    data = await call_control_tool(db, "get_action_result", {"proposal_id": proposal_id})
    if not isinstance(data, dict) or "proposal" not in data:
        raise HTTPException(status_code=404, detail="PROPOSAL_NOT_FOUND")
    return envelope(request, data)


@router.post("/{proposal_id}/decision")
async def decide_proposal(
    proposal_id: str,
    payload: RemediationDecisionCreate,
    request: Request,
    db: Db,
    admin: AdminUser,
    _: CsrfProtected,
) -> dict[str, object]:
    current = await call_control_tool(db, "get_action_result", {"proposal_id": proposal_id})
    proposal = current.get("proposal") if isinstance(current, dict) else None
    if not isinstance(proposal, dict):
        raise HTTPException(status_code=404, detail="PROPOSAL_NOT_FOUND")
    if proposal.get("status") != "pending":
        raise HTTPException(status_code=409, detail="PROPOSAL_NOT_PENDING")
    if proposal.get("version") != payload.expected_version:
        raise HTTPException(status_code=409, detail="VERSION_CONFLICT")

    server = await active_control_server(db)
    try:
        result = await invoke_remote_tool(
            server,
            get_settings(),
            "decide_remediation_proposal",
            {
                "proposal_id": proposal_id,
                "decision": payload.decision,
                "decided_by": admin.username,
                "expected_version": payload.expected_version,
            },
            read_only=False,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    if result.get("ok") is not True:
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else "MCP_TOOL_FAILED"
        raise HTTPException(status_code=422, detail=str(code))
    data = result.get("data")

    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action=f"remediation.{payload.decision}",
        resource_type="remediation_proposal",
        resource_id=proposal_id,
        request_id=request.state.request_id,
        details={
            "server_id": server.id,
            "device_id": proposal.get("device_id"),
            "action": proposal.get("action"),
        },
    )
    await db.commit()
    return envelope(request, data)
