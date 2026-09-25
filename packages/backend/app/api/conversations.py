from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.api.common import conversation_view, envelope, owned_conversation
from app.api.deps import CsrfProtected, CurrentUser, Db
from app.models import Conversation, MCPServer, MCPTool, ToolRiskPolicy
from app.schemas import ConversationCreate, ConversationUpdate

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(
    request: Request,
    db: Db,
    user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    criteria = (Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
    total = await db.scalar(select(func.count()).select_from(Conversation).where(*criteria))
    items = list(
        (
            await db.scalars(
                select(Conversation)
                .where(*criteria)
                .order_by(Conversation.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return envelope(
        request,
        {
            "items": [conversation_view(item) for item in items],
            "page": page,
            "page_size": page_size,
            "total": total or 0,
        },
    )


@router.get("/agent-tools")
async def list_agent_tools(request: Request, db: Db, _: CurrentUser) -> dict[str, object]:
    servers = list(
        (
            await db.scalars(
                select(MCPServer).where(
                    MCPServer.enabled.is_(True),
                    MCPServer.connection_status == "connected",
                    MCPServer.deleted_at.is_(None),
                )
            )
        ).all()
    )
    items = []
    for server in servers:
        count = await db.scalar(
            select(func.count())
            .select_from(MCPTool)
            .where(
                MCPTool.server_id == server.id,
                MCPTool.enabled.is_(True),
                MCPTool.risk_policy.in_([ToolRiskPolicy.READ_ONLY, ToolRiskPolicy.PROPOSAL_ONLY]),
            )
        )
        if count:
            items.append(
                {
                    "id": server.id,
                    "server_key": server.server_key,
                    "name": server.name,
                    "tool_count": count,
                }
            )
    return envelope(request, {"items": items})


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = Conversation(user_id=user.id, title=payload.title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return envelope(request, conversation_view(conversation))


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = await owned_conversation(db, conversation_id, user)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="CONVERSATION_TITLE_REQUIRED")
    conversation.title = title
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(conversation)
    return envelope(request, conversation_view(conversation))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
    _: CsrfProtected,
) -> dict[str, object]:
    conversation = await owned_conversation(db, conversation_id, user)
    conversation.deleted_at = datetime.now(timezone.utc)
    conversation.updated_at = conversation.deleted_at
    await db.commit()
    return envelope(request, {"deleted": True})
