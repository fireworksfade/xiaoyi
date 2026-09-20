# RAG 检索链路升级 Spec

## 1. 背景

当前 `xiaoyi-mcp-services` 的知识库检索链路已经具备：

- 文档切分与入库
- Qwen3-Embedding-0.6B 向量化
- Qdrant Dense Retrieval
- lexical retrieval
- Qwen3-Reranker-0.6B 重排序
- Recall、MRR、Hit Rate、Latency 等基础 RAG Eval

当前主要问题：

1. 文档分块主要基于固定字符长度，无法充分利用 Markdown 和技术文档结构。
2. 文档预处理可能破坏标题、日志、代码块、故障步骤等重要上下文。
3. Chunk size 尚未基于真实检索效果进行系统评测。
4. 当前 lexical retrieval 不是真正的 BM25。
5. Dense 与 lexical score 不属于同一分布，不适合直接进行 raw score 融合。
6. 需要形成稳定的 Dense + BM25 + Reranker Hybrid Retrieval。

本次升级目标是在不替换现有 Embedding 和 Reranker 模型的情况下，提高技术知识库、故障排查文档、Markdown 文档和日志类文档的召回与排序质量。

# 2. Goals

本次改造完成以下六个目标。

## G1. 固定字符分块升级为结构感知 + Token 分块

改造成：

```
Document
  ↓
Structure-aware Parsing
  ↓
Structural Blocks
  ↓
Token-aware Chunking
  ↓
Chunks
```

Chunk 长度统一使用 token 数计算。

默认：

```
chunk_size: 512
chunk_overlap: 64
```

Eval 支持：

```
384
512
768
1024
```

## G2. 保留技术文档结构

必须尽可能保留：

- Markdown heading
- heading hierarchy
- fenced code block
- shell command
- 配置文件
- 日志
- stack trace
- numbered list
- bullet list
- troubleshooting steps
- table
- paragraph

禁止 normalization 将这些内容全部压平成单行普通文本。

例如：

```
# MQTT

## Keep Alive 超时

### 日志

```text
mqtt timeout
connection closed
reconnecting...
```

### 排查步骤

1. 检查 keepalive 配置
2. 检查 broker timeout
3. 检查网络 RTT

```
生成 chunk 时必须保留标题上下文、日志换行和故障步骤边界。

---

## G3. Embedding 保持不变

继续使用：

```text
Qwen3-Embedding-0.6B
```

本次不更换 Embedding 模型。

新的 chunk pipeline 必须兼容现有 embedding 接口。

## G4. Chunk Size Eval

测试：

```
384
512
768
1024
```

默认从：

```
512 tokens
```

开始。

默认 overlap：

```
64 tokens
```

每种 chunk size 必须独立执行：

```
ingest
→ embedding
→ index
→ retrieve
→ rerank
→ eval
```

不同 chunk 策略之间不得复用旧索引。

## G5. Reranker 保持不变

继续使用：

```
Qwen3-Reranker-0.6B
```

整体流程：

```
Dense Retrieval
+
BM25 Retrieval
       ↓
RRF Fusion
       ↓
Candidate Set
       ↓
Qwen3-Reranker-0.6B
       ↓
Final Top-K
```

## G6. lexical retrieval 升级为 BM25 Hybrid

移除当前简单 lexical similarity 作为主要 lexical retrieval。

最终方案固定为：

```
Qdrant Dense Retrieval
+
SQLite FTS5 / BM25
+
RRF
+
Qwen3-Reranker-0.6B
```

本 Spec **不包含进一步迁移至 Qdrant Sparse Vector 或其他 Sparse Backend**。

SQLite FTS5 + BM25 即本次 sparse retrieval 的目标实现。

# 3. Non-Goals

本次不包含：

- 更换 Qwen3-Embedding-0.6B
- 更换 Qwen3-Reranker-0.6B
- Qdrant Sparse Vector
- Sparse Vector Migration
- Elasticsearch / OpenSearch
- Graph RAG
- Agentic Retrieval
- Query Rewrite
- HyDE
- Multi-query Retrieval
- Embedding Fine-tuning
- Reranker Fine-tuning
- 新增 LLM

# 4. Target Architecture

