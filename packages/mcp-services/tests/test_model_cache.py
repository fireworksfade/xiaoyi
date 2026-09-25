"""模型缓存清单检查与缓存模式解析测试。"""

import json
from pathlib import Path

import pytest

from model_service.cache import (
    ERROR_CACHE_INCOMPLETE,
    inspect_cache,
    resolve_cache_mode,
)
from model_service.errors import ModelServiceError


def _write_model_cache(
    root: Path,
    model_name: str,
    *,
    with_config: bool = True,
    with_tokenizer: bool = True,
    with_weights: bool = True,
) -> Path:
    org, _, name = model_name.partition("/")
    snapshot = root / "hub" / f"models--{org}--{name}" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True, exist_ok=True)
    if with_config:
        (snapshot / "config.json").write_text("{}", encoding="utf-8")
    if with_tokenizer:
        (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    if with_weights:
        (snapshot / "model.safetensors").write_bytes(b"weights")
    return snapshot


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "models"


def test_complete_cache_passes(cache_dir: Path) -> None:
    _write_model_cache(cache_dir, "Qwen/Qwen3-Embedding-0.6B")
    _write_model_cache(cache_dir, "Qwen/Qwen3-Reranker-0.6B")
    status = inspect_cache(
        cache_dir, "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "offline"
    )
    assert status.complete
    assert status.embedding_model_cached
    assert status.reranker_model_cached
    assert status.last_error_code is None
    assert status.loading_stage == "cache_ok"


def test_missing_embedding_fails(cache_dir: Path) -> None:
    _write_model_cache(cache_dir, "Qwen/Qwen3-Reranker-0.6B")
    status = inspect_cache(
        cache_dir, "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "offline"
    )
    assert not status.complete
    assert not status.embedding_model_cached
    assert status.reranker_model_cached
    assert status.last_error_code == ERROR_CACHE_INCOMPLETE
    assert status.loading_stage == "failed"


def test_missing_reranker_fails(cache_dir: Path) -> None:
    _write_model_cache(cache_dir, "Qwen/Qwen3-Embedding-0.6B")
    status = inspect_cache(
        cache_dir, "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "offline"
    )
    assert not status.complete
    assert not status.reranker_model_cached
    assert status.last_error_code == ERROR_CACHE_INCOMPLETE


def test_incomplete_model_missing_weights(cache_dir: Path) -> None:
    _write_model_cache(cache_dir, "Qwen/Qwen3-Embedding-0.6B", with_weights=False)
    _write_model_cache(cache_dir, "Qwen/Qwen3-Reranker-0.6B")
    status = inspect_cache(
        cache_dir, "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "offline"
    )
    assert not status.complete
    detail = status.detail["embedding"]
    assert detail["files"]["weights"] is None
    assert detail["files"]["config"] is not None


def test_empty_cache_dir(cache_dir: Path) -> None:
    status = inspect_cache(
        cache_dir, "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "offline"
    )
    assert not status.complete
    assert status.last_error_code == ERROR_CACHE_INCOMPLETE
    payload = json.loads(json.dumps(status.to_dict()))
    assert payload["cache_mode"] == "offline"


def test_cache_mode_default_is_download(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_CACHE_MODE", raising=False)
    assert resolve_cache_mode() == "download"


def test_cache_mode_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_CACHE_MODE", "offline")
    assert resolve_cache_mode() == "offline"


def test_cache_mode_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_CACHE_MODE", "sometimes")
    with pytest.raises(ModelServiceError):
        resolve_cache_mode()


def test_sharded_weights_recognized(cache_dir: Path) -> None:
    org, _, name = "Qwen/Qwen3-Embedding-0.6B".partition("/")
    snapshot = cache_dir / "hub" / f"models--{org}--{name}" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot / "model-00001-of-00002.safetensors").write_bytes(b"a")
    (snapshot / "model-00002-of-00002.safetensors").write_bytes(b"b")
    status = inspect_cache(
        cache_dir, "Qwen/Qwen3-Embedding-0.6B", "Qwen/Qwen3-Reranker-0.6B", "download"
    )
    assert not status.complete  # reranker 缺失
    assert status.embedding_model_cached
