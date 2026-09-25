"""Structure-aware chunking pipeline.

Pipeline: Document → Structure-aware Parser → Structural Blocks
→ Token-aware Chunker → Chunks（Spec《RAG 检索链路升级》§4/§39）。
"""

from iot_diagnosis.chunking.markdown_parser import Block, parse_blocks
from iot_diagnosis.chunking.models import Chunk
from iot_diagnosis.chunking.token_chunker import ChunkerConfig, chunk_blocks
from iot_diagnosis.chunking.token_counter import TokenCounter, token_counter_from_env

__all__ = [
    "Block",
    "Chunk",
    "ChunkerConfig",
    "TokenCounter",
    "chunk_blocks",
    "parse_blocks",
    "token_counter_from_env",
]
