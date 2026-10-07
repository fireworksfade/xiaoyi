# Embedding / Reranker API 配置

Docker Compose 自动读取仓库根目录 `.env`；模板为根目录 `.env.example`。
Embedding 和 Reranker 可独立切换。模板里的 provider、模型、地址和密钥留空，
不会启用外部 API；基础 Compose 仍使用 hash / weighted，本地模型叠加档位仍使用 Qwen3。

下面是外部 API 的配置形状，请将示例地址、模型、密钥和维度换成服务的真实值：

```dotenv
DIAGNOSIS_EMBEDDING_PROVIDER=openai_compatible
DIAGNOSIS_EMBEDDING_BASE_URL=https://embedding.example.com/v1
DIAGNOSIS_EMBEDDING_MODEL=your-embedding-model
DIAGNOSIS_EMBEDDING_API_KEY=your-embedding-key
DIAGNOSIS_EMBEDDING_DIMENSIONS=1024
DIAGNOSIS_EMBEDDING_TIMEOUT_SECONDS=20
DIAGNOSIS_EMBEDDING_QUERY_INSTRUCTION=
DIAGNOSIS_QDRANT_COLLECTION=iot_diagnosis_api_v1

DIAGNOSIS_RERANKER_PROVIDER=remote
DIAGNOSIS_RERANKER_URL=https://reranker.example.com/v1/rerank
DIAGNOSIS_RERANKER_MODEL=your-reranker-model
DIAGNOSIS_RERANKER_API_KEY=your-reranker-key
DIAGNOSIS_RERANKER_TIMEOUT_SECONDS=30
```

Embedding 接口必须支持 `POST /embeddings`，请求字段为 `model`、`input`（文本数组）、
`dimensions`，响应为 `data: [{index, embedding}]`。维度应与 API 实际输出一致。
查询指令为空时发送原始查询；Qwen 类模型可保留模板中的指令前缀。

Reranker URL 是完整接口地址。请求字段为 `query`、`documents`、`top_n`，
配置模型名后额外发送 `model`，配置密钥后发送 `Authorization: Bearer ...`。
支持响应 `results: [{index, relevance_score}]` 或本地服务的 `results: [{index, score}]`，
结果需按相关性降序覆盖全部候选。接口失败或结果无效时，优先使用已启用的本地 Qwen 兜底，最后回退 weighted 重排。
其他协议需要另加适配器。

## 百炼 DashScope

