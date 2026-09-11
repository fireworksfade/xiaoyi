# IoT Diagnosis MCP Core Model Specification v1.2

- Status: Implemented and validated
- Date: 2026-09-11
- Extends: `iot-diagnosis-mcp-completion-spec-v1.1.md`
- Priority: Core functionality; security and concurrency are deferred

## 1. Purpose

Complete the operational path for the deployed Qwen3 embedding and reranker models. The MCP
service must be able to verify model availability, index documents efficiently, rebuild the
vector collection from SQLite, and evaluate the real retrieval path separately from deterministic
CI evaluation.

## 2. Required functionality

### 2.1 Batch embeddings and vector writes

- `EmbeddingProvider` exposes `embed_many(texts, is_query=False)` in addition to `embed`.
- The hash provider and OpenAI-compatible provider implement the same batch contract.
- The OpenAI-compatible provider sends one `/embeddings` request for a batch and validates every
  returned index and vector dimension.
- Qdrant accepts multiple points in one upsert request.
- Knowledge-document replacement uses one batch model request and one batch Qdrant write when the
  external store is available.
- A failed batch write retains durable per-item outbox records so recovery remains idempotent.

### 2.2 Vector index rebuild

- Add a write-capable MCP tool `rebuild_vector_index`.
- SQLite remains the rebuild source of truth.
- The tool reindexes both knowledge chunks and verified fault cases.
- Optional source filtering is supported.
- The result reports attempted, indexed, pending, provider, collection, dimensions, duration, and
  synchronization status.
- A failure does not delete SQLite or MySQL data and is recoverable through the existing outbox.

### 2.3 Retrieval model readiness

- The MCP `/ready` route probes the configured local retrieval-model health endpoint.
- The response includes model status, embedding model, reranker model, dimensions, and device when
  available.
- A configured but unavailable model service makes readiness return HTTP 503 with issue
  `retrieval_models`.
- Hash-only/offline mode remains ready without a model-service endpoint.

### 2.4 Real retrieval evaluation

- The evaluation CLI supports `deterministic` and `live-retrieval` profiles.
- `deterministic` remains the default and keeps CI reproducible.
- `live-retrieval` preserves Qdrant, embedding, and reranker configuration while disabling the
  external diagnosis LLM so retrieval quality is measured independently.
- Reports identify the profile and providers and include average, p50, and p95 retrieval latency.
- The live report is written separately and never replaces deterministic CI results.

## 3. Delivery order

1. Batch embedding contract and Qdrant batch upsert.
2. Vector rebuild repository operation and MCP tool.
3. Model health probing and readiness integration.
4. Dual-profile evaluator, tests, Docker validation, and documentation.

## 4. Acceptance criteria

- Replacing a multi-chunk document performs one embedding HTTP request and one Qdrant upsert.
- Batch response reordering by `index` is handled correctly; missing or invalid vectors fail.
- Rebuild indexes all eligible SQLite records and reports accurate counts.
- Model outage is visible in `/ready`; recovery returns readiness to 200 without restarting MCP.
- Deterministic tests remain green.
- A Docker live-retrieval evaluation uses `openai_compatible` and `qwen3_remote` without fallback.
- Qdrant collection remains healthy and the external outbox returns to zero.

## 5. Validation results

- MCP regression: 33 passed, 1 skipped offline; live Streamable HTTP test passed.
- Live discovery and smoke: all 9 tools discovered and the full diagnosis path passed.
- Batch endpoint: two inputs returned two ordered 1024-dimensional vectors in one request.
- Vector rebuild: 7 attempted, 7 indexed, 0 pending, approximately 101 ms.
- Readiness: Qwen3 embedding and reranker reported ready on CUDA; all stores connected.
- Live retrieval evaluation: Recall@5 1.0, Hit Rate 1.0, MRR 0.8013, average 256.16 ms,
  P50 251.28 ms, P95 312.76 ms, with no reranker fallback.