```
                    Raw Documentation
                           │
                           ▼
                Structure-aware Parser
                           │
                           ▼
                  Structural Blocks
                           │
                           ▼
                  Token-aware Chunker
                    512 / overlap 64
                           │
                           ▼
                 Qwen3-Embedding-0.6B
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
       Qdrant Dense                SQLite FTS5
         Retrieval                    BM25
         Top 40                       Top 40
             │                           │
             └─────────────┬─────────────┘
                           ▼
                        RRF
                           │
                           ▼
                   Candidate <= 60
                           │
                           ▼
                Qwen3-Reranker-0.6B
                           │
                           ▼
                        Top-K
```

# 5. Chunk 数据模型

Chunk 不再只使用字符串表示。

建议：

```
@dataclass
class Chunk:
    content: str
    document_id: str
    chunk_index: int

    title: str | None = None
    heading_path: list[str] | None = None
    block_type: str | None = None
    token_count: int | None = None
    source: str | None = None

    metadata: dict | None = None
```

推荐 `block_type`：

```
paragraph
code
log
list
steps
table
mixed
```

# 6. Qdrant Payload

Payload 至少包含：

```
{
  "document_id": "...",
  "chunk_index": 12,
  "title": "MQTT 故障排查",
  "heading_path": [
    "MQTT",
    "Keep Alive 超时"
  ],
  "block_type": "steps",
  "token_count": 487,
  "content": "...",
  "source": "..."
}
```

新增字段不得破坏已有查询接口。

# 7. Structure-aware Parser

识别：

```
# H1
## H2
### H3
#### H4
```

Parser 维护当前 heading stack。

例如：

```
# MQTT
## Connection
### Timeout
```

对应：

```
{
  "heading_path": [
    "MQTT",
    "Connection",
    "Timeout"
  ]
}
```

# 8. Heading Context Injection

Chunk 独立进入检索系统后不能失去标题语义。

例如：

```
# MQTT

## Keep Alive

设备频繁断开连接。
```

Embedding 内容：

```
# MQTT
## Keep Alive

设备频繁断开连接。
```

同时 metadata 保留：

```
{
  "heading_path": [
    "MQTT",
    "Keep Alive"
  ]
}
```

# 9. Code Block

Fenced code block 优先作为 atomic block。

如果：

```
token_count <= chunk_size
```

则不得拆分。

如果：

```
token_count > chunk_size
```

允许内部 token 分块，但需要保留：

- heading_path
- language
- block_type
- block sequence

例如：

```
{
  "block_type": "code",
  "language": "python",
  "block_sequence": 2,
  "block_total": 3
}
```

# 10. 日志处理

日志必须保留行边界。

例如：

```
2026-09-01 12:00:00 ERROR connection timeout
2026-09-01 12:00:01 INFO reconnecting
2026-09-01 12:00:02 ERROR reconnect failed
```

不得转换成：

```
2026... timeout 2026... reconnecting 2026... failed
```

对于超长日志：

```
log line
→ token budget
→ chunk
```

尽量不要截断单条日志。

# 11. Troubleshooting Steps

例如：

```
1. 检查设备 IP
2. ping gateway
3. 检查 MQTT broker
4. 查看 keepalive 配置
```

识别：

```
block_type = steps
```

整个 block 小于 chunk_size 时不拆。

超过 chunk_size 时：

```
按 step boundary 分块
```

不得优先使用任意 token boundary 把单个步骤拆开。

# 12. Table

Markdown 表格优先整体保存。

超长表格：

```
重复 header
+
按 row 分块
```

不得随机截断 table row。

# 13. Tokenizer

Chunk size 必须基于 tokenizer。

禁止使用：

```
text[:512]
```

或者：

```
len(text)
```

作为 token 长度判断。

建议抽象：

```
class TokenCounter:
    def count(self, text: str) -> int:
        ...

    def split(
        self,
        text: str,
        max_tokens: int
    ) -> list[str]:
        ...
```

Tokenizer 尽可能与 Qwen tokenizer 对齐。

# 14. Chunk Packing

Parser 首先生成：

```
Block[]
```

Chunk builder 再根据 token budget 合并相邻 block。

例如：

```
heading     20
paragraph  180
paragraph  140
steps      130
```

可以组成一个约：

```
470 tokens
```

的 chunk。

不要把每个 paragraph 都强制变成独立 chunk。

# 15. Boundary Priority

优先级：

```
Document
↓
Heading Section
↓
Structural Block
↓
Paragraph / Step / Log Line / Table Row
↓
Sentence
↓
Token Hard Split
```

