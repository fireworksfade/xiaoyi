from pydantic import BaseModel, Field

from app.models import MCPPurpose, ToolRiskPolicy


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    client_message_id: str = Field(min_length=1, max_length=80)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    tool_mode: str = Field(default="auto", pattern=r"^(auto|none|selected)$")
    mcp_server_ids: list[str] = Field(default_factory=list, max_length=10)


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


class RemediationDecisionCreate(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")
    expected_version: int = Field(ge=1)


class ModelConfigurationUpdate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model_name: str = Field(min_length=1, max_length=120)
    api_mode: str = Field(pattern=r"^(responses|chat_completions)$")
    api_key: str | None = Field(default=None, min_length=8, max_length=4000)
    clear_api_key: bool = False
    enabled: bool = False
