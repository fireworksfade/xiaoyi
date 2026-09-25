"""ContextBuilder 与 token 估算测试（specs WP-10 / §9.1、§14.5）。"""

import pytest

from app.services.context_builder import (
    CONTEXT_INPUT_TOO_LARGE,
    AttachmentDraft,
    ContextBudgetExceeded,
    ContextLimits,
    build_context,
)
from app.services.token_estimator import ConservativeTokenEstimator

# 小预算便于触发省略路径
LIMITS = ContextLimits(
    max_input_tokens=400,
    max_history_messages=100,
    max_attachment_chars=200,
    max_total_attachment_chars=300,
    reserve_output_tokens=50,
)


def _msg(role: str, content: str, index: int) -> dict[str, object]:
    return {"id": f"m{index}", "role": role, "content": content}


def test_ascii_and_cjk_estimates_differ() -> None:
    estimator = ConservativeTokenEstimator()
    ascii_tokens = estimator.estimate_text("a" * 400)
    cjk_tokens = estimator.estimate_text("字" * 150)
    assert 80 <= ascii_tokens <= 130
    assert 90 <= cjk_tokens <= 130  # 中文按 1.5 字符/token


def test_current_message_always_included() -> None:
    history = [_msg("user", "旧消息 " + "字" * 500, i) for i in range(10)]
    result = build_context(
        current_message={"id": "cur", "role": "user", "content": "当前问题"},
        current_attachments=[],
        history=history,
        history_attachments={},
        limits=LIMITS,
    )
    assert result.messages[-1]["content"] == "当前问题"
    assert result.metadata["included_message_count"] >= 1
    assert result.metadata["omitted_message_count"] > 0


def test_oversized_current_message_fails_with_stable_code() -> None:
    with pytest.raises(ContextBudgetExceeded) as excinfo:
        build_context(
            current_message={"id": "cur", "role": "user", "content": "字" * 100_000},
            current_attachments=[],
            history=[],
            history_attachments={},
            limits=LIMITS,
        )
    assert excinfo.value.code == CONTEXT_INPUT_TOO_LARGE


def test_attachments_omitted_before_old_turns() -> None:
    """预算不足时先省略旧附件正文，再移除最旧轮次。"""
    history = [
        _msg("user", "带附件的提问", 0),
        _msg("assistant", "回答一", 1),
        _msg("user", "普通提问", 2),
        _msg("assistant", "回答二", 3),
    ]
    attachments = {"m0": [AttachmentDraft(filename="log.txt", text="字" * 1000)]}
    tight = ContextLimits(
        max_input_tokens=150,
        max_history_messages=100,
        max_attachment_chars=200,
        max_total_attachment_chars=300,
        reserve_output_tokens=50,
    )
    result = build_context(
        current_message={"id": "cur", "role": "user", "content": "当前问题"},
        current_attachments=[],
        history=history,
        history_attachments=attachments,
        limits=tight,
    )
    assert result.metadata["omitted_attachment_chars"] > 0
    # 省略后保留文件名占位说明
    assert any("附件正文因预算被省略" in m["content"] for m in result.messages)


def test_attachment_char_limits_applied() -> None:
    result = build_context(
        current_message={"id": "cur", "role": "user", "content": "问题"},
        current_attachments=[
            AttachmentDraft(filename="big.txt", text="a" * 1000),
            AttachmentDraft(filename="big2.txt", text="b" * 1000),
        ],
        history=[],
        history_attachments={},
        limits=ContextLimits(
            max_input_tokens=60_000,
            max_attachment_chars=100,
            max_total_attachment_chars=150,
        ),
    )
    last = result.messages[-1]["content"]
    assert "a" * 100 in last
    assert "a" * 101 not in last
    assert "b" * 50 in last
    assert "b" * 51 not in last


def test_metadata_counts_are_accurate() -> None:
    history = [_msg("user" if i % 2 == 0 else "assistant", f"消息{i}", i) for i in range(8)]
    result = build_context(
        current_message={"id": "cur", "role": "user", "content": "当前"},
        current_attachments=[],
        history=history,
        history_attachments={},
        limits=ContextLimits(
            max_input_tokens=10_000,
            max_history_messages=100,
        ),
    )
    assert result.metadata["included_message_count"] == 9
    assert result.metadata["omitted_message_count"] == 0
    assert result.metadata["history_message_count"] == 8
    assert result.metadata["estimated_input_tokens"] > 0


def test_history_capped_by_max_history_messages() -> None:
    history = [_msg("user", f"消息{i}", i) for i in range(50)]
    limits = ContextLimits(max_input_tokens=10_000, max_history_messages=5)
    result = build_context(
        current_message={"id": "cur", "role": "user", "content": "当前"},
        current_attachments=[],
        history=history,
        history_attachments={},
        limits=limits,
    )
    # 只考虑最近 5 条候选历史（不拆开轮次的前提下）
    assert result.metadata["history_message_count"] == 50
    included = result.metadata["included_message_count"]
    assert 1 <= included <= 6