Token hard split 只能作为最后 fallback。

# 16. Chunk Overlap

默认：

```
chunk_overlap: 64
```

Overlap 优先使用完整结构：

```
previous paragraph
previous step
previous heading context
```

无法满足时才采用纯 token overlap。

# 17. Chunk 配置

```
rag:
  chunking:
    strategy: structure_token
    chunk_size: 512
    chunk_overlap: 64

    preserve_code_blocks: true
    preserve_logs: true
    preserve_lists: true
    preserve_tables: true

    inject_heading_context: true
```

支持环境变量：

```
RAG_CHUNK_SIZE
RAG_CHUNK_OVERLAP
```

# 18. Embedding

固定：

```
Qwen3-Embedding-0.6B
```

Embedding 输入：

```
heading context
+
chunk content
```

不将以下字段加入 embedding text：

```
document_id
chunk_index
timestamp
internal metadata
```

# 19. Dense Retrieval

继续：

```
Qdrant
+
Qwen3-Embedding-0.6B
```

默认：

```
dense_top_k: 40
```

# 20. SQLite FTS5 / BM25

建立 FTS5 chunk index。

例如：

```
CREATE VIRTUAL TABLE knowledge_chunks_fts
USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    title,
    heading,
    content
);
```

查询示例：

```
SELECT
    chunk_id,
    bm25(knowledge_chunks_fts) AS score
FROM knowledge_chunks_fts
WHERE knowledge_chunks_fts MATCH ?
ORDER BY score
LIMIT ?;
```

需要根据 SQLite FTS5 BM25 score 的实际排序语义进行封装，避免调用方依赖原始 score 正负方向。

# 21. BM25 Indexed Content

索引：

```
title
heading_path
content
```

第一版以稳定实现为优先。

暂不要求复杂 field weighting。

# 22. BM25 Candidate 数量

默认：

```
sparse_top_k: 40
```

检索产生：

```
Dense Top 40
+
BM25 Top 40
```

合并去重后再做 RRF。

# 23. Candidate Deduplication

使用：

```
chunk_id
```

去重。

候选内部保留：

```
{
  "dense_rank": 3,
  "dense_score": 0.81,

  "sparse_rank": 7,
  "sparse_score": 4.3
}
```

Sparse raw score 仅用于 debug。

最终 hybrid 排序不直接使用 raw score 相加。

# 24. RRF

Dense cosine 和 BM25 score 不得直接：

```
dense_score + bm25_score
```

统一使用 Reciprocal Rank Fusion：

```
RRF(d) =
Σ 1 / (k + rank_i(d))
```

默认：

```
k = 60
```

示例：

```
score = 0.0

if dense_rank is not None:
    score += 1 / (60 + dense_rank)

if sparse_rank is not None:
    score += 1 / (60 + sparse_rank)
```

# 25. Candidate Limit

RRF 后最多选择：

```
60
```

个 candidate。

配置：

```
rerank_candidate_limit: 60
```

然后送入 Qwen3 Reranker。

# 26. Reranker

固定：

```
Qwen3-Reranker-0.6B
```

输入：

```
query
+
chunk
```

Chunk 中保留 heading context。

最终结果主要按照：

```
reranker_score DESC
```

排序。

# 27. Final Top-K

默认：

```
final_top_k: 5
```

Eval 测试：

```
Recall@1
Recall@3
Recall@5
Recall@10
```

# 28. Chunk Eval Matrix

必须测试：

| Chunk Size | Overlap |
| ---------- | ------- |
| 384        | 64      |
| 512        | 64      |
| 768        | 64      |
| 1024       | 64      |

默认 baseline：

```
512 / 64
```

# 29. Retrieval Strategy Eval

必须比较：

```
Dense Only

BM25 Only

Dense + BM25 + RRF

Dense + BM25 + RRF + Reranker
```

目的是分别确认：

- BM25 是否增加 lexical recall
- RRF 是否改善 hybrid candidate
- Reranker 是否改善最终排序

# 30. Eval Metrics

至少包含：

```
Recall@1
Recall@3
Recall@5
Recall@10

Precision@5

MRR

Hit Rate@5

P50 latency
P95 latency
```

Latency 拆分：

```
embedding
dense retrieval
BM25 retrieval
RRF
reranker
total
```

