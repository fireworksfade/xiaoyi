from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import MCPPurpose, RunStatus, ToolRiskPolicy, UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class UserView(BaseModel):
    id: str
    username: str
    role: UserRole


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ConversationView(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    client_message_id: str = Field(min_length=1, max_length=80)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    tool_mode: str = Field(default="auto", pattern=r"^(auto|none|selected)$")
    mcp_server_ids: list[str] = Field(default_factory=list, max_length=10)


class MessageView(BaseModel):
    id: str
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime


class RunView(BaseModel):
    id: str
    conversation_id: str
    status: RunStatus
    final_message_id: str | None
    error: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class Page(BaseModel):
    items: list[Any]
    page: int
    page_size: int
    total: int


class MCPServerCreate(BaseModel):
    server_key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=500)
    purpose: MCPPurpose = MCPPurpose.GENERIC
    credential: str | None = Field(default=None, max_length=4000)


class MCPServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    purpose: MCPPurpose | None = None
    credential: str | None = Field(default=None, max_length=4000)
    enabled: bool | None = None


class MCPToolUpdate(BaseModel):
    enabled: bool
    risk_policy: ToolRiskPolicy


class VerifiedFaultCaseCreate(BaseModel):
    device_id: str = Field(min_length=1, max_length=120)
    fault_type: str = Field(min_length=1, max_length=120)
    fault_name: str = Field(min_length=1, max_length=200)
    symptoms: list[str] = Field(min_length=1, max_length=20)
    logs: list[str] = Field(min_length=1, max_length=50)
    cause: str = Field(min_length=1, max_length=4000)
    solution: str = Field(min_length=1, max_length=4000)
    verified: bool


class ModelConfigurationUpdate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model_name: str = Field(min_length=1, max_length=120)
    api_mode: str = Field(pattern=r"^(responses|chat_completions)$")
    api_key: str | None = Field(default=None, min_length=8, max_length=4000)
    clear_api_key: bool = False
    enabled: bool = False
