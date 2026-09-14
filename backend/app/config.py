from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "小yi API"
    app_env: str = "development"
    app_secret_key: str = "development-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./data/xiaoyi.db"
    frontend_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "127.0.0.1"]
    session_cookie_name: str = "xiaoyi_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_hours: int = 24
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    openai_api_mode: str = "responses"
    agent_runtime: str = "mock"
    seed_demo_users: bool = True
    # 开发/测试默认在启动时执行 alembic upgrade head；生产部署应先跑
    # `python -m app.cli deploy` 并设置 DB_AUTO_UPGRADE=false
    db_auto_upgrade: bool = True
    # Agent 执行：dispatcher（默认）使用进程内调度器 + 周期扫描；
    # legacy 在一个发布周期内回退 BackgroundTasks（启动恢复扫描仍执行）
    run_dispatcher_mode: str = "dispatcher"
    run_dispatcher_poll_seconds: float = 1.0
    run_shutdown_grace_seconds: float = 30.0
    # 上下文预算（WP-10）：估算 token、历史消息数与附件字符硬上限
    agent_context_max_input_tokens: int = 60_000
    agent_context_max_history_messages: int = 100
    agent_attachment_max_chars: int = 50_000
    agent_attachments_total_max_chars: int = 100_000
    # 消息分页：不传参数时默认返回最近一页；legacy=true 暂时恢复全量一个版本
    message_pagination_default_limit: int = 50
    message_pagination_max_limit: int = 200
    message_pagination_legacy_default: bool = False
    # 运行事件缓冲（WP-11）：delta 合并阈值、时间窗与工具输出持久化上限
    run_delta_merge_chars: int = 256
    run_delta_merge_ms: int = 200
    run_tool_output_max_bytes: int = 65_536
    # 保留策略（WP-11）：删除开关默认关闭（dry-run）；后台周期任务按 interval 执行
    retention_delete_enabled: bool = False
    retention_interval_hours: int = 6
    retention_batch_size: int = 1000
    unbound_attachment_retention_hours: int = 24
    expired_session_grace_days: int = 7
    # 运行事件压缩：完成后 24h 删除可重建 delta；失败/未完成保留诊断期默认 7 天
    run_events_compact_after_hours: int = 24
    run_events_failed_retention_hours: int = 168
    # 就绪探针：声明为必需依赖的 MCP server key；故障时 /ready 返回 503。
    # 未声明的 MCP 属可选依赖，故障表现为 degraded，不阻止对话历史服务。
    mcp_required_server_keys: Annotated[list[str], NoDecode] = []

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("mcp_allowed_hosts", mode="before")
    @classmethod
    def split_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    @field_validator("mcp_required_server_keys", mode="before")
    @classmethod
    def split_required_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_cookie_policy(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true")
        if self.is_production and self.app_secret_key in ("", "development-only-change-me"):
            raise ValueError("APP_SECRET_KEY must be set to a strong random value in production")
        if self.is_production and self.seed_demo_users:
            raise ValueError("SEED_DEMO_USERS must be false in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def ensure_local_paths(self) -> None:
        if self.database_url.startswith("sqlite"):
            Path("data").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
