# IoT Diagnosis MCP Completion Specification v1.1

- Status: Implemented and validated
- Date: 2026-09-10
- Extends: `iot-diagnosis-mcp-spec-v1.0.md`
- Compatibility: Existing six v1.0 tools and their successful response fields remain compatible

## 1. Purpose

v1.0 proves the local end-to-end diagnosis flow. v1.1 closes the remaining correctness,
traceability, ingestion, retrieval-quality, evaluation, and production-readiness gaps without
adding device-control capability.

## 2. Scope

### 2.1 Required

1. Durable external-store synchronization for MySQL and Qdrant.
2. Queryable diagnosis traces, including failed diagnoses.
3. Text, Markdown, and PDF knowledge ingestion with deterministic chunk identifiers.
4. Replaceable embedding and reranking interfaces with safe local defaults.
5. Reproducible RAG/router evaluation and latency reporting.
6. Optional bearer authentication, truthful liveness/readiness, and bounded request inputs.
7. Automated tests for success, degradation, recovery, and authorization boundaries.

### 2.2 Not in scope

- Device restart, firmware update, Wi-Fi/MQTT configuration changes.
- Internet/SerpAPI retrieval.
- Graph RAG, Self-RAG, multi-agent diagnosis, anomaly detection, or time-series models.
- Mandatory external model/provider dependencies for local development.

## 3. Compatibility rules

- Keep `diagnose_fault`, `get_device_status`, `get_device_logs`, `search_knowledge`,
  `search_fault_cases`, and `add_verified_fault_case`.
- New write-capable tools must advertise non-read-only MCP annotations and are disabled by
  default when first discovered by the main backend.
- Existing SQLite databases migrate in place. Migrations must be additive.
- Hash embeddings remain the offline default; configured provider embeddings are opt-in.
- When an external store is unavailable, the MCP process stays alive and exposes the degraded
  state explicitly.

## 4. External-store synchronization

### 4.1 Model

SQLite is the local source of truth. Each committed write that must be mirrored creates or
updates an outbox item when delivery to MySQL or Qdrant fails.

Outbox fields:

- `id`
- `component`: `mysql` or `qdrant`
- `operation`
- `payload_json`
- `attempts`
- `last_error`
- `created_at`, `updated_at`, `completed_at`

### 4.2 Behaviour

- Immediate delivery is attempted after the SQLite transaction commits.
- Failed delivery is durable and retried by a background worker.
- A retry uses the same deterministic database key/vector point ID, making replay idempotent.
- `add_verified_fault_case` reports:
  - `indexed`: whether Qdrant accepted the write now;
  - `mysql_saved` and `vector_indexed`;
  - `sync_status`: `complete` or `pending`.
- The health payload includes pending outbox count.

### 4.3 Acceptance

- Simulated MySQL/Qdrant failure does not lose the local record.
- A pending item becomes completed after the component recovers.
- The API never reports `indexed: true` when the vector write failed.

## 5. Diagnosis traceability

### 5.1 New tool

`get_diagnosis_trace(diagnosis_id)` returns:

- query, device, diagnosis result or error;
- router and selected sources;
- retrieved/reranked contexts, including IDs, titles, content, and scores;
- latency and token observations;
- creation timestamp.

### 5.2 Failure records

Every accepted `diagnose_fault` invocation creates a diagnosis record. Device-not-found,
retrieval, model, and persistence failures record a normalized error code where local SQLite is
still writable. The failure response includes the generated `diagnosis_id`.

### 5.3 Acceptance

- A successful diagnosis can be retrieved by ID with its exact final contexts.
- Realtime rule queries return an exact answer and state without invoking the diagnosis LLM.
- The trace retains the complete final result snapshot, not only reconstructed core fields.
- A failed diagnosis can be retrieved by ID with a non-null error.
- Unknown IDs return `DIAGNOSIS_NOT_FOUND`.

## 6. Knowledge ingestion

### 6.1 Inputs

- MCP tool `ingest_knowledge_text` for already-extracted text/Markdown.
- CLI `scripts/ingest_documents.py` for `.txt`, `.md`, and `.pdf` files.

Required metadata:

- allowed source (`mqtt_docs`, `wifi_docs`, `sensor_docs`, `device_docs`);
- stable `document_id`;
- title;
- optional device type.

### 6.2 Pipeline

