"""保守 token 估算器（specs WP-10 / §3.5）。

不绑定特定模型 tokenizer：
- ASCII 连续文本按约 4 字符/token；
- 非 ASCII 字符（中文等）按约 1.5 字符/token；
- 每条消息增加固定结构开销。

后续可通过实现同一接口接入模型专用估算器。
"""

from __future__ import annotations

from typing import Protocol

ASCII_CHARS_PER_TOKEN = 4.0
NON_ASCII_CHARS_PER_TOKEN = 1.5
MESSAGE_OVERHEAD_TOKENS = 8


class TokenEstimator(Protocol):
    def estimate_text(self, text: str) -> int: ...

    def estimate_message(self, role: str, content: str) -> int: ...


class ConservativeTokenEstimator:
    def estimate_text(self, text: str) -> int:
        if not text:
            return 0
        non_ascii = sum(1 for ch in text if ord(ch) > 0x7F)
        ascii_chars = len(text) - non_ascii
        tokens = ascii_chars / ASCII_CHARS_PER_TOKEN + non_ascii / NON_ASCII_CHARS_PER_TOKEN
        return max(1, int(tokens) + (1 if tokens % 1 else 0))

    def estimate_message(self, role: str, content: str) -> int:
        return MESSAGE_OVERHEAD_TOKENS + self.estimate_text(role) + self.estimate_text(content)


DEFAULT_ESTIMATOR = ConservativeTokenEstimator()
