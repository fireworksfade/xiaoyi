"""Token 计数与硬切分（Spec §13）。

chunk 长度一律基于 token 计数，禁止使用字符长度判断。默认实现为与
Qwen 系 BPE tokenizer 对齐的启发式估计（CJK 字符约 1 token/字，
英文/数字约 1 token/4 字符，符号约 1 token/字符）；如部署环境提供
真实 tokenizer，可通过 RAG_TOKENIZER_PATH 加载 transformers tokenizer。
"""

from __future__ import annotations

import math
import os
import re
from typing import Protocol

# CJK：汉字 + 假名 + 谚文 + 扩展A
_CJK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_CJK_CHAR_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]")

# 切分粒度：单个 CJK 字符、连续字母数字串、其余单字符
_PIECE_RE = re.compile(
    r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF\uF900-\uFAFF]"
    r"|[A-Za-z0-9]+|."
)


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...

    def split(self, text: str, max_tokens: int) -> list[str]: ...


class HeuristicTokenCounter:
    """无外部依赖的 Qwen BPE 近似计数器。"""

    name = "heuristic"

    @staticmethod
    def _piece_tokens(piece: str) -> int:
        if _CJK_CHAR_RE.fullmatch(piece):
            return 1
        if _WORD_RE.fullmatch(piece):
            return max(1, math.ceil(len(piece) / 4))
        return 1

    def count(self, text: str) -> int:
        if not text:
            return 0
        total = 0
        for piece in _PIECE_RE.findall(text):
            if piece.isspace():
                continue
            total += self._piece_tokens(piece)
        return total

    def split(self, text: str, max_tokens: int) -> list[str]:
        if max_tokens <= 0:
            raise ValueError("TOKEN_BUDGET_INVALID")
        pieces = [piece for piece in _PIECE_RE.findall(text) if not piece.isspace()]
        # 重建时保留 piece 间的原始间隔信息：记录每个 piece 的起始位置
        spans: list[tuple[int, int]] = []
        for match in _PIECE_RE.finditer(text):
            if not match.group().isspace():
                spans.append(match.span())
        if not spans:
            return [text] if text else []

        windows: list[str] = []
        start = spans[0][0]
        current_tokens = 0
        previous_end = spans[0][0]
        for (piece_start, piece_end), piece in zip(spans, pieces, strict=True):
            piece_tokens = self._piece_tokens(piece)
            if current_tokens and current_tokens + piece_tokens > max_tokens:
                windows.append(text[start:previous_end])
                start = piece_start
                current_tokens = 0
            current_tokens += piece_tokens
            previous_end = piece_end
        windows.append(text[start:previous_end])
        return windows


class HFTokenizerCounter:
    """基于 transformers tokenizer 的精确计数（可选）。"""

    name = "hf_tokenizer"

    def __init__(self, tokenizer_path: str):
        from transformers import AutoTokenizer  # noqa: PLC0415 - 可选重依赖，延迟导入

        self._tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=False)

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._tokenizer(text, add_special_tokens=False)["input_ids"])

    def split(self, text: str, max_tokens: int) -> list[str]:
        if max_tokens <= 0:
            raise ValueError("TOKEN_BUDGET_INVALID")
        if not text:
            return []
        ids = self._tokenizer(text, add_special_tokens=False)["input_ids"]
        windows = []
        for offset in range(0, len(ids), max_tokens):
            chunk_ids = ids[offset : offset + max_tokens]
            windows.append(self._tokenizer.decode(chunk_ids, skip_special_tokens=True))
        return windows


_HF_COUNTER_CACHE: dict[str, HFTokenizerCounter | None] = {}


def token_counter_from_env() -> TokenCounter:
    tokenizer_path = os.getenv("RAG_TOKENIZER_PATH", "").strip()
    if tokenizer_path:
        if tokenizer_path not in _HF_COUNTER_CACHE:
            try:
                _HF_COUNTER_CACHE[tokenizer_path] = HFTokenizerCounter(tokenizer_path)
            except Exception:  # noqa: BLE001 - tokenizer 不可用时回退启发式
                _HF_COUNTER_CACHE[tokenizer_path] = None
        counter = _HF_COUNTER_CACHE[tokenizer_path]
        if counter is not None:
            return counter
    return HeuristicTokenCounter()


def is_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))
