import io
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pypdf import PdfReader
from sqlalchemy import select

from app.api.deps import AdminUser, CsrfProtected, CurrentUser, Db
from app.config import get_settings
from app.models import MCPTool, ToolRiskPolicy
from app.services.mcp_catalog import invoke_remote_tool
from app.services.operations import add_audit_log


router = APIRouter(prefix="/knowledge-documents", tags=["Knowledge documents"])

MAX_KNOWLEDGE_BYTES = 20 * 1024 * 1024
MAX_KNOWLEDGE_CHARS = 200_000
ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf"}
KNOWLEDGE_SOURCES = ("mqtt_docs", "wifi_docs", "sensor_docs", "device_docs")
DOCUMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
INGEST_TOOL_NAME = "ingest_knowledge_text"
LIST_TOOL_NAME = "list_knowledge_documents"
DELETE_TOOL_NAME = "delete_knowledge_document"


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("KNOWLEDGE_ENCODING_INVALID") from exc
    elif suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("KNOWLEDGE_PDF_INVALID") from exc
    else:
        raise ValueError("KNOWLEDGE_TYPE_NOT_ALLOWED")
    text = text.strip()
    if not text:
        raise ValueError("KNOWLEDGE_HAS_NO_TEXT")
    return text


def derive_document_id(filename: str) -> str:
    stem = Path(filename).stem.strip()
    if DOCUMENT_ID_PATTERN.match(stem):
        return stem
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"upload-{stamp}-{secrets.token_hex(3)}"


async def require_ingest_tool(db: Db, server_id: str) -> None:
    tool = await db.scalar(
        select(MCPTool).where(
            MCPTool.server_id == server_id,
            MCPTool.original_name == INGEST_TOOL_NAME,
            MCPTool.enabled.is_(True),
            MCPTool.risk_policy == ToolRiskPolicy.APPROVAL_REQUIRED,
        )
    )
    if not tool:
        raise HTTPException(status_code=409, detail="KNOWLEDGE_INGEST_TOOL_NOT_APPROVED")


async def active_iot_server(db: Db, service_id: str | None):
    from app.api.diagnosis import active_diagnosis_server

    if service_id:
        return await active_diagnosis_server(db, service_id)
    from app.models import MCPServer, MCPPurpose

    server = await db.scalar(
        select(MCPServer)
        .where(
            MCPServer.purpose == MCPPurpose.IOT,
            MCPServer.enabled.is_(True),
            MCPServer.connection_status == "connected",
            MCPServer.deleted_at.is_(None),
        )
        .order_by(MCPServer.created_at)
    )
    if not server:
        raise HTTPException(status_code=503, detail="MCP_UNAVAILABLE")
    return server


async def call_tool(
    db: Db,
    service_id: str | None,
    tool_name: str,
    arguments: dict,
    read_only: bool,
    require_approval: bool = False,
    request_id: str | None = None,
) -> tuple[object, object, str | None]:
    server = await active_iot_server(db, service_id)
    if require_approval:
        await require_ingest_tool(db, server.id)
    elif read_only:
        tool = await db.scalar(
            select(MCPTool).where(
                MCPTool.server_id == server.id,
                MCPTool.original_name == tool_name,
                MCPTool.enabled.is_(True),
            )
        )
        if not tool:
            raise HTTPException(status_code=409, detail="KNOWLEDGE_TOOL_NOT_ENABLED")
    extra_headers = {"X-Request-Id": request_id} if request_id else None
    try:
        result = await invoke_remote_tool(
            server,
            get_settings(),
            tool_name,
            arguments,
            read_only=read_only,
            extra_headers=extra_headers,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP_UNAVAILABLE") from exc
    if result.get("ok") is not True:
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else "MCP_TOOL_FAILED"
        raise HTTPException(status_code=422, detail=str(code))
    trace_id = result.get("trace_id")
    return server, result.get("data"), str(trace_id) if trace_id else None


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_knowledge_document(
    request: Request,
    db: Db,
    admin: AdminUser,
    _: CsrfProtected,
    file: UploadFile = File(),
    source: str = Form("mqtt_docs"),
    document_id: str = Form(""),
    title: str = Form(""),
    device_type: str = Form("ESP32"),
    service_id: str = Form(""),
) -> dict[str, object]:
    if source not in KNOWLEDGE_SOURCES:
        raise HTTPException(status_code=422, detail="KNOWLEDGE_SOURCE_INVALID")
    safe_name = Path(file.filename or "").name
    if not safe_name or Path(safe_name).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="KNOWLEDGE_TYPE_NOT_ALLOWED")
    content = await file.read(MAX_KNOWLEDGE_BYTES + 1)
    if len(content) > MAX_KNOWLEDGE_BYTES:
        raise HTTPException(status_code=413, detail="KNOWLEDGE_TOO_LARGE")
    try:
        text = extract_text(safe_name, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(text) > MAX_KNOWLEDGE_CHARS:
        raise HTTPException(status_code=413, detail="KNOWLEDGE_TEXT_TOO_LARGE")
    final_id = document_id.strip() or derive_document_id(safe_name)
    if not DOCUMENT_ID_PATTERN.match(final_id):
        raise HTTPException(status_code=422, detail="KNOWLEDGE_DOCUMENT_ID_INVALID")
    final_title = title.strip() or Path(safe_name).stem or final_id
    server, item, trace_id = await call_tool(
        db,
        service_id or None,
        INGEST_TOOL_NAME,
        {
            "source": source,
            "document_id": final_id,
            "title": final_title[:300],
            "content": text,
            "device_type": device_type.strip()[:120] or "ESP32",
        },
        read_only=False,
        require_approval=True,
        request_id=request.state.request_id,
    )
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="knowledge_document.ingested",
        resource_type="knowledge_document",
        resource_id=str(item.get("document_id")) if isinstance(item, dict) else final_id,
        request_id=request.state.request_id,
        details={
            "server_id": server.id,
            "source": source,
            "filename": safe_name,
            "size_bytes": len(content),
            "trace_id": trace_id,
        },
    )
    await db.commit()
    return envelope(request, {**(item if isinstance(item, dict) else {}), "trace_id": trace_id})


@router.delete("/{source}/{document_id}", status_code=status.HTTP_200_OK)
async def remove_knowledge_document(
    source: str,
    document_id: str,
    request: Request,
    db: Db,
    admin: AdminUser,
    _: CsrfProtected,
    service_id: str = "",
) -> dict[str, object]:
    server, item, trace_id = await call_tool(
        db,
        service_id or None,
        DELETE_TOOL_NAME,
        {"source": source, "document_id": document_id},
        read_only=False,
        require_approval=True,
        request_id=request.state.request_id,
    )
    add_audit_log(
        db,
        actor_type="user",
        actor_id=admin.id,
        action="knowledge_document.deleted",
        resource_type="knowledge_document",
        resource_id=document_id,
        request_id=request.state.request_id,
        details={"server_id": server.id, "source": source, "trace_id": trace_id},
    )
    await db.commit()
    return envelope(request, {**(item if isinstance(item, dict) else {}), "trace_id": trace_id})


@router.get("")
async def list_knowledge_documents(
    request: Request,
    db: Db,
    user: CurrentUser,
    service_id: str = "",
) -> dict[str, object]:
    _, item, _trace = await call_tool(
        db,
        service_id or None,
        LIST_TOOL_NAME,
        {},
        read_only=True,
        request_id=request.state.request_id,
    )
    return envelope(request, item)
