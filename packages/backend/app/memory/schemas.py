import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["episodic", "experience"] = "experience"
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1200)
    content: dict[str, Any] = Field(default_factory=dict)
    applicability: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False
    expected_revision: int | None = Field(default=None, ge=1)
    change_reason: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def validate_content(self):
        if len(json.dumps([self.content, self.applicability], ensure_ascii=False)) > 12000:
            raise ValueError("MEMORY_CONTENT_TOO_LARGE")
        if self.kind == "experience":
            if not self.content.get("claims") and not self.content.get("procedure"):
                raise ValueError("MEMORY_EVIDENCE_MISSING")
            for claim in self.content.get("claims", []):
                if not isinstance(claim, dict) or claim.get("epistemic_status") not in {
                    "observed", "user_asserted", "hypothesis", "corroborated",
                    "contradicted", "unknown",
                }:
                    raise ValueError("MEMORY_EVIDENCE_MISSING")
                if claim["epistemic_status"] != "user_asserted" and not claim.get("evidence_refs"):
                    raise ValueError("MEMORY_EVIDENCE_MISSING")
        elif self.content.get("outcome") not in {
            "pending", "succeeded", "failed", "inconclusive", "not_executed",
        }:
            raise ValueError("MEMORY_EVIDENCE_MISSING")
        if self.applicability.get("device_ids") and not self.applicability.get("mcp_server_id"):
            raise ValueError("MEMORY_SOURCE_UNAVAILABLE")
        return self


class RevisionAction(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=1200)


class MemorySearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    mcp_server_id: str | None = None
    device_id: str | None = None
    device_type: str | None = None
    top_k: int = Field(default=6, ge=1, le=6)


class ForgetSource(BaseModel):
    conversation_id: str
