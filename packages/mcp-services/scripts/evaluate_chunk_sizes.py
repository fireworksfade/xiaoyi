"""Chunk Size Eval（Spec《RAG 检索链路升级》§28、§30-§33）。

对 384 / 512 / 768 / 1024（overlap 64）逐组独立执行
ingest → embedding → index → retrieve → rerank → eval；
每组使用全新临时数据库与索引，不复用旧索引（Spec G4）。
输出 eval_results/chunk_{size}.json 与 summary.json / summary.md。

确定性 profile 下用进程内 cosine 索引模拟 dense 通道（hash embedding）；
live-retrieval profile 需已配置 DIAGNOSIS_QDRANT_URL / embedding / reranker，
每个 chunk size 使用独立 collection（{collection}_{size}）避免索引串扰。
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iot_diagnosis.embeddings import HashEmbeddingProvider  # noqa: E402
from iot_diagnosis.ingestion import ingest_text  # noqa: E402
from iot_diagnosis.repository import DiagnosisRepository  # noqa: E402
from iot_diagnosis.retrieval import search_knowledge  # noqa: E402
from iot_diagnosis.router import route_query  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _load_document_mapping() -> list[tuple[str, str, str, str]]:
    spec = importlib.util.spec_from_file_location(
        "ingest_recommended_documents",
        ROOT / "scripts" / "ingest_recommended_documents.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("INGEST_MAPPING_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        (filename, source, document_id, title)
        for filename, source, document_id, title in module.DOCUMENTS
    ]


class LocalDenseIndex:
    """确定性 profile 的进程内 dense 通道（cosine over hash embeddings）。"""

    def __init__(self, provider: HashEmbeddingProvider):
        self.provider = provider
        self.items: dict[tuple[str, str], tuple[list[float], dict[str, Any]]] = {}

    def add(self, documents: list[dict[str, Any]]) -> None:
        for item in documents:
            key = (item["source"], item["source_id"])
            self.items[key] = (self.provider.embed(item["content"]), dict(item))

    def search(self, query: str, sources: list[str], top_k: int) -> list[dict[str, Any]]:
        query_vector = self.provider.embed(query, is_query=True)
        selected = set(sources)
        scored = []
        for (source, source_id), (vector, item) in self.items.items():
            if selected and source not in selected:
                continue
            score = sum(a * b for a, b in zip(query_vector, vector, strict=True))
            scored.append((score, source, source_id, item))
        scored.sort(key=lambda row: row[0], reverse=True)
        return [
            {
                **item,
                "id": source_id,
                "score": round(score, 6),
            }
            for score, _, source_id, item in scored[:top_k]
        ]


def attach_local_dense(repository: DiagnosisRepository, index: LocalDenseIndex) -> None:
    repository.vector_search = lambda query, sources, top_k, query_vector=None: index.search(
        query, sources, top_k
    )


def ingest_corpus(
    repository: DiagnosisRepository,
    mapping: list[tuple[str, str, str, str]],
    chunk_size: int,
    overlap: int,
) -> int:
    knowledge_dir = ROOT / "knowledge"
    total = 0
    for filename, source, document_id, title in mapping:
        content = (knowledge_dir / filename).read_text(encoding="utf-8")
        result = ingest_text(
            repository,
            source=source,
            document_id=document_id,
            title=title,
            content=content,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        total += result["chunk_count"]
    return total


def chunk_statistics(repository: DiagnosisRepository, top_k: int) -> dict[str, Any]:
    rows = repository.knowledge_documents(["mqtt_docs", "wifi_docs", "sensor_docs", "device_docs"])
    tokens = [int(row.get("token_count") or 0) for row in rows]
    documents = {(row["source"], row.get("document_id") or "") for row in rows}
    return {
        "document_count": len(documents),
        "chunk_count": len(rows),
        "avg_chunks_per_document": round(len(rows) / len(documents), 2) if documents else 0.0,
        "avg_tokens_per_chunk": round(statistics.fmean(tokens), 1) if tokens else 0.0,
        "p50_tokens_per_chunk": percentile([float(t) for t in tokens], 0.50),
        "p95_tokens_per_chunk": percentile([float(t) for t in tokens], 0.95),
        "max_tokens_per_chunk": max(tokens, default=0),
        "eval_top_k": top_k,
    }


def evaluate_chunk_size(
    size: int,
    overlap: int,
    dataset: list[dict],
    mapping: list[tuple[str, str, str, str]],
    top_k: int,
    strategy: str,
    workdir: Path,
    live: bool,
) -> dict[str, Any]:
    database = workdir / f"chunk_{size}.db"
    if live:
        os.environ["DIAGNOSIS_QDRANT_COLLECTION"] = (
            f"{os.getenv('DIAGNOSIS_QDRANT_COLLECTION', 'iot_diagnosis_qwen3')}_{size}"
        )
    repository = DiagnosisRepository(str(database))
    index = LocalDenseIndex(HashEmbeddingProvider(384))
    if not live:
        attach_local_dense(repository, index)

    started = time.perf_counter()
    ingest_corpus(repository, mapping, size, overlap)
    index.add(
        repository.knowledge_documents(["mqtt_docs", "wifi_docs", "sensor_docs", "device_docs"])
    )
    index.add(
        [
            {
                "source": "fault_cases",
                "source_id": case["fault_id"],
                "content": "；".join(
                    [
                        case["fault_name"],
                        *case["symptoms"],
                        *case["logs"],
                        case["cause"],
                        case["solution"],
                    ]
                ),
            }
            for case in repository.fault_cases()
        ]
    )
    index_ms = (time.perf_counter() - started) * 1000

    recalls: dict[int, list[float]] = {k: [] for k in (1, 3, 5, 10)}
    precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    hits: list[float] = []
    latencies: list[float] = []
    stage_latencies: dict[str, list[float]] = {}
    state = repository.get_device_status("ESP32_05")

    for case in dataset:
        relevant_docs = {rid.split("#", 1)[0] for rid in (case.get("relevant_ids") or [])}
        if not relevant_docs:
            continue
        logs = case.get("logs") or []
        route = route_query(case["query"], state, logs)
        started = time.perf_counter()
        result = search_knowledge(
            repository,
            case["query"],
            route.sources,
            top_k,
            state=state,
            logs=logs,
            strategy=strategy,
        )
        latencies.append((time.perf_counter() - started) * 1000)
        for stage, value in (result.get("latency_ms") or {}).items():
            if stage != "total":
                stage_latencies.setdefault(stage, []).append(float(value))
        # chunk size 变化会移动相关内容所在的 chunk 序号，按文档粒度匹配
        retrieved_docs = [item["id"].split("#", 1)[0] for item in result["results"]]
        for k in recalls:
            matches = relevant_docs & set(retrieved_docs[:k])
            recalls[k].append(len(matches) / len(relevant_docs))
        matches5 = relevant_docs & set(retrieved_docs[:5])
        precisions.append(len(matches5) / max(1, 5))
        ranks = [retrieved_docs.index(doc) + 1 for doc in relevant_docs if doc in retrieved_docs]
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0.0)
        hits.append(float(bool(relevant_docs & set(retrieved_docs))))

    def mean(values: list[float]) -> float:
        return round(statistics.fmean(values), 4) if values else 0.0

    stats = chunk_statistics(repository, top_k)
    return {
        "chunk_size": size,
        "chunk_overlap": overlap,
        "strategy": strategy,
        "match_granularity": "document",
        "cases": len(dataset),
        "chunking": {
            **stats,
            "index_duration_ms": round(index_ms, 2),
        },
        "retrieval": {
            "recall@1": mean(recalls[1]),
            "recall@3": mean(recalls[3]),
            "recall@5": mean(recalls[5]),
            "recall@10": mean(recalls[10]),
            "precision@5": mean(precisions),
            "mrr": mean(reciprocal_ranks),
            "hit_rate@5": mean(hits),
            "p50_latency_ms": round(percentile(latencies, 0.50), 2),
            "p95_latency_ms": round(percentile(latencies, 0.95), 2),
            "stage_latency_ms": {
                stage: {
                    "average": mean(values),
                    "p95": round(percentile(values, 0.95), 2),
                }
                for stage, values in sorted(stage_latencies.items())
            },
        },
    }


def write_summary(results: list[dict[str, Any]], output_dir: Path) -> None:
    summary = {"results": results, "baseline": {"chunk_size": 512, "chunk_overlap": 64}}
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    header = "| Chunk | Recall@5 | MRR | Hit Rate@5 | P95(ms) | Chunk Count |"
    divider = "| ----- | -------- | --- | ---------- | ------- | ----------- |"
    lines = [header, divider]
    for result in sorted(results, key=lambda item: item["chunk_size"]):
        retrieval = result["retrieval"]
        lines.append(
            f"| {result['chunk_size']} "
            f"| {retrieval['recall@5']} "
            f"| {retrieval['mrr']} "
            f"| {retrieval['hit_rate@5']} "
            f"| {retrieval['p95_latency_ms']} "
            f"| {result['chunking']['chunk_count']} |"
        )
    lines.append("")
    lines.append(
        "> Baseline: 512 / 64。若 512 与 768 / 1024 指标接近且 latency / index cost 更低，"
        "按 Spec §33 取 512 为 production 默认值。"
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG chunk sizes (Spec §28)")
    parser.add_argument("--sizes", default="384,512,768,1024")
    parser.add_argument("--overlap", type=int, default=64)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "evals" / "rag_router.jsonl",
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="单次检索条数，用于计算 Recall@1/3/5/10"
    )
    parser.add_argument("--strategy", default="hybrid", choices=("dense", "sparse", "hybrid"))
    parser.add_argument(
        "--profile",
        choices=("deterministic", "live-retrieval"),
        default="deterministic",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "eval_results")
    args = parser.parse_args()

    os.environ["DIAGNOSIS_LLM_API_KEY"] = ""
    os.environ["DIAGNOSIS_LLM_MODEL"] = ""
    os.environ["DIAGNOSIS_MYSQL_DSN"] = ""
    live = args.profile == "live-retrieval"
    if not live:
        os.environ["DIAGNOSIS_QDRANT_URL"] = ""
        os.environ["DIAGNOSIS_EMBEDDING_PROVIDER"] = "hash"
        os.environ["DIAGNOSIS_EMBEDDING_DIMENSIONS"] = "384"
        os.environ["DIAGNOSIS_RERANKER_PROVIDER"] = "weighted"

    dataset = load_jsonl(args.dataset)
    mapping = _load_document_mapping()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    # Windows 下 SQLite 连接依赖 GC 释放，TemporaryDirectory 自动清理会报
    # WinError 32；改为手动目录 + 忽略失败的清理。
    workdir = Path(tempfile.mkdtemp(prefix="rag_chunk_eval_"))
    try:
        for size in (int(item) for item in args.sizes.split(",")):
            print(f"Evaluating chunk_size={size} overlap={args.overlap} ...", flush=True)
            result = evaluate_chunk_size(
                size,
                args.overlap,
                dataset,
                mapping,
                args.top_k,
                args.strategy,
                workdir,
                live,
            )
            results.append(result)
            (args.output_dir / f"chunk_{size}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(result["retrieval"], ensure_ascii=False), flush=True)
    finally:
        gc.collect()
        shutil.rmtree(workdir, ignore_errors=True)

    write_summary(results, args.output_dir)
    print(f"Summary written to {args.output_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
