# IoT Diagnosis MCP Discovery Specification v1.3

- Status: Implemented and validated
- Date: 2026-09-11
- Extends: `iot-diagnosis-mcp-core-model-spec-v1.2.md`
- Priority: Core functionality; security and concurrency remain deferred

## 1. Purpose

Remove the requirement that an MCP client already knows a device ID, diagnosis ID, or knowledge
document ID. The service exposes compact inventories before the client drills into status, traces,
or retrieval.

## 2. Tools

### `list_devices`

Returns device metadata and the latest effective status. It supports optional `device_type` and
`online` filters plus bounded `limit`/`offset` pagination. Effective online state includes the
existing heartbeat freshness rule.

### `list_diagnoses`

Returns compact diagnosis summaries without the potentially large retrieved contexts. It supports
optional `device_id` and `fault_type` filters, `all`/`succeeded`/`failed` status selection, and
bounded pagination. A returned diagnosis ID can be passed to `get_diagnosis_trace`.

### `list_knowledge_documents`

Returns one entry per logical document rather than one entry per chunk. Each entry reports source,
document ID, base title, device type, chunk count, character count, and ingestion timestamp. It
supports source/device type filters and bounded pagination.

## 3. Compatibility

- The existing nine v1.2 tools and their response shapes remain unchanged.
- All three tools are read-only and use SQLite, the local source of truth.
- Every list response contains `items`, `total`, `limit`, and `offset`.
- The main backend enables these tools with its read-only policy during catalog bootstrap.

## 4. Acceptance criteria

- A client can discover a device and immediately call `get_device_status` or `diagnose_fault`.
- Effective online filtering distinguishes fresh and stale/offline device reports.
- Successful and failed diagnosis records can be listed independently.
- Multi-chunk knowledge is represented as one logical document with accurate aggregate counts.
- MCP discovery exposes twelve tools and all offline regression tests pass.
