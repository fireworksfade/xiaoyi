from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

from iot_diagnosis.diagnosis import diagnose
from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retrieval import search_knowledge
from iot_diagnosis.router import route_query


def load_jsonl(path: Path) -> list[dict]:
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


def evaluate(
    dataset: list[dict],
    repository: DiagnosisRepository,
    top_k: int,
    profile: str = "deterministic",
    strategy: str | None = None,
) -> dict:
    recalls: list[float] = []
    precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    hits: list[float] = []
    latencies: list[float] = []
    stage_latencies: dict[str, list[float]] = {}
    router_correct = 0
    source_scores: list[float] = []
    diagnosis_correct: list[float] = []
    diagnosis_name_correct: list[float] = []
    token_usage = {"input": 0, "output": 0}
    embedding_provider = "local_lexical"
    reranker = {"provider": "weighted", "fallback": False}
    used_strategy = strategy or "hybrid"

    state = repository.get_device_status("ESP32_05")
    for case in dataset:
        logs = case.get("logs") or []
        route = route_query(case["query"], state, logs)
        router_correct += int(route.router == case["expected_router"])
        expected_sources = set(case["expected_sources"])
        actual_sources = set(route.sources)
        source_scores.append(
            len(expected_sources & actual_sources) / len(expected_sources)
            if expected_sources
            else 1.0
        )

        relevant_ids = set(case.get("relevant_ids") or [])
        if relevant_ids:
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
            embedding_provider = result["embedding_provider"]
            reranker = result["reranker"]
            used_strategy = result["strategy"]
            # 文档粒度匹配：chunk 边界随分块策略变化（Spec §28），
            # 相关性按逻辑文档判定（DOC#0000 → DOC）
            retrieved = [item["id"].split("#", 1)[0] for item in result["results"]]
            relevant_docs = {rid.split("#", 1)[0] for rid in relevant_ids}
            matches = relevant_docs & set(retrieved)
            recalls.append(len(matches) / len(relevant_docs))
            precisions.append(len(matches) / max(1, top_k))
            ranks = [retrieved.index(item) + 1 for item in matches]
            reciprocal_ranks.append(1 / min(ranks) if ranks else 0.0)
            hits.append(float(bool(matches)))

        if case.get("expected_fault_type"):
            result = diagnose(
                repository,
                "ESP32_05",
                case["query"],
                logs,
                True,
            )
            diagnosis_correct.append(float(result["fault_type"] == case["expected_fault_type"]))
            if case.get("expected_fault_name"):
                diagnosis_name_correct.append(
                    float(result["fault_name"] == case["expected_fault_name"])
                )
            token_usage["input"] += result["observability"]["input_tokens"]
            token_usage["output"] += result["observability"]["output_tokens"]

    def mean(values: list[float]) -> float:
        return round(statistics.fmean(values), 4) if values else 0.0

    return {
        "profile": profile,
        "strategy": used_strategy,
        "cases": len(dataset),
        "embedding_provider": embedding_provider,
        "reranker": reranker,
        f"recall@{top_k}": mean(recalls),
        f"precision@{top_k}": mean(precisions),
        "mrr": mean(reciprocal_ranks),
        "hit_rate": mean(hits),
        "router_accuracy": round(router_correct / len(dataset), 4) if dataset else 0.0,
        "source_selection_accuracy": mean(source_scores),
        "diagnosis_accuracy": mean(diagnosis_correct),
        "diagnosis_name_accuracy": mean(diagnosis_name_correct),
        "average_retrieval_latency_ms": mean(latencies),
        "p50_retrieval_latency_ms": round(percentile(latencies, 0.50), 4),
        "p95_retrieval_latency_ms": round(percentile(latencies, 0.95), 4),
        "stage_latency_ms": {
            stage: {
                "average": mean(values),
                "p95": round(percentile(values, 0.95), 4),
            }
            for stage, values in sorted(stage_latencies.items())
        },
        "token_usage": token_usage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate IoT diagnosis RAG")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parents[1] / "evals" / "rag_router.jsonl",
    )
    parser.add_argument("--database", default="data/iot_diagnosis_eval.db")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--strategy",
        choices=("dense", "sparse", "hybrid"),
        default=None,
        help="检索策略对比（Spec §29）；缺省取 RAG_RETRIEVAL_STRATEGY",
    )
    parser.add_argument(
        "--profile",
        choices=("deterministic", "live-retrieval"),
        default="deterministic",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["DIAGNOSIS_LLM_API_KEY"] = ""
    os.environ["DIAGNOSIS_LLM_MODEL"] = ""
    os.environ["DIAGNOSIS_MYSQL_DSN"] = ""
    if args.profile == "deterministic":
        os.environ["DIAGNOSIS_QDRANT_URL"] = ""
        os.environ["DIAGNOSIS_EMBEDDING_PROVIDER"] = "hash"
        os.environ["DIAGNOSIS_EMBEDDING_DIMENSIONS"] = "384"
        os.environ["DIAGNOSIS_RERANKER_PROVIDER"] = "weighted"
    report = evaluate(
        load_jsonl(args.dataset),
        DiagnosisRepository(args.database),
        args.top_k,
        args.profile,
        args.strategy,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