Parse → normalize whitespace → paragraph-aware chunk → overlap → metadata → SQLite → MySQL
mirror → vector index.

Chunk IDs use `<document_id>#<zero-padded-index>`. Re-ingesting the same document replaces its
old chunks. Qdrant payloads retain `document_id`, `chunk_index`, and source metadata.

### 6.3 Limits

- MCP text input: 200,000 characters maximum.
- Chunk size: 300–4,000 characters.
- Overlap: 0–500 characters and smaller than chunk size.
- Empty extracted documents are rejected.

## 7. Embedding and reranking

### 7.1 Embedding interface

`EmbeddingProvider.embed(text) -> list[float]` with:

- deterministic hash provider for offline/test use;
- OpenAI-compatible `/embeddings` provider configured by environment variables;
- explicit dimensions and collection compatibility checks.

### 7.2 Reranker interface

`Reranker.rerank(query, candidates, context) -> candidates`.

The default weighted reranker combines normalized retrieval score, lexical similarity, source
relevance, and verified-case preference. It must be isolated from retrieval/fusion so a learned
reranker can replace it later.

### 7.3 Deployed model profile

- Compose embedding: `Qwen/Qwen3-Embedding-0.6B`, 1024 dimensions, GPU inference.
- Compose reranker: `Qwen/Qwen3-Reranker-0.6B`, official yes/no CausalLM scoring.
- Qdrant collection: `iot_diagnosis_qwen3`; legacy 384-dimensional data remains isolated.
- Model cache: persistent `retrieval-model-cache` volume.
- Retrieval responses expose provider and fallback metadata.

## 8. Evaluation and performance

- Versioned JSONL fixtures cover realtime queries and the ten specified MQTT, Wi-Fi, sensor,
  device-runtime, and network fault scenarios.
- Evaluation command reports Recall@K, Precision@K, MRR, Hit Rate, routing accuracy, source
  selection accuracy, fault-type accuracy, fault-name accuracy, average latency, and token usage
  when available.
- CI uses deterministic providers and fixed fixtures.
- Online model performance is reported separately and is not mixed with deterministic CI.
- Targets remain: realtime <500 ms, RAG <3 s, full online diagnosis <8 s; a report may mark a
  target unmet but must not hide the measurement.

## 9. Security and health

- If `DIAGNOSIS_MCP_BEARER_TOKEN` is set, `/mcp` requires that bearer token.
- `verified_by` remains server-derived when invoked through the main backend; direct MCP writes
  require authenticated transport in production.
- `/health` is liveness and returns 200 while the process can serve fallback behaviour.
- `/ready` is readiness and returns 503 when a required configured store is unavailable or the
  outbox backlog exceeds its configured threshold.
- Secrets never appear in logs, tool results, or health payloads.

## 10. Delivery order

1. Durable outbox and accurate write status.
2. Trace query and failure records.
3. Knowledge ingestion and replacement.
4. Embedding/reranker interfaces.
5. Evaluation command and fixtures.
6. Bearer authentication and readiness endpoint.
7. Full regression, README/Compose updates, and online smoke verification.

## 11. Definition of done

- All required behaviours above have automated tests.
- Existing v1.0 tests continue to pass after intentional assertion updates for accurate status.
- Local Compose liveness remains healthy with MySQL and Qdrant connected.
- Degraded-mode and recovery tests pass without external services.
- Main backend can refresh the catalog without enabling new write tools automatically.
- Documentation contains exact local, Compose, ingestion, evaluation, and authentication commands.

## 12. Implementation validation

- MCP offline regression suite: 28 passed; live Streamable HTTP suite: 29 passed.
- Backend regression suite: 10 passed.
- Deterministic 15-case evaluation: Recall@5 1.0, Hit Rate 1.0, Router Accuracy 1.0,
  Source Selection Accuracy 1.0, Diagnosis Accuracy 1.0, and Diagnosis Name Accuracy 1.0.
- Compose readiness: SQLite, MySQL, and Qdrant connected; outbox pending 0 after retry.
- Recovery drills: Qdrant write outage, startup MySQL contention, and a client missing at startup
  all reconnect and replay without data loss.
- Realtime rule response latency: approximately 1.8 ms without an LLM call.
- Latest online full diagnosis latency: approximately 45.3 seconds due to external-provider
  latency; functional acceptance passes, but the 8-second performance target is currently unmet.
