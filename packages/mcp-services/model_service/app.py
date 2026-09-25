from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# offline 模式必须在导入 huggingface_hub/transformers 之前生效；
# download 模式不设置 HF_HUB_OFFLINE，允许从配置的模型源下载缺失文件。
CACHE_MODE = os.getenv("MODEL_CACHE_MODE", "download").strip().lower()
if CACHE_MODE == "offline":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

MODELS_DIR = Path(os.getenv("HF_HOME", "/models"))

import numpy as np
import torch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

from model_service.cache import inspect_cache
from model_service.errors import MODEL_LOAD_FAILED, ModelServiceError

logger = logging.getLogger("xiaoyi.model_service")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B")
MAX_LENGTH = int(os.getenv("MODEL_MAX_LENGTH", "2048"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
RERANKER_BATCH_SIZE = int(os.getenv("RERANKER_BATCH_SIZE", "4"))
RERANKER_INSTRUCTION = os.getenv(
    "RERANKER_INSTRUCTION",
    "Rank passages and verified cases by relevance to an IoT fault diagnosis query",
)


class EmbeddingRequest(BaseModel):
    model: str | None = None
    input: str | list[str]
    dimensions: int | None = Field(default=None, ge=32, le=1024)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    documents: list[str] = Field(min_length=1, max_length=200)
    top_n: int = Field(default=5, ge=1, le=100)


models: dict[str, Any] = {}

# 并发 embedding 请求的 micro-batching：短窗口内到达的请求合并为一次
# GPU encode，避免并发单条请求各自触发一次前向。
EMBED_COALESCE_WINDOW_SECONDS = 0.005
EMBED_MAX_BATCH_TEXTS = 64


class _EmbedJob:
    def __init__(self, texts: list[str], dimensions: int | None):
        self.texts = texts
        self.dimensions = dimensions
        self.future: asyncio.Future[np.ndarray] = asyncio.get_running_loop().create_future()


_embed_queue: asyncio.Queue[_EmbedJob] | None = None
_embed_worker_task: asyncio.Task | None = None


def _encode_sync(texts: list[str]) -> np.ndarray:
    return models["embedding"].encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )


def _truncate_dimensions(vectors: np.ndarray, dimensions: int) -> np.ndarray:
    if dimensions >= vectors.shape[1]:
        return vectors
    truncated = vectors[:, :dimensions]
    norms = np.linalg.norm(truncated, axis=1, keepdims=True)
    return truncated / np.maximum(norms, 1e-12)


async def _embedding_worker() -> None:
    assert _embed_queue is not None
    loop = asyncio.get_running_loop()
    while True:
        job = await _embed_queue.get()
        batch = [job]
        batch_texts = len(job.texts)
        deadline = loop.time() + EMBED_COALESCE_WINDOW_SECONDS
        while batch_texts < EMBED_MAX_BATCH_TEXTS and not _embed_queue.empty():
            if loop.time() >= deadline:
                break
            batch.append(_embed_queue.get_nowait())
            batch_texts += len(batch[-1].texts)
        try:
            all_texts = [text for item in batch for text in item.texts]
            vectors = await loop.run_in_executor(None, _encode_sync, all_texts)
            offset = 0
            for item in batch:
                count = len(item.texts)
                item.future.set_result(vectors[offset : offset + count])
                offset += count
        except Exception as exc:
            for item in batch:
                if not item.future.done():
                    item.future.set_exception(exc)


service_state: dict[str, Any] = {
    "loading_stage": "starting",
    "last_error_code": None,
    "cache": None,
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    start = time.monotonic()
    # 启动前先做缓存清单检查；offline 缺失时不下载、不进入无说明的重启循环。
    status = inspect_cache(MODELS_DIR, EMBEDDING_MODEL, RERANKER_MODEL, CACHE_MODE)
    service_state["cache"] = status.to_dict()
    if not status.complete and CACHE_MODE == "offline":
        service_state["loading_stage"] = "failed"
        service_state["last_error_code"] = status.last_error_code
        logger.error(
            "model cache incomplete (mode=offline): %s",
            status.to_dict(),
            extra={"event": "model_cache_incomplete", "error_code": status.last_error_code},
        )
        # 进程保持存活，通过 /ready 暴露 MODEL_CACHE_INCOMPLETE，便于运维一次性定位。
        yield
        return

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        service_state["loading_stage"] = "loading_embedding"
        models["embedding"] = SentenceTransformer(
            EMBEDDING_MODEL,
            device=device,
            model_kwargs={"dtype": dtype},
            tokenizer_kwargs={"padding_side": "left"},
        )
        models["embedding"].max_seq_length = MAX_LENGTH
        service_state["loading_stage"] = "loading_reranker"
        reranker_tokenizer = AutoTokenizer.from_pretrained(RERANKER_MODEL, padding_side="left")
        reranker_model = (
            AutoModelForCausalLM.from_pretrained(RERANKER_MODEL, dtype=dtype).to(device).eval()
        )
        prefix = (
            "<|im_start|>system\nJudge whether the Document meets the requirements based on "
            'the Query and the Instruct provided. Note that the answer can only be "yes" or '
            '"no".<|im_end|>\n<|im_start|>user\n'
        )
        suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        models["reranker"] = reranker_model
        models["reranker_tokenizer"] = reranker_tokenizer
        models["reranker_prefix"] = reranker_tokenizer.encode(prefix, add_special_tokens=False)
        models["reranker_suffix"] = reranker_tokenizer.encode(suffix, add_special_tokens=False)
        models["reranker_false_id"] = reranker_tokenizer.convert_tokens_to_ids("no")
        models["reranker_true_id"] = reranker_tokenizer.convert_tokens_to_ids("yes")
        models["device"] = device
        global _embed_queue, _embed_worker_task
        _embed_queue = asyncio.Queue()
        _embed_worker_task = asyncio.create_task(_embedding_worker())
        service_state["loading_stage"] = "ready"
        service_state["last_error_code"] = None
        logger.info(
            "models loaded on %s in %.1fs (cache_mode=%s)",
            device,
            time.monotonic() - start,
            CACHE_MODE,
            extra={
                "event": "model_load_completed",
                "duration_ms": int((time.monotonic() - start) * 1000),
            },
        )
    except Exception as exc:
        service_state["loading_stage"] = "failed"
        service_state["last_error_code"] = MODEL_LOAD_FAILED
        logger.exception("model loading failed", extra={"event": "model_load_failed"})
        raise ModelServiceError(MODEL_LOAD_FAILED, str(exc)) from exc
    yield
    if _embed_worker_task is not None:
        _embed_worker_task.cancel()
        _embed_worker_task = None
    _embed_queue = None
    models.clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(title="IoT Diagnosis Qwen Retrieval Models", lifespan=lifespan)


def _ready_payload() -> dict[str, Any]:
    ready = "embedding" in models and "reranker" in models
    stage = service_state["loading_stage"]
    if ready:
        stage = "ready"
    elif service_state["last_error_code"]:
        stage = "failed"
    elif stage in {"starting", "checking"}:
        stage = "loading"
    return {
        "status": stage,
        "service": "retrieval-models",
        "device": models.get("device"),
        "cache_mode": CACHE_MODE,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_model_cached": (service_state.get("cache") or {}).get("embedding_model_cached"),
        "reranker_model": RERANKER_MODEL,
        "reranker_model_cached": (service_state.get("cache") or {}).get("reranker_model_cached"),
        "loading_stage": service_state["loading_stage"],
        "last_error_code": service_state["last_error_code"],
        "dimensions": 1024,
    }


@app.get("/live")
def live() -> dict[str, Any]:
    """进程事件循环可响应即返回 200。"""
    return {"status": "alive", "service": "retrieval-models"}


@app.get("/ready")
def ready() -> JSONResponse:
    """两个模型均加载且可执行最小推理才返回 200。"""
    payload = _ready_payload()
    if payload["status"] == "ready":
        return JSONResponse(status_code=200, content=payload)
    return JSONResponse(status_code=503, content=payload)


@app.get("/health")
def health() -> dict[str, Any]:
    """兼容旧探针；语义与 /ready 相同，新部署应使用 /live 与 /ready。"""
    return _ready_payload()


@app.post("/v1/embeddings")
async def embeddings(request: EmbeddingRequest) -> dict[str, Any]:
    texts = [request.input] if isinstance(request.input, str) else request.input
    assert _embed_queue is not None
    job = _EmbedJob(texts, request.dimensions)
    _embed_queue.put_nowait(job)
    vectors = await job.future
    dimensions = request.dimensions or int(vectors.shape[1])
    vectors = _truncate_dimensions(vectors, dimensions)
    return {
        "object": "list",
        "model": request.model or EMBEDDING_MODEL,
        "data": [
            {"object": "embedding", "index": index, "embedding": vector.tolist()}
            for index, vector in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.post("/rerank")
def rerank(request: RerankRequest) -> dict[str, Any]:
    tokenizer = models["reranker_tokenizer"]
    prefix_tokens = models["reranker_prefix"]
    suffix_tokens = models["reranker_suffix"]
    formatted = [
        (f"<Instruct>: {RERANKER_INSTRUCTION}\n<Query>: {request.query}\n<Document>: {document}")
        for document in request.documents
    ]
    tokenized = tokenizer(
        formatted,
        padding=False,
        truncation="longest_first",
        return_attention_mask=False,
        max_length=MAX_LENGTH - len(prefix_tokens) - len(suffix_tokens),
    )["input_ids"]
    scores: list[float] = []
    for offset in range(0, len(tokenized), RERANKER_BATCH_SIZE):
        input_ids = [
            prefix_tokens + item + suffix_tokens
            for item in tokenized[offset : offset + RERANKER_BATCH_SIZE]
        ]
        inputs = tokenizer.pad({"input_ids": input_ids}, padding=True, return_tensors="pt").to(
            models["device"]
        )
        with torch.no_grad():
            logits = models["reranker"](**inputs, logits_to_keep=1).logits[:, -1, :]
        yes_no_logits = torch.stack(
            [
                logits[:, models["reranker_false_id"]],
                logits[:, models["reranker_true_id"]],
            ],
            dim=1,
        )
        scores.extend(
            torch.nn.functional.softmax(yes_no_logits, dim=1)[:, 1].float().cpu().tolist()
        )
    ranked = sorted(
        ({"index": index, "score": float(score)} for index, score in enumerate(scores)),
        key=lambda item: item["score"],
        reverse=True,
    )
    return {
        "model": RERANKER_MODEL,
        "results": ranked[: min(request.top_n, len(ranked))],
    }
