"""Token-aware Chunker（Spec §1/G1、§14-§16）。

先由 Structure-aware Parser 产生 Block[]，本模块按 token budget 合并相邻
结构块；heading context 的 token 计入 chunk 预算（Spec §8）。超长块优先按
结构边界（行 / 步骤 / 句子 / 表格行）拆分，token 硬切分只作最后 fallback
（Spec §15）；相邻拆分片段之间按配置产生 overlap，优先完整结构（Spec §16）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from iot_diagnosis.chunking.models import Block, Chunk
from iot_diagnosis.chunking.token_counter import TokenCounter

# 块之间的换行分隔按约 2 token 预算（HF tokenizer 下换行有成本）
_JOIN_GAP_TOKENS = 2


@dataclass(frozen=True)
class ChunkerConfig:
    chunk_size: int = 512
    chunk_overlap: int = 64
    inject_heading_context: bool = True
    preserve_code_blocks: bool = True
    preserve_logs: bool = True
    preserve_lists: bool = True
    preserve_tables: bool = True


@dataclass
class _Atom:
    text: str
    tokens: int
    block_type: str
    heading_path: tuple[str, ...]
    language: str | None = None
    block_sequence: int | None = None
    block_total: int | None = None


@dataclass
class _PendingChunk:
    heading_path: tuple[str, ...] = ()
    atoms: list[_Atom] = field(default_factory=list)
    tokens: int = 0


_NUMBERED_RE = re.compile(r"^\s*\d{1,3}[.)、]\s*")
_BULLET_RE = re.compile(r"^\s*[-*+]\s*")
_SENTENCE_END_RE = re.compile(r"[。！？!?]+|\n+")


def _split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(text):
        end = match.end()
        parts.append(text[start:end])
        start = end
    if start < len(text):
        parts.append(text[start:])
    return [part for part in parts if part.strip()]


def _render_heading(path: tuple[str, ...] | list[str]) -> str:
    return "\n".join(f"{'#' * (level + 1)} {text}" for level, text in enumerate(path))


def _group_units(units: list[str], budget: int, counter: TokenCounter) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        unit_tokens = counter.count(unit)
        if unit_tokens > budget:
            # 单元自身超预算：token 硬切分（最后 fallback，Spec §15）
            if current:
                groups.append(current)
                current = []
            for piece in counter.split(unit, budget):
                groups.append([piece])
            continue
        if current and current_tokens + unit_tokens > budget:
            groups.append(current)
            current = []
            current_tokens = 0
        current.append(unit)
        current_tokens += unit_tokens
    if current:
        groups.append(current)
    return groups


def _overlap_tail(units: list[str], overlap_tokens: int, counter: TokenCounter) -> str:
    """取尾部完整结构单元，总 token 不超过 overlap（Spec §16）。"""
    if overlap_tokens <= 0 or not units:
        return ""
    tail: list[str] = []
    total = 0
    for unit in reversed(units):
        unit_tokens = counter.count(unit)
        if total + unit_tokens > overlap_tokens:
            break
        tail.insert(0, unit)
        total += unit_tokens
    if not tail:
        # 无完整单元可放入 overlap 时退化为纯 token overlap
        pieces = counter.split(units[-1], overlap_tokens)
        return pieces[-1] if pieces else ""
    return "\n".join(tail)


def _piece_units(block_type: str, piece: str) -> list[str]:
    lines = piece.split("\n")
    if block_type == "code":
        inner = lines[1:-1] if len(lines) > 2 else lines
    elif block_type == "table":
        inner = lines[2:] if len(lines) > 2 else []
    else:
        inner = lines
    return [line for line in inner if line.strip()]


def _split_oversized_block(
    block: Block,
    budget: int,
    counter: TokenCounter,
    overlap: int,
) -> list[_Atom]:
    """按结构边界拆分超长块，返回带 overlap 的原子序列。"""
    lines = block.content.split("\n")
    is_code = block.block_type == "code"
    is_table = block.block_type == "table"
    # 拆分时为 overlap 预留空间，保证 overlap + 片段不超预算（Spec §16）
    piece_budget = max(1, budget - overlap) if overlap > 0 else budget

    if is_table:
        header = lines[0] if lines else ""
        separator = lines[1] if len(lines) > 1 else ""
        rows = lines[2:] if len(lines) > 2 else []
        header_prefix = "\n".join(part for part in (header, separator) if part)
        header_tokens = counter.count(header_prefix) + 1 if header_prefix else 0
        groups = _group_units(rows, max(1, piece_budget - header_tokens), counter)
        pieces = []
        for group in groups:
            body = "\n".join(group)
            pieces.append(f"{header_prefix}\n{body}" if header_prefix else body)
    elif block.block_type in {"steps", "list"}:
        marker = _NUMBERED_RE if block.block_type == "steps" else _BULLET_RE
        units: list[str] = []
        for line in lines:
            if marker.match(line) or not units:
                units.append(line)
            else:
                units[-1] = f"{units[-1]}\n{line}"
        pieces = ["\n".join(group) for group in _group_units(units, piece_budget, counter)]
    elif is_code:
        # 拆分时保持 fenced code 结构完整（Spec §9）
        fence_open = (
            lines[0].strip() if lines and lines[0].lstrip().startswith(("```", "~~~")) else "```"
        )
        fence_close = (
            lines[-1].strip()
            if lines and lines[-1].strip() in {"```", "~~~"}
            else "```"
            if fence_open.startswith("`")
            else "~~~"
        )
        inner = lines
        if lines and lines[0].lstrip().startswith(("```", "~~~")):
            inner = lines[1:]
        if inner and inner[-1].strip() in {"```", "~~~"}:
            inner = inner[:-1]
        fence_tokens = counter.count(f"{fence_open}\n{fence_close}")
        groups = _group_units(inner, max(1, piece_budget - fence_tokens), counter)
        pieces = [f"{fence_open}\n" + "\n".join(group) + f"\n{fence_close}" for group in groups]
    elif block.block_type == "log":
        pieces = ["\n".join(group) for group in _group_units(lines, piece_budget, counter)]
    else:
        sentences = _split_sentences(block.content)
        pieces = ["".join(group) for group in _group_units(sentences, piece_budget, counter)]

    atoms: list[_Atom] = []
    previous_units: list[str] = []
    for index, piece in enumerate(pieces):
        text = piece
        if index > 0 and overlap > 0:
            tail = _overlap_tail(previous_units, overlap, counter)
            if tail:
                if is_code:
                    # overlap 行插入 fence 内部，保持代码块结构
                    first_newline = text.find("\n")
                    text = f"{text[: first_newline + 1]}{tail}\n{text[first_newline + 1 :]}"
                elif is_table:
                    # overlap 行插入表头之后（Spec §12：表头始终在最前）
                    separator_end = text.find("\n", text.find("\n") + 1)
                    text = f"{text[: separator_end + 1]}{tail}\n{text[separator_end + 1 :]}"
                else:
                    text = f"{tail}\n{text}"
            if text != piece and counter.count(text) > budget:
                # overlap 使片段超预算时舍弃 overlap，保证预算成立
                text = piece
        atoms.append(
            _Atom(
                text=text,
                tokens=counter.count(text),
                block_type=block.block_type,
                heading_path=tuple(block.heading_path),
                language=block.language,
                block_sequence=index + 1,
                block_total=len(pieces),
            )
        )
        previous_units = _piece_units(block.block_type, piece)
    return atoms


def chunk_blocks(
    blocks: list[Block],
    *,
    document_id: str,
    source: str = "",
    title: str = "",
    counter: TokenCounter,
    config: ChunkerConfig | None = None,
) -> list[Chunk]:
    """把结构块按 token budget 装配为 chunk 列表（Spec §14）。"""
    config = config or ChunkerConfig()
    if config.chunk_size <= 0:
        raise ValueError("CHUNK_SIZE_INVALID")
    if not 0 <= config.chunk_overlap < config.chunk_size:
        raise ValueError("CHUNK_OVERLAP_INVALID")

    content_blocks = [block for block in blocks if block.block_type != "heading"]
    if not content_blocks:
        return []

    # heading context 注入时其 token 计入预算（Spec §8/§14）
    prefix_tokens: dict[tuple[str, ...], int] = {}

    def prefix_cost(path: tuple[str, ...]) -> int:
        if path not in prefix_tokens:
            text = _render_heading(path) if config.inject_heading_context else ""
            prefix_tokens[path] = counter.count(text) + (_JOIN_GAP_TOKENS if text else 0)
        return prefix_tokens[path]

    def body_budget(path: tuple[str, ...]) -> int:
        return max(1, config.chunk_size - prefix_cost(path))

    preserve = {
        "code": config.preserve_code_blocks,
        "log": config.preserve_logs,
        "steps": config.preserve_lists,
        "list": config.preserve_lists,
        "table": config.preserve_tables,
    }

    atoms: list[_Atom] = []
    for block in content_blocks:
        path = tuple(block.heading_path)
        block_tokens = counter.count(block.content)
        atomic = preserve.get(block.block_type, False)
        if block_tokens <= body_budget(path):
            atoms.append(
                _Atom(
                    text=block.content,
                    tokens=block_tokens,
                    block_type=block.block_type,
                    heading_path=path,
                    language=block.language,
                )
            )
            continue
        if not atomic:
            # 对应 preserve 开关关闭时退化为普通段落切分
            block = Block(
                block_type="paragraph",
                content=block.content,
                heading_path=block.heading_path,
                language=block.language,
            )
        atoms.extend(
            _split_oversized_block(block, body_budget(path), counter, config.chunk_overlap)
        )

    chunks: list[Chunk] = []
    pending = _PendingChunk()
    last_section: tuple[str, ...] | None = None
    for atom in atoms:
        if pending.atoms:
            new_section = atom.heading_path != last_section
            extra = (
                counter.count(_render_heading(atom.heading_path)) + _JOIN_GAP_TOKENS
                if new_section
                else 0
            )
            projected = (
                prefix_cost(pending.heading_path)
                + pending.tokens
                + _JOIN_GAP_TOKENS
                + extra
                + atom.tokens
            )
            # 跨小节合并仅在当前 chunk 未过半时进行（Spec §14），
            # 避免把每个小节都强制拆成独立 chunk
            if projected > config.chunk_size or (
                new_section and pending.tokens >= config.chunk_size // 2
            ):
                chunks.append(_finalize(pending, document_id, source, title, counter, config))
                pending = _PendingChunk()
                last_section = None
        if pending.atoms and atom.heading_path != last_section:
            # 新小节并入现有 chunk：heading 行作为正文一部分保留（Spec §2）
            heading_text = _render_heading(atom.heading_path)
            merged = f"{heading_text}\n\n{atom.text}"
            atom = _Atom(
                text=merged,
                tokens=counter.count(merged),
                block_type=atom.block_type,
                heading_path=atom.heading_path,
                language=atom.language,
                block_sequence=atom.block_sequence,
                block_total=atom.block_total,
            )
        if not pending.atoms:
            pending.heading_path = atom.heading_path
        last_section = atom.heading_path
        pending.atoms.append(atom)
        pending.tokens += atom.tokens + (_JOIN_GAP_TOKENS if len(pending.atoms) > 1 else 0)
    if pending.atoms:
        chunks.append(_finalize(pending, document_id, source, title, counter, config))

    for index, chunk in enumerate(chunks):
        chunk.chunk_index = index
    return chunks


def _finalize(
    pending: _PendingChunk,
    document_id: str,
    source: str,
    title: str,
    counter: TokenCounter,
    config: ChunkerConfig,
) -> Chunk:
    heading_path = list(pending.heading_path)
    prefix = _render_heading(heading_path) if config.inject_heading_context else ""
    parts = ([prefix] if prefix else []) + [atom.text for atom in pending.atoms]
    content = "\n\n".join(parts)

    types = {atom.block_type for atom in pending.atoms}
    block_type = types.pop() if len(types) == 1 else "mixed"
    language = next((atom.language for atom in pending.atoms if atom.language), None)
    sequence = next((atom.block_sequence for atom in pending.atoms if atom.block_sequence), None)
    total = next((atom.block_total for atom in pending.atoms if atom.block_total), None)

    metadata: dict[str, object] = {
        "heading_injected": bool(prefix),
        "atom_count": len(pending.atoms),
    }
    if language:
        metadata["language"] = language
    if sequence is not None:
        metadata["block_sequence"] = sequence
        metadata["block_total"] = total

    return Chunk(
        content=content,
        document_id=document_id,
        chunk_index=0,
        title=heading_path[0] if heading_path else title or None,
        heading_path=heading_path,
        block_type=block_type,
        token_count=counter.count(content),
        source=source or None,
        metadata=metadata,
    )
