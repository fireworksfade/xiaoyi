"""检查检索模型缓存完整性并输出 JSON 状态。

用法：
    python -m scripts.check_model_cache [--models-dir /models]

退出码：0 缓存完整；1 缓存不完整或配置无效。供发布前校验 offline 模式可用性。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from model_service.cache import dump_status, inspect_cache, resolve_cache_mode


def main() -> int:
    parser = argparse.ArgumentParser(description="Check retrieval model cache completeness")
    parser.add_argument(
        "--models-dir",
        default=os.getenv("HF_HOME", "/models"),
        help="模型缓存根目录（默认 HF_HOME 或 /models）",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B"),
    )
    parser.add_argument(
        "--reranker-model",
        default=os.getenv("RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B"),
    )
    args = parser.parse_args()

    mode = resolve_cache_mode()
    status = inspect_cache(Path(args.models_dir), args.embedding_model, args.reranker_model, mode)
    print(dump_status(status))
    return 0 if status.complete else 1


if __name__ == "__main__":
    sys.exit(main())