如果 dataset 支持 graded relevance，可增加：

```
NDCG@5
NDCG@10
```

# 31. Chunk Statistics

每次 Eval 输出：

```
document_count
chunk_count

avg_chunks_per_document

avg_tokens_per_chunk
P50_tokens_per_chunk
P95_tokens_per_chunk
max_tokens_per_chunk
```

# 32. Eval Output

建议：

```
eval_results/
    chunk_384.json
    chunk_512.json
    chunk_768.json
    chunk_1024.json

    summary.json
    summary.md
```

Summary：

| Chunk | Recall@5 | MRR  | P95  | Chunk Count |
| ----- | -------- | ---- | ---- | ----------- |
| 384   | ...      | ...  | ...  | ...         |
| 512   | ...      | ...  | ...  | ...         |
| 768   | ...      | ...  | ...  | ...         |
| 1024  | ...      | ...  | ...  | ...         |

# 33. Chunk Size 选择标准

综合：

```
Recall@5
MRR
P95
Index Size
Chunk Count
Reranker Context Cost
```

如果 512 与 768 / 1024 的检索指标接近，而 512：

- 定位更精确
- latency 更低
- reranker 输入更短
- index cost 可接受

则采用：

```
512
```

作为 production 默认值。

# 34. Backward Compatibility

已有：

```
search_knowledge(query, top_k)
```

调用方式尽量保持不变。

内部允许扩展：

```
search_knowledge(
    query,
    top_k=5,
    strategy="hybrid",
)
```

支持：

```
dense
sparse
hybrid
```

主要用于：

- Eval
- Debug
- Fallback

默认 production：

```
hybrid
```

# 35. Feature Flags

```
retrieval:
  enable_sparse: true
  enable_rrf: true
  enable_reranker: true
```

允许分别关闭组件用于测试和 fallback。

# 36. Observability

Debug mode 输出：

```
{
  "query": "...",

  "dense_candidates": 40,
  "sparse_candidates": 40,
  "merged_candidates": 57,
  "rerank_candidates": 57,
  "returned": 5,

  "latency_ms": {
    "embedding": 22,
    "dense": 11,
    "sparse": 4,
    "fusion": 1,
    "rerank": 143,
    "total": 181
  }
}
```

默认不得打印完整敏感知识库内容。

# 37. Retrieval Debug Metadata

开发环境中可返回：

```
{
  "chunk_id": "...",

  "dense_rank": 3,
  "dense_score": 0.78,

  "sparse_rank": 2,
  "sparse_score": 5.31,

  "rrf_score": 0.0317,

  "reranker_score": 0.91
}
```

用于分析召回来源与最终排序变化。

# 38. Implementation Phases

## Phase 1 — Structure-aware Chunking

实现：

```
Markdown parser
heading tracking
code preservation
log preservation
steps/list preservation
table preservation
token chunker
chunk metadata
```

默认：

```
512 / 64
```

## Phase 2 — Chunk Eval

执行：

```
384
512
768
1024
```

确定 production chunk size。

## Phase 3 — BM25

实现：

```
SQLite FTS5
+
BM25 Retrieval
```

替换当前简单 lexical retrieval。

## Phase 4 — Hybrid Retrieval

实现：

```
Qdrant Dense
+
SQLite BM25
+
RRF
```

RRF 输出最多 60 个候选。

## Phase 5 — Reranker + Hybrid Eval

接入现有：

```
Qwen3-Reranker-0.6B
```

对比：

```
Dense
BM25
Hybrid
Hybrid + Reranker
```

根据 Eval 确定最终参数。

**Phase 5 即本次检索架构升级的终态。**

不再增加：

```
Qdrant Sparse
Sparse Vector Migration
其它 Sparse Backend
```

# 39. Suggested Module Structure

推荐：

```
iot_diagnosis/
    ingestion.py

    chunking/
        models.py
        markdown_parser.py
        token_chunker.py
        token_counter.py

    retrieval/
        dense.py
        bm25.py
        fusion.py
        hybrid.py

    reranker.py

scripts/
    evaluate_rag.py
    evaluate_chunk_sizes.py
```

不要求一次性重构全部目录。

但职责应逐步明确为：

```
Parser
↓
Chunker
↓
Dense / BM25 Retriever
↓
RRF
↓
Reranker
```

# 40. Testing

## Chunking Tests

至少覆盖：

