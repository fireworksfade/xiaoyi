from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import new_id, utc_now


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Owned(Identity):
    owner_user_id: Mapped[str] = mapped_column(String(36), index=True)


class Memory(Owned, Base):
    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "event_key"),
        Index("ix_memory_owner_kind_status", "owner_user_id", "kind", "status", "updated_at"),
    )
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    title: Mapped[str] = mapped_column(String(160))
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    active_revision: Mapped[int | None] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(30))
    event_key: Mapped[str | None] = mapped_column(String(250))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryRevision(Identity, Base):
    __tablename__ = "memory_revisions"
    __table_args__ = (UniqueConstraint("memory_id", "revision"),)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    applicability_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    search_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    review_state: Mapped[str] = mapped_column(String(20), default="candidate")
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36))
    extractor_version: Mapped[str] = mapped_column(String(40), default="v1")
    policy_version: Mapped[str] = mapped_column(String(40), default="v1")
    model_id: Mapped[str | None] = mapped_column(String(120))


class MemorySource(Owned, Base):
    __tablename__ = "memory_sources"
    __table_args__ = (UniqueConstraint("owner_user_id", "source_key"),)
    source_key: Mapped[str] = mapped_column(String(250))
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    mcp_server_id: Mapped[str | None] = mapped_column(String(36))
    diagnosis_id: Mapped[str | None] = mapped_column(String(120), index=True)
    command_id: Mapped[str | None] = mapped_column(String(120))
    tool_call_id: Mapped[str | None] = mapped_column(String(120))
    excerpt: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    access_state: Mapped[str] = mapped_column(String(30), default="available")


class MemoryEvidenceLink(Owned, Base):
    __tablename__ = "memory_evidence_links"
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    episode_id: Mapped[str | None] = mapped_column(String(36), index=True)
    episode_revision: Mapped[int | None] = mapped_column(Integer)
    relation: Mapped[str] = mapped_column(String(20), default="derived_from")


class MemoryFeedback(Owned, Base):
    __tablename__ = "memory_feedback"
    __table_args__ = (UniqueConstraint("owner_user_id", "memory_id", "command_id"),)
    memory_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    command_id: Mapped[str] = mapped_column(String(120))
    outcome: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)


class MemoryUsage(Owned, Base):
    __tablename__ = "memory_usage"
    memory_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str | None] = mapped_column(String(36))
    diagnosis_id: Mapped[str | None] = mapped_column(String(120))
    stage: Mapped[str] = mapped_column(String(20))


class MemoryTombstone(Owned, Base):
    __tablename__ = "memory_tombstones"
    __table_args__ = (UniqueConstraint("owner_user_id", "scope", "target_id"),)
    scope: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[str] = mapped_column(String(250))
    content_hash: Mapped[str | None] = mapped_column(String(64))


class MemoryJob(Owned, Base):
    __tablename__ = "memory_jobs"
    __table_args__ = (UniqueConstraint("owner_user_id", "job_key"),)
    job_key: Mapped[str] = mapped_column(String(250))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    error_code: Mapped[str | None] = mapped_column(String(100))


class MemoryActionLink(Owned, Base):
    __tablename__ = "memory_action_links"
    __table_args__ = (UniqueConstraint("correlation_key"),)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str] = mapped_column(String(36))
    mcp_server_id: Mapped[str] = mapped_column(String(36))
    correlation_key: Mapped[str] = mapped_column(String(120))
    parameters_hash: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    tool_name: Mapped[str] = mapped_column(String(80))
    proposal_id: Mapped[str | None] = mapped_column(String(120), index=True)
    command_id: Mapped[str | None] = mapped_column(String(120), index=True)
    diagnosis_id: Mapped[str | None] = mapped_column(String(120))
    applied_memory_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    reservation: Mapped[str] = mapped_column(String(20), default="reserved")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(30), default="pending")
    rediagnosis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    next_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    tracking_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryVectorOutbox(Owned, Base):
    __tablename__ = "memory_vector_outbox"
    memory_id: Mapped[str] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(20))
    model_fingerprint: Mapped[str] = mapped_column(String(120))
    collection: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="pending")


class MemoryIndexState(Identity, Base):
    __tablename__ = "memory_index_state"
    __table_args__ = (UniqueConstraint("memory_id", "revision", "model_fingerprint"),)
    memory_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    model_fingerprint: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(100))


class WorkingMemory(Owned, Base):
    __tablename__ = "working_memories"
    __table_args__ = (UniqueConstraint("owner_user_id", "conversation_id"),)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    run_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer, default=1)
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
