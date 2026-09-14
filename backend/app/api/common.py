from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import Db
from app.config import Settings, get_settings
from app.models import AgentRun, Conversation, Message, User
from app.services.run_state import is_retryable

SettingsDep = Annotated[Settings, Depends(get_settings)]


def envelope(request: Request, data: object) -> dict[str, object]:
    return {"data": data, "request_id": request.state.request_id}


def user_view(user: User) -> dict[str, str]:
    return {"id": user.id, "username": user.username, "role": user.role.value}


def conversation_view(item: Conversation) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def message_view(item: Message) -> dict[str, object]:
    return {
        "id": item.id,
        "role": item.role,
        "content": item.content,
        "metadata": item.metadata_json,
        "created_at": item.created_at.isoformat(),
    }


def run_view(item: AgentRun) -> dict[str, object]:
    error = None
    if item.error_code:
        error = {
            "code": item.error_code,
            "message": item.error_message,
            "retryable": is_retryable(item.error_code),
        }
    return {
        "id": item.id,
        "conversation_id": item.conversation_id,
        "status": item.status.value,
        "final_message_id": item.final_message_id,
        "error": error,
        "interruption_reason": item.interruption_reason,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


async def owned_conversation(db: Db, conversation_id: str, user: User) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONVERSATION_NOT_FOUND")
    return conversation
