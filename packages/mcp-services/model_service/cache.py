"""检索模型缓存完整性检查。

模型服务启动前必须确认两个模型的必要文件已经存在于持久卷中；
offline 模式缺失时给出稳定错误码 MODEL_CACHE_INCOMPLETE，而不是停留在无说明的重启循环。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from model_service.errors import CONFIGURATION_ERROR, MODEL_CACHE_INCOMPLETE, ModelServiceError

ERROR_CACHE_INCOMPLETE = MODEL_CACHE_INCOMPLETE

# 一个模型缓存完整至少需要：配置、tokenizer、权重各一份。
_REQUIRED_KINDS = {
    "config": ("config.json",),
    "tokenizer": ("tokenizer.json", "tokenizer_config.json", "spm.model"),
    "weights": ("model.safetensors", "pytorch_model.bin"),
}


@dataclass
class ModelCacheStatus:
    cache_mode: str
    embedding_model_cached: bool = False
    reranker_model_cached: bool = False
    loading_stage: str = "checking"
    last_error_code: str | None = None
    detail: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "embedding_model_cached": self.embedding_model_cached,
            "reranker_model_cached": self.reranker_model_cached,
            "cache_mode": self.cache_mode,
            "loading_stage": self.loading_stage,
            "last_error_code": self.last_error_code,
            "detail": self.detail,
        }

    @property
    def complete(self) -> bool:
        return self.embedding_model_cached and self.reranker_model_cached


def _model_relative_paths(model_name: str) -> list[Path]:
    """HF hub 缓存相对路径：models--<org>--<name>/snapshots/<rev>/。"""
    org, _, name = model_name.partition("/")
    safe = f"models--{org}--{name}" if org else f"models--{name}"
    return [Path("hub") / safe / "snapshots"]


def _snapshot_dirs(model_root: Path) -> list[Path]:
    if not model_root.is_dir():
        return []
    return sorted(
        (item for item in model_root.iterdir() if item.is_dir()), key=lambda p: p.stat().st_mtime
    )


def _find_file(directory: Path, kind: str, names: tuple[str, ...]) -> Path | None:
    if not directory.is_dir():
        return None
    for item in sorted(directory.rglob("*")):
        if not item.is_file():
            continue
        if item.name in names:
            return item
    # 权重分片（model-00001-of-00002.safetensors 等）也视为有效权重。
    if kind == "weights":
        for item in sorted(directory.rglob("*")):
            if item.is_file() and item.suffix in {".safetensors", ".bin"}:
                return item
    return None


def inspect_model_cache(models_dir: Path, model_name: str) -> tuple[bool, dict]:
    """检查单个模型的缓存文件清单，返回 (完整, 明细)。"""
    detail: dict = {"model": model_name, "files": {}}
    if not model_name:
        detail["error"] = "MODEL_NAME_EMPTY"
        return False, detail
    for relative in _model_relative_paths(model_name):
        snapshots_root = models_dir / relative
        for snapshot in _snapshot_dirs(snapshots_root):
            files_found = True
            for kind, names in _REQUIRED_KINDS.items():
                found = _find_file(snapshot, kind, names)
                detail["files"][kind] = str(found.relative_to(models_dir)) if found else None
                if not found:
                    files_found = False
            if files_found:
                detail["snapshot"] = str(snapshot.relative_to(models_dir))
                return True, detail
    return False, detail


def inspect_cache(
    models_dir: Path,
    embedding_model: str,
    reranker_model: str,
    cache_mode: str,
) -> ModelCacheStatus:
    status = ModelCacheStatus(cache_mode=cache_mode)
    status.loading_stage = "checking"
    embedding_ok, embedding_detail = inspect_model_cache(models_dir, embedding_model)
    reranker_ok, reranker_detail = inspect_model_cache(models_dir, reranker_model)
    status.embedding_model_cached = embedding_ok
    status.reranker_model_cached = reranker_ok
    status.detail = {"embedding": embedding_detail, "reranker": reranker_detail}
    if not status.complete:
        status.last_error_code = ERROR_CACHE_INCOMPLETE
        status.loading_stage = "failed"
    else:
        status.last_error_code = None
        status.loading_stage = "cache_ok"
    return status


def resolve_cache_mode() -> str:
    """download 为默认模式（全新环境可联网拉取）；offline 禁止网络下载。"""
    mode = os.getenv("MODEL_CACHE_MODE", "download").strip().lower()
    if mode not in {"download", "offline"}:
        raise ModelServiceError(
            CONFIGURATION_ERROR,
            f"MODEL_CACHE_MODE 无效: {mode}",
        )
    return mode


def dump_status(status: ModelCacheStatus) -> str:
    return json.dumps(status.to_dict(), ensure_ascii=False, indent=2)
