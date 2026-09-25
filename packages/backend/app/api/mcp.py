from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminUser, CsrfProtected, Db
from app.config import get_settings
from app.models import MCPServer, MCPTool, ToolRiskPolicy, utc_now
from app.schemas import MCPServerCreate, MCPServerUpdate, MCPToolUpdate
from app.security import encrypt_secret
from app.services.mcp_catalog import fetch_remote_tools, refresh_tool_catalog, validate_mcp_url
from app.services.operations import add_audit_log

router = APIRouter(prefix="/mcp-servers", tags=["MCP services"])


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def server_view(server: MCPServer, tool_count: int | None = None) -> dict[str, object]:
    return {
        "id": server.id,
        "server_key": server.server_key,
        "name": server.name,
        "url": server.url,
        "purpose": server.purpose.value,
        "enabled": server.enabled,
        "connection_status": server.connection_status,
        "last_error": server.last_error,
        "credential_configured": bool(server.credential_ciphertext),
        "config_version": server.config_version,
        "tools_version": server.tools_version,
        "tool_count": tool_count,
        "last_checked_at": server.last_checked_at.isoformat() if server.last_checked_at else None,
    }


def tool_view(tool: MCPTool) -> dict[str, object]:
    return {
        "id": tool.id,
        "original_name": tool.original_name,
        "model_alias": tool.model_alias,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "enabled": tool.enabled,
        "risk_policy": tool.risk_policy.value,
        "catalog_version": tool.catalog_version,
    }


async def active_server(db: Db, server_id: str) -> MCPServer:
    server = await db.scalar(
        select(MCPServer).where(MCPServer.id == server_id, MCPServer.deleted_at.is_(None))
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP_SERVER_NOT_FOUND")
    return server


@router.get("")
async def list_servers(
    request: Request,
    db: Db,
    _: AdminUser,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    criteria = MCPServer.deleted_at.is_(None)
    total = await db.scalar(select(func.count()).select_from(MCPServer).where(criteria))
    servers = list(
        (
            await db.scalars(
                select(MCPServer)
                .where(criteria)
                .order_by(MCPServer.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return envelope(
        request,
        {
            "items": [server_view(item) for item in servers],
            "page": page,
            "page_size": page_size,
            "total": total or 0,
        },
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_server(
    payload: MCPServerCreate,
    request: Request,
    db: Db,
    admin: AdminUser,
    __: CsrfProtected,
) -> dict[str, object]:
    settings = get_settings()
    try:
        url = validate_mcp_url(payload.url, settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    server = MCPServer(
        server_key=payload.server_key,
        name=payload.name,
        url=url,
        purpose=payload.purpose,
        credential_ciphertext=(
            encrypt_secret(payload.credential, settings.app_secret_key)
            if payload.credential
            else None
        ),
    )
    db.add(server)
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="mcp_server.created",
        resource_type="mcp_server",
        resource_id=server.id,
        request_id=request.state.request_id,
        details={
            "server_key": server.server_key,
            "purpose": server.purpose.value,
            "credential_configured": bool(payload.credential),
        },
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="MCP_SERVER_KEY_EXISTS") from exc
    await db.refresh(server)
    return envelope(request, server_view(server, 0))


@router.get("/{server_id}")
async def get_server(server_id: str, request: Request, db: Db, _: AdminUser) -> dict[str, object]:
    server = await active_server(db, server_id)
    count = await db.scalar(
        select(func.count()).select_from(MCPTool).where(MCPTool.server_id == server.id)
    )
    return envelope(request, server_view(server, count or 0))


@router.patch("/{server_id}")
async def update_server(
    server_id: str,
    payload: MCPServerUpdate,
    request: Request,
    db: Db,
    admin: AdminUser,
    __: CsrfProtected,
) -> dict[str, object]:
    settings = get_settings()
    server = await active_server(db, server_id)
    changes = payload.model_dump(exclude_unset=True)
    changed_fields = sorted(changes)
    was_enabled = server.enabled
    if "url" in changes:
        try:
            changes["url"] = validate_mcp_url(changes["url"], settings)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        server.connection_status = "unchecked"
    credential = changes.pop("credential", None)
    if credential is not None:
        server.credential_ciphertext = (
            encrypt_secret(credential, settings.app_secret_key) if credential else None
        )
    for key, value in changes.items():
        setattr(server, key, value)
    server.config_version += 1
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="mcp_server.updated",
        resource_type="mcp_server",
        resource_id=server.id,
        request_id=request.state.request_id,
        details={
            "changed_fields": changed_fields,
            "enabled_before": was_enabled,
            "enabled_after": server.enabled,
        },
    )
    await db.commit()
    return envelope(request, server_view(server))


@router.delete("/{server_id}")
async def delete_server(
    server_id: str,
    request: Request,
    db: Db,
    admin: AdminUser,
    __: CsrfProtected,
) -> dict[str, object]:
    server = await active_server(db, server_id)
    server.enabled = False
    server.deleted_at = utc_now()
    tools = list((await db.scalars(select(MCPTool).where(MCPTool.server_id == server.id))).all())
    for tool in tools:
        tool.enabled = False
        tool.risk_policy = ToolRiskPolicy.DISABLED
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="mcp_server.deleted",
        resource_type="mcp_server",
        resource_id=server.id,
        request_id=request.state.request_id,
        details={"disabled_tool_count": len(tools)},
    )
    await db.commit()
    return envelope(request, {"deleted": True})


@router.post("/{server_id}/test")
async def test_server(
    server_id: str,
    request: Request,
    db: Db,
    admin: AdminUser,
    __: CsrfProtected,
) -> dict[str, object]:
    server = await active_server(db, server_id)
    try:
        tools = await fetch_remote_tools(server, get_settings())
    except Exception as exc:
        server.connection_status = "failed"
        server.last_error = str(exc)[:1000]
        server.last_checked_at = utc_now()
        add_audit_log(
            db,
            actor_type="user",
            actor_id=admin.id,
            action="mcp_server.connection_failed",
            resource_type="mcp_server",
            resource_id=server.id,
            request_id=request.state.request_id,
            details={"error_code": "MCP_UNAVAILABLE"},
        )
        await db.commit()
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    server.connection_status = "connected"
    server.last_error = None
    server.last_checked_at = utc_now()
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="mcp_server.connection_tested",
        resource_type="mcp_server",
        resource_id=server.id,
        request_id=request.state.request_id,
        details={"connected": True, "tool_count": len(tools)},
    )
    await db.commit()
    return envelope(request, {"connected": True, "tool_count": len(tools)})


@router.post("/{server_id}/refresh-tools")
async def refresh_tools(
    server_id: str,
    request: Request,
    db: Db,
    admin: AdminUser,
    __: CsrfProtected,
) -> dict[str, object]:
    server = await active_server(db, server_id)
    try:
        tools = await refresh_tool_catalog(db, server, get_settings())
    except Exception as exc:
        server.connection_status = "failed"
        server.last_error = str(exc)[:1000]
        server.last_checked_at = utc_now()
        add_audit_log(
            db,
            actor_type="user",
            actor_id=admin.id,
            action="mcp_server.catalog_refresh_failed",
            resource_type="mcp_server",
            resource_id=server.id,
            request_id=request.state.request_id,
            details={"error_code": "MCP_UNAVAILABLE"},
        )
        await db.commit()
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="mcp_server.catalog_refreshed",
        resource_type="mcp_server",
        resource_id=server.id,
        request_id=request.state.request_id,
        details={"tool_count": len(tools), "tools_version": server.tools_version},
    )
    await db.commit()
    return envelope(
        request,
        {"items": [tool_view(item) for item in tools], "tools_version": server.tools_version},
    )


@router.get("/{server_id}/tools")
async def list_tools(server_id: str, request: Request, db: Db, _: AdminUser) -> dict[str, object]:
    server = await active_server(db, server_id)
    tools = list(
        (
            await db.scalars(
                select(MCPTool)
                .where(MCPTool.server_id == server.id)
                .order_by(MCPTool.original_name)
            )
        ).all()
    )
    return envelope(request, {"items": [tool_view(item) for item in tools]})


@router.patch("/{server_id}/tools/{tool_id}")
async def update_tool(
    server_id: str,
    tool_id: str,
    payload: MCPToolUpdate,
    request: Request,
    db: Db,
    admin: AdminUser,
    __: CsrfProtected,
) -> dict[str, object]:
    server = await active_server(db, server_id)
    tool = await db.scalar(
        select(MCPTool).where(MCPTool.id == tool_id, MCPTool.server_id == server.id)
    )
    if not tool:
        raise HTTPException(status_code=404, detail="MCP_TOOL_NOT_FOUND")
    if payload.enabled and payload.risk_policy == ToolRiskPolicy.DISABLED:
        raise HTTPException(status_code=422, detail="TOOL_POLICY_INVALID")
    tool.enabled = payload.enabled
    tool.risk_policy = payload.risk_policy if payload.enabled else ToolRiskPolicy.DISABLED
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="mcp_tool.policy_updated",
        resource_type="mcp_tool",
        resource_id=tool.id,
        request_id=request.state.request_id,
        details={
            "server_id": server.id,
            "enabled": tool.enabled,
            "risk_policy": tool.risk_policy.value,
        },
    )
    await db.commit()
    return envelope(request, tool_view(tool))
