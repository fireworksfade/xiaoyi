"""对话上下文构建器（specs WP-10 / §9.1、§14.2）。

- 始终保留当前用户消息；从新到旧按 user/assistant 语义轮次选择历史；
- 预算不足时先省略旧附件正文（保留文件名占位），再省略最旧轮次；
- 不截断当前用户文本；当前文本自身超预算时抛出 CONTEXT_INPUT_TOO_LARGE；
- 元数据记录 included/omitted 消息数、附件字符数与估算 token 数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.token_estimator import DEFAULT_ESTIMATOR, ConservativeTokenEstimator

ATTACHMENT_PLACEHOLDER = "（附件正文因预算被省略）"
CONTEXT_INPUT_TOO_LARGE = "CONTEXT_INPUT_TOO_LARGE"


class ContextBudgetExceeded(Exception):
    """当前用户消息自身超过预算；调用方应将 run 标记为该错误码。"""

    code = CONTEXT_INPUT_TOO_LARGE


@dataclass
class ContextLimits:
    max_input_tokens: int = 60_000
    max_history_messages: int = 100
    max_attachment_chars: int = 50_000
    max_total_attachment_chars: int = 100_000
    reserve_output_tokens: int = 8_000

    @classmethod
    def from_settings(cls, settings) -> "ContextLimits":  # noqa: ANN001
        return cls(
            max_input_tokens=settings.agent_context_max_input_tokens,
            max_history_messages=settings.agent_context_max_history_messages,
            max_attachment_chars=settings.agent_attachment_max_chars,
            max_total_attachment_chars=settings.agent_attachments_total_max_chars,
        )


@dataclass
class AttachmentDraft:
    filename: str
    text: str


@dataclass
class ContextResult:
    """构建结果：渲染后的模型输入消息与预算元数据。"""

    messages: list[dict[str, str]]
    metadata: dict[str, Any]
    included_history_ids: set[str] = field(default_factory=set)


def _render_user_message(
    content: str, attachments: list[AttachmentDraft], *, omit_bodies: bool
) -> str:
    if not attachments:
        return content
    parts = []
    for attachment in attachments:
        body = ATTACHMENT_PLACEHOLDER if omit_bodies else attachment.text
        parts.append(f"[附件：{attachment.filename}]\n{body}")
    return f"{content}\n\n" + "\n\n".join(parts)


@dataclass
class ContextTurn:
    """一组 user/assistant 语义轮次；不能被拆开省略。"""

    messages: list[dict[str, Any]] = field(default_factory=list)  # 升序，含 role/content/id
    attachments: list[AttachmentDraft] = field(default_factory=list)

    def render(self, *, omit_bodies: bool) -> list[dict[str, str]]:
        rendered: list[dict[str, str]] = []
        for message in self.messages:
            if message["role"] == "user":
                text = _render_user_message(
                    message["content"], self.attachments, omit_bodies=omit_bodies
                )
            else:
                text = message["content"]
            rendered.append({"role": message["role"], "content": text})
        return rendered

    @property
    def attachment_chars(self) -> int:
        return sum(len(a.text) for a in self.attachments)


def _estimate(rendered: list[dict[str, str]], estimator: ConservativeTokenEstimator) -> int:
    return sum(estimator.estimate_message(item["role"], item["content"]) for item in rendered)


def _clip_attachments(
    attachments: list[AttachmentDraft], limits: ContextLimits
) -> list[AttachmentDraft]:
    """单附件与总字符硬上限；超限保留文件名与已裁剪正文。"""
    clipped: list[AttachmentDraft] = []
    total = 0
    for attachment in attachments:
        remaining = limits.max_total_attachment_chars - total
        if remaining <= 0:
            clipped.append(AttachmentDraft(filename=attachment.filename, text=""))
            continue
        text = attachment.text[: min(limits.max_attachment_chars, remaining)]
        total += len(text)
        clipped.append(AttachmentDraft(filename=attachment.filename, text=text))
    return clipped


def _aggregate_turns(
    history: list[dict[str, Any]],
    history_attachments: dict[str, list[AttachmentDraft]],
    max_turns: int,
    *,
    max_attachment_chars: int,
) -> list[ContextTurn]:
    """从新到旧聚合为语义轮次（user 起始），最多 max_turns 轮；返回旧→新。

    历史附件同样受单附件字符上限约束（进入模型的文本）。
    """
    turns: list[ContextTurn] = []
    current: list[dict[str, Any]] = []
    for message in reversed(history):
        current.insert(0, message)
        if message["role"] == "user":
            turns.insert(0, ContextTurn(messages=current, attachments=[]))
            current = []
            if len(turns) >= max_turns:
                break
    for turn in turns:
        for message in turn.messages:
            if message["role"] == "user":
                turn.attachments = [
                    AttachmentDraft(filename=a.filename, text=a.text[:max_attachment_chars])
                    for a in history_attachments.get(message.get("id", ""), [])
                ]
                break
    return turns


def build_context(
    *,
    current_message: dict[str, Any],
    current_attachments: list[AttachmentDraft],
    history: list[dict[str, Any]],
    history_attachments: dict[str, list[AttachmentDraft]],
    limits: ContextLimits | None = None,
    estimator: ConservativeTokenEstimator | None = None,
) -> ContextResult:
    """按预算构建模型输入；返回渲染后的消息列表与预算元数据。"""
    limits = limits or ContextLimits()
    estimator = estimator or DEFAULT_ESTIMATOR
    budget = limits.max_input_tokens - limits.reserve_output_tokens

    current_attachments = _clip_attachments(current_attachments, limits)
    current_rendered = _render_user_message(
        current_message["content"], current_attachments, omit_bodies=False
    )
    used = estimator.estimate_message("user", current_rendered)
    if used > budget:
        raise ContextBudgetExceeded("当前消息超过上下文预算：请缩短文本或减少附件")

    turns = _aggregate_turns(
        history,
        history_attachments,
        limits.max_history_messages,
        max_attachment_chars=limits.max_attachment_chars,
    )

    # 从新到旧决策：整轮纳入 → 省略附件正文纳入 → 整轮省略
    decisions: list[tuple[ContextTurn, bool]] = []  # (turn, omit_bodies)
    omitted_messages = 0
    omitted_attachment_chars = 0
    for turn in reversed(turns):
        full_tokens = _estimate(turn.render(omit_bodies=False), estimator)
        if used + full_tokens <= budget:
            decisions.append((turn, False))
            used += full_tokens
            continue
        if turn.attachments:
            slim_tokens = _estimate(turn.render(omit_bodies=True), estimator)
            if used + slim_tokens <= budget:
                decisions.append((turn, True))
                used += slim_tokens
                omitted_attachment_chars += turn.attachment_chars
                continue
        omitted_messages += len(turn.messages)
        omitted_attachment_chars += turn.attachment_chars

    final: list[dict[str, str]] = []
    for turn, omit_bodies in reversed(decisions):  # 旧 → 新
        final.extend(turn.render(omit_bodies=omit_bodies))
    final.append({"role": "user", "content": current_rendered})

    included_ids = {message.get("id") for turn, _omit in decisions for message in turn.messages}
    metadata = {
        "included_message_count": len(included_ids) + 1,
        "omitted_message_count": omitted_messages,
        "history_message_count": len(history),
        "included_attachment_chars": sum(
            turn.attachment_chars for turn, omit in decisions if not omit
        ),
        "omitted_attachment_chars": omitted_attachment_chars,
        "estimated_input_tokens": used,
        "max_input_tokens": limits.max_input_tokens,
    }
    return ContextResult(
        messages=final,
        metadata=metadata,
        included_history_ids={str(message_id) for message_id in included_ids if message_id},
    )