```
heading inheritance
code block preservation
log line preservation
numbered steps preservation
table preservation

token limit
overlap

very long paragraph
very long code block
very long logs

Chinese
English
Chinese + English
```

## BM25 Tests

重点测试精确技术词：

```
ERR_CONNECTION_RESET
MQTT_KEEPALIVE
mosquitto.conf
AT+CGATT
error code
command
model number
configuration key
```

这些 query 应能体现 BM25 相对于 Dense Retrieval 的补充价值。

## Hybrid Tests

至少覆盖：

```
dense-only hit
BM25-only hit
both hit

candidate deduplication

RRF ordering

reranker reorder
```

# 41. Acceptance Criteria

## AC1

默认 chunker 不再以固定字符长度为主要策略。

必须采用：

```
Structure-aware + Token-aware
```

## AC2

Markdown heading hierarchy 可在 metadata 中读取。

## AC3

正常长度 code block 不被破坏。

## AC4

日志保持换行和行边界。

## AC5

故障排查步骤优先按 step boundary 分块。

## AC6

默认：

```
chunk_size = 512
chunk_overlap = 64
```

且支持配置修改。

## AC7

能够执行：

```
384
512
768
1024
```

四组 chunk Eval。

## AC8

Embedding 保持：

```
Qwen3-Embedding-0.6B
```

## AC9

Reranker 保持：

```
Qwen3-Reranker-0.6B
```

## AC10

当前 lexical retrieval 替换为：

```
SQLite FTS5 + BM25
```

## AC11

Dense 与 BM25 不直接 raw score 相加。

必须使用：

```
RRF
```

进行 rank fusion。

## AC12

Hybrid retrieval 可关闭并 fallback 至 Dense Retrieval。

## AC13

Eval 至少输出：

```
Recall@5
MRR
Hit Rate
P50
P95
```

## AC14

现有 API / MCP 调用方不需要大规模修改。

## AC15

本次实现不得增加 Qdrant Sparse Vector 依赖。

Sparse Retrieval 的正式实现固定为：

```
SQLite FTS5 + BM25
```

# 42. Default Configuration

```
rag:
  embedding:
    model: Qwen3-Embedding-0.6B

  chunking:
    strategy: structure_token

    chunk_size: 512
    chunk_overlap: 64

    preserve_code_blocks: true
    preserve_logs: true
    preserve_lists: true
    preserve_tables: true

    inject_heading_context: true

  retrieval:
    strategy: hybrid

    dense_top_k: 40
    sparse_top_k: 40

    fusion: rrf
    rrf_k: 60

    rerank_candidate_limit: 60

    final_top_k: 5

  reranker:
    model: Qwen3-Reranker-0.6B
```

# 43. Final Architecture

最终架构固定为：

```
Markdown / Logs / Code / Troubleshooting Docs
                     ↓
          Structure-aware Parser
                     ↓
             Token Chunker
              512 / 64
                     ↓
          Qwen3-Embedding-0.6B
                     ↓
          ┌──────────┴──────────┐
          │                     │
     Qdrant Dense          SQLite FTS5
       Top 40               BM25 Top 40
          │                     │
          └──────────┬──────────┘
                     ↓
                    RRF
                     ↓
               Candidate ≤ 60
                     ↓
          Qwen3-Reranker-0.6B
                     ↓
                  Top 5
```

本项目不继续扩展第二套 sparse infrastructure。

核心技术栈固定为：

```
Qdrant = Dense Retrieval

SQLite FTS5 = BM25 Retrieval

RRF = Hybrid Fusion

Qwen3-Reranker-0.6B = Final Ranking
```

# 44. Implementation Priority

```
P0
Structure-aware Parser
        ↓
Token Chunker
        ↓
512 / 64 Default
        ↓
Chunk Metadata

P1
384 / 512 / 768 / 1024 Eval

P2
SQLite FTS5 + BM25

P3
Dense + BM25 + RRF

P4
Qwen3-Reranker Integration Verification

P5
Hybrid Eval + Production Parameter Tuning
```

**P5 完成后即结束本次架构升级。**

核心原则：

> 先提高 Chunk 质量，再扩大召回；先通过 Eval 验证，再增加复杂度。

最终以以下指标作为验收依据：

```
Recall
MRR
Hit Rate
Latency
结构保真度
检索稳定性
```

而不是以增加更多检索组件为目标。