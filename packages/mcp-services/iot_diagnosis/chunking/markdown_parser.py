"""Structure-aware Markdown Parser（Spec §7、§9-§12）。

将文档解析为结构块序列：heading / paragraph / code / log / list / steps /
table / quote。解析过程不做任何压平（normalization 禁止破坏代码块、日志
换行、故障步骤与表格结构），每个块记录解析时的 heading stack。
"""

from __future__ import annotations

import re

from iot_diagnosis.chunking.models import Block

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([A-Za-z0-9_+#.-]*)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}.*\|\s*$")
_NUMBERED_RE = re.compile(r"^\s*\d{1,3}[.)、]\s+\S")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+\S")
_QUOTE_RE = re.compile(r"^\s*>")
_LOG_LINE_RE = re.compile(
    r"(^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"  # ISO 时间戳前缀
    r"|^\[\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"|^[IWEF] \(\d+\)"  # ESP-IDF 日志格式
    r"|^\[(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL|TRACE|NOTICE)\]"
    r"|\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL|TRACE|NOTICE)\b\s*[:：])",
    re.IGNORECASE,
)


def _split_log_candidates(lines: list[str]) -> bool:
    """连续文本行是否为日志块：≥2 行且多数行具有日志特征（Spec §10）。"""
    if len(lines) < 2:
        return False
    matched = sum(1 for line in lines if _LOG_LINE_RE.search(line))
    return matched >= max(1, len(lines) // 2)


def _push_heading(stack: list[tuple[int, str]], level: int, text: str) -> list[str]:
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, text))
    return [text for _, text in stack]


def parse_blocks(text: str) -> list[Block]:
    """把 Markdown / 纯文本解析为结构块序列。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _FENCE_OPEN_RE.match(line)
        if fence:
            marker = fence.group(1)
            language = fence.group(2) or None
            body: list[str] = [line]
            index += 1
            while index < total:
                body.append(lines[index])
                closing = _FENCE_OPEN_RE.match(lines[index])
                if (
                    closing
                    and closing.group(1)[0] == marker[0]
                    and len(closing.group(1)) >= len(marker)
                ):
                    index += 1
                    break
                index += 1
            blocks.append(
                Block(
                    block_type="code",
                    content="\n".join(body),
                    heading_path=[text for _, text in heading_stack],
                    language=language,
                )
            )
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            path = _push_heading(heading_stack, level, heading.group(2))
            blocks.append(
                Block(
                    block_type="heading",
                    content=line,
                    heading_path=path,
                    level=level,
                )
            )
            index += 1
            continue

        if (
            _TABLE_ROW_RE.match(line)
            and index + 1 < total
            and _TABLE_SEPARATOR_RE.match(lines[index + 1])
        ):
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < total and _TABLE_ROW_RE.match(lines[index]):
                table_lines.append(lines[index])
                index += 1
            blocks.append(
                Block(
                    block_type="table",
                    content="\n".join(table_lines),
                    heading_path=[text for _, text in heading_stack],
                    table_header=table_lines[0],
                )
            )
            continue

        # 剩余为普通文本行运行（paragraph / log / list / steps / quote）
        run: list[str] = []
        while index < total and lines[index].strip():
            current = lines[index]
            if _FENCE_OPEN_RE.match(current) or _HEADING_RE.match(current):
                break
            if run and _TABLE_ROW_RE.match(run[-1]) and _TABLE_SEPARATOR_RE.match(current):
                # 表头行已被当作普通文本消费；回退后由外层按表格块解析
                run.pop()
                index -= 1
                break
            run.append(current)
            index += 1

        first = run[0]
        if _NUMBERED_RE.match(first):
            block_type = "steps"
        elif _BULLET_RE.match(first):
            block_type = "list"
        elif _QUOTE_RE.match(first):
            block_type = "quote"
        elif _split_log_candidates(run):
            block_type = "log"
        else:
            block_type = "paragraph"
        blocks.append(
            Block(
                block_type=block_type,
                content="\n".join(run),
                heading_path=[text for _, text in heading_stack],
            )
        )

    return blocks