两个 provider 均可填写 `DashScope`（不区分大小写）。Embedding 的 BASE_URL 可继续填写
`compatible-mode/v1` 地址，客户端自动转换为同一地域的原生 Embedding 地址；
也支持 `/api/v1` 基础地址或完整的原生 Embedding 地址。原生请求使用
`input.texts` 和 `parameters.dimension/text_type`，响应兼容 `index` / `text_index`，
并将批量输入切成最多 10 条一次。查询与文档分别发送 query/document 类型。
`DIAGNOSIS_EMBEDDING_QUERY_INSTRUCTION` 非空时作为原生 `instruct` 参数发送。
实测当前 flash 模型兼容接口在批量请求中返回重复的 index=0，故 DashScope 档位采用
原生接口并保留完整的索引、维度和数值校验，避免向量与文档错配。
原生协议参考 [百炼 Embedding API](https://www.alibabacloud.com/help/zh/model-studio/text-embedding-synchronous-api)。

百炼原生 Reranker 设置 `DIAGNOSIS_RERANKER_PROVIDER=DashScope`，URL 填
`https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank`
或对应地域/业务空间的同类完整地址，模型和密钥按当前账号填写。
客户端发送 `model`、`input: {query, documents}`、`parameters: {top_n, return_documents}`，
读取 `output.results`，并继续执行原有排名融合和失败兜底。
如果模型使用顶层 `query/documents`、顶层 `results` 的兼容重排接口，provider 应设为 `remote`。
协议与模型适用范围参见 [百炼排序 API](https://www.alibabacloud.com/help/zh/model-studio/text-rerank-api)。

改好 `.env` 后使用基础 Compose 重建容器配置：

```bash
docker compose up -d --force-recreate iot-mcp
```

外部 API 部署使用基础 `compose.yaml` 即可，无需启动本地 GPU 模型服务。
更换 Embedding 模型时，即使维度相同也应使用新的 Qdrant 集合，然后调用
`rebuild_vector_index` 工具重建；只修改 Reranker 不需要重建向量。
这些 `DIAGNOSIS_*` 设置作用于 IoT 知识检索；后端记忆检索使用 `RETRIEVAL_EMBEDDING_*` 设置。
根目录 `.env` 已被 Git 忽略，不会提交真实密钥。

## API 主模型与自动兜底

当前项目的 `.env` 使用 DashScope API 作为主 Embedding（1024 维）和主 Reranker。
正常请求始终先调用 API，不需要手动切换 provider。兜底配置也在根目录 `.env`：

```dotenv
DIAGNOSIS_EMBEDDING_FALLBACK=true
DIAGNOSIS_EMBEDDING_FALLBACK_DIMENSIONS=384
DIAGNOSIS_QDRANT_FALLBACK_COLLECTION=iot_diagnosis_portable
```

- 启用本地模型兜底后，Embedding 顺序为 API（1024 维）→ 本地 Qwen3-Embedding-0.6B（512 维）→ hash（384 维），每一层都有独立的集合。
- Reranker 顺序为 API → 本地 Qwen3-Reranker-0.6B → weighted。
- 下次请求继续优先尝试 API，恢复后自动回到主模型，不会一直停留在兜底模式。
- 主模型写入成功后同步更新 hash 集合；API 写入失败时先写入兜底集合，
  同时进入 outbox 队列，API 恢复后补齐主集合。本地模型可用时也同步维护其集合；
  本地模型写入失败期间仍维护 hash 集合，本地恢复后可重建其索引。

三种向量使用独立的集合，不能混写。兜底仍依赖 Qdrant 服务；Qdrant 本身不可用时，
现有 hybrid 检索继续使用 SQLite BM25/词法通道。

本地 0.6B 兜底开关与地址也在 `.env` 中：

```dotenv
DIAGNOSIS_LOCAL_EMBEDDING_FALLBACK=true
DIAGNOSIS_LOCAL_EMBEDDING_BASE_URL=http://retrieval-models:9010/v1
DIAGNOSIS_LOCAL_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
DIAGNOSIS_LOCAL_EMBEDDING_DIMENSIONS=512
DIAGNOSIS_LOCAL_QDRANT_COLLECTION=iot_diagnosis_qwen3_512
DIAGNOSIS_LOCAL_RERANKER_FALLBACK=true
DIAGNOSIS_LOCAL_RERANKER_URL=http://retrieval-models:9010/rerank
DIAGNOSIS_LOCAL_RERANKER_MODEL=Qwen/Qwen3-Reranker-0.6B
```

启动 API 主模型与本地模型兜底档位：

```bash
docker compose -f compose.yaml -f compose.retrieval-api-fallback.yaml up -d
```

该叠加文件复用已有 Qwen 模型服务和缓存，不覆盖主 API 配置，也不要求本地模型
健康后才启动 IoT 服务。首次启用时应给本地 512 维集合写入现有知识内容。
已有缓存时默认离线加载；首次下载可将 `LOCAL_MODEL_CACHE_MODE=download`。
只重建本地兜底索引、不重复调用主 API 的命令：

```bash
docker compose -f compose.yaml -f compose.retrieval-api-fallback.yaml exec -T iot-mcp python -m scripts.rebuild_fallback_indexes --target local
```

本地模型恢复后也可用该命令补齐停机期间缺失的内容。`--target hash` 可重建最后一层兜底索引。
检索返回的 `embedding_provider`、`embedding_collection` 与 `reranker.provider` 表示实际使用的档位。
