# IoT Diagnosis MCP Server Specification

- **Version:** 1.0
- **Status:** Draft / Implementation Ready
- **Target System:** 基于大语言模型的物联网节点智能故障诊断系统
- **Protocol:** Model Context Protocol 2026-07-28
- **Primary Language:** Python
- **Recommended Framework:** FastAPI + MCP Python SDK
- **Primary Device:** ESP32
- **Messaging:** MQTT
- **Database:** MySQL
- **Vector Database:** Chroma / Qdrant / FAISS
- **LLM:** 可配置
- **Embedding Model:** 可配置
- **Reranker:** 可配置

---

# 1. 系统目标

IoT Diagnosis MCP Server 用于将物联网故障诊断系统中的设备数据查询、故障知识检索、Adaptive Multi-Source RAG、故障诊断以及故障案例知识更新能力统一封装为 MCP Tools。

上层 LLM Agent 不需要直接访问 MQTT、MySQL、向量数据库或 RAG 内部实现，而通过统一 MCP 接口完成相关操作。

核心目标包括：

1. 提供标准化 IoT 故障诊断能力；
2. 封装 Hybrid Adaptive Multi-Source RAG；
3. 支持设备实时状态查询；
4. 支持历史故障案例与技术文档检索；
5. 支持规则 Router + LLM Router 混合自适应路由；
6. 支持检索结果融合与 Rerank；
7. 支持故障诊断结果结构化输出；
8. 支持人工确认后的故障案例动态入库；
9. 降低 Agent 与底层 IoT、数据库、RAG 系统之间的耦合。

---

# 2. 系统总体架构

```text
                 ┌─────────────────┐
                 │     Web UI      │
                 └────────┬────────┘
                          │
                          ↓
                 ┌─────────────────┐
                 │    AI Agent     │
                 │    MCP Client   │
                 └────────┬────────┘
                          │
                      MCP Protocol
                          │
                          ↓
          ┌────────────────────────────┐
          │ IoT Diagnosis MCP Server   │
          │                            │
          │  ┌──────────────────────┐  │
          │  │   Tool Interface     │  │
          │  └──────────┬───────────┘  │
          │             ↓              │
          │  ┌──────────────────────┐  │
          │  │ Hybrid Adaptive      │  │
          │  │ Router               │  │
          │  └──────────┬───────────┘  │
          │             ↓              │
          │  ┌──────────────────────┐  │
          │  │ Multi-Source RAG     │  │
          │  └──────────┬───────────┘  │
          │             ↓              │
          │  ┌──────────────────────┐  │
          │  │ Fusion + Reranker    │  │
          │  └──────────┬───────────┘  │
          │             ↓              │
          │  ┌──────────────────────┐  │
          │  │ Diagnosis Engine     │  │
          │  └──────────────────────┘  │
          └──────────────┬─────────────┘
                         │
       ┌─────────────────┼──────────────────┐
       ↓                 ↓                  ↓
┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│ Vector DB   │   │    MySQL     │   │ MQTT Broker │
│             │   │              │   │             │
│ Docs        │   │ Device State │   │ ESP32       │
│ Cases       │   │ Fault Record │   │ Telemetry   │
└─────────────┘   └──────────────┘   └─────────────┘
```

---

# 3. MCP Server 边界

IoT Diagnosis MCP Server 负责：

```text
设备数据访问
故障日志访问
历史案例检索
技术文档检索
Adaptive Router
Multi-Source Retrieval
Reranking
LLM故障分析
故障案例写入
```

MCP Server 不负责：

```text
Web前端渲染
用户登录UI
ESP32固件
MQTT Broker本身
LLM模型训练
向量数据库底层实现
```

---

# 4. MCP Tool 定义

MCP Server v1.0 暴露以下核心 Tools：

```text
iot_diagnosis

├── diagnose_fault
├── get_device_status
├── get_device_logs
├── search_knowledge
├── search_fault_cases
└── add_verified_fault_case
```

其中：

```text
diagnose_fault
```

为高级 Tool。

其他 Tool 为基础能力 Tool。

---

# 5. Tool：diagnose_fault

## 5.1 功能

执行完整 IoT 故障诊断。

内部自动完成：

```text
设备状态读取
     ↓
日志获取
     ↓
Hybrid Router
     ↓
Source Selection
     ↓
Multi-Source Retrieval
     ↓
Fusion
     ↓
Reranking
     ↓
LLM Diagnosis
     ↓
Structured Output
```

---

## 5.2 输入

```json
{
  "device_id": "ESP32_05",
  "query": "设备为什么一直断开MQTT连接？",
  "logs": [
    "MQTT disconnected",
    "MQTT keep alive timeout"
  ],
  "use_realtime_state": true
}
```

### JSON Schema

```json
{
  "type": "object",
  "properties": {
    "device_id": {
      "type": "string",
      "description": "设备唯一ID"
    },
    "query": {
      "type": "string",
      "description": "故障问题或诊断请求"
    },
    "logs": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "use_realtime_state": {
      "type": "boolean",
      "default": true
    }
  },
  "required": [
    "device_id",
    "query"
  ]
}
```

---

# 6. diagnose_fault 输出

```json
{
  "diagnosis_id": "DIA_20260909_001",
  "device_id": "ESP32_05",
  "fault_type": "mqtt_connection",
  "fault_name": "MQTT Keep Alive Timeout",
  "severity": "medium",
  "confidence": 0.91,

  "cause": "MQTT Keep Alive参数或Broker超时配置异常",

  "evidence": [
    "WiFi处于connected状态",
    "RSSI为-47 dBm",
    "检测到MQTT keep alive timeout"
  ],

  "solutions": [
    "检查MQTT Keep Alive参数",
    "检查Broker连接超时参数",
    "确认客户端心跳是否正常发送"
  ],

  "route": {
    "router": "llm",
    "retrieval_required": true,
    "selected_sources": [
      "fault_cases",
      "mqtt_docs"
    ]
  },

  "sources": [
    {
      "source_type": "fault_case",
      "source_id": "F105",
      "score": 0.92
    },
    {
      "source_type": "document",
      "source_id": "MQTT_DOC_03",
      "score": 0.86
    }
  ]
}
```

---

# 7. Tool：get_device_status

## 功能

查询当前设备状态。

数据主要来自：

```text
MySQL
+
Redis（可选）
+
MQTT缓存（可选）
```

输入：

```json
{
  "device_id": "ESP32_05"
}
```

输出：

```json
{
  "device_id": "ESP32_05",
  "online": true,
  "wifi_status": "connected",
  "rssi": -47,
  "mqtt_status": "disconnected",
  "temperature": 26.3,
  "uptime": 86400,
  "last_seen": "2026-09-09T22:31:42+08:00"
}
```

---

# 8. Tool：get_device_logs

## 功能

读取指定设备最近的日志。

输入：

```json
{
  "device_id": "ESP32_05",
  "limit": 50,
  "level": "ERROR"
}
```

输出：

```json
{
  "device_id": "ESP32_05",
  "logs": [
    {
      "timestamp": "2026-09-09T22:30:21+08:00",
      "level": "ERROR",
      "message": "MQTT keep alive timeout"
    }
  ]
}
```

---

# 9. Tool：search_knowledge

## 功能

统一知识检索接口。

允许指定知识源，也允许系统自动选择。

输入：

```json
{
  "query": "MQTT频繁掉线并出现keep alive timeout",
  "sources": [
    "fault_cases",
    "mqtt_docs"
  ],
  "top_k": 5
}
```

当：

```json
"sources": []
```

时，自动调用 Adaptive Router 选择数据源。

输出：

```json
{
  "results": [
    {
      "source": "fault_cases",
      "id": "F105",
      "title": "MQTT Keep Alive异常",
      "content": "...",
      "score": 0.92
    }
  ]
}
```

---

# 10. Tool：search_fault_cases

专门查询历史故障案例。

输入：

```json
{
  "query": "设备MQTT反复断开",
  "device_type": "ESP32",
  "fault_type": "mqtt",
  "top_k": 5
}
```

输出：

```json
{
  "results": [
    {
      "fault_id": "F105",
      "fault_name": "MQTT Keep Alive异常",
      "symptoms": [
        "MQTT频繁掉线"
      ],
      "cause": "Keep Alive参数设置异常",
      "solution": "调整MQTT Keep Alive参数",
      "verified": true,
      "similarity": 0.92
    }
  ]
}
```

---

# 11. Tool：add_verified_fault_case

## 功能

将已经由人工确认的故障处理结果写入知识库。

该接口禁止 LLM 在没有人工确认的情况下直接调用成功。

输入：

```json
{
  "device_id": "ESP32_05",
  "fault_type": "mqtt",
  "fault_name": "MQTT Keep Alive异常",

  "symptoms": [
    "MQTT频繁断开"
  ],

  "logs": [
    "MQTT keep alive timeout"
  ],

  "cause": "Keep Alive参数设置异常",

  "solution": "将Keep Alive由10秒调整为60秒",

  "verified": true,

  "verified_by": "operator"
}
```

---

# 12. Knowledge Update Pipeline

执行：

```text
人工确认故障
        ↓
add_verified_fault_case
        ↓
Schema Validation
        ↓
verified == true ?
      /       \
    否         是
    ↓           ↓
 Reject     保存MySQL
                ↓
          构造案例文本
                ↓
            Embedding
                ↓
           Vector DB
                ↓
          返回 fault_id
```

案例文本建议标准化为：

```text
设备类型：ESP32
故障类型：MQTT
故障名称：MQTT Keep Alive异常

故障现象：
MQTT连接频繁断开

日志：
MQTT keep alive timeout

原因：
Keep Alive配置异常

解决方案：
调整MQTT Keep Alive参数

验证状态：
已验证
```

---

# 13. Hybrid Adaptive Router

系统 Router 分为两层：

```text
Layer 1
Rule Router

Layer 2
LLM Router
```

---

# 14. Rule Router

Rule Router 优先处理确定性较高的问题。

示例：

```python
if is_realtime_query(query):
    return REALTIME_DB

if contains_explicit_fault_pattern(query):
    return RULE_ROUTE

return LLM_ROUTE
```

典型规则：

```text
RSSI是多少
温度是多少
设备是否在线
当前MQTT状态
```

直接路由：

```text
realtime_db
```

无需执行 RAG。

---

# 15. Rule Router 示例

```python
REALTIME_PATTERNS = [
    "当前RSSI",
    "现在RSSI",
    "当前温度",
    "设备在线",
    "MQTT状态"
]
```

如果输入：

```text
ESP32_05当前RSSI是多少？
```

返回：

```json
{
  "router": "rule",
  "need_retrieval": false,
  "sources": [
    "realtime_db"
  ]
}
```

---

# 16. LLM Router

复杂问题交给 LLM Router。

输入：

```text
用户问题
+
设备状态
+
设备日志
```

要求输出严格 JSON：

```json
{
  "fault_type": "mqtt",
  "need_retrieval": true,
  "sources": [
    "fault_cases",
    "mqtt_docs"
  ],
  "top_k": 5
}
```

---

# 17. Router Output Schema

```json
{
  "type": "object",
  "properties": {
    "fault_type": {
      "type": "string"
    },

    "need_retrieval": {
      "type": "boolean"
    },

    "sources": {
      "type": "array",
      "items": {
        "enum": [
          "fault_cases",
          "mqtt_docs",
          "wifi_docs",
          "sensor_docs",
          "device_docs",
          "realtime_db"
        ]
      }
    },

    "top_k": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20
    }
  }
}
```

---

# 18. Multi-Source RAG

系统支持以下 Source：

| Source | 内容 |
|---|---|
| fault_cases | 历史维修案例 |
| mqtt_docs | MQTT技术资料 |
| wifi_docs | WiFi技术资料 |
| device_docs | ESP32技术资料 |
| sensor_docs | 传感器技术资料 |
| realtime_db | 当前设备状态 |

不同 Source 可以拥有独立 Collection。

例如：

```text
vector_db

├── fault_cases
├── mqtt_docs
├── wifi_docs
├── esp32_docs
└── sensor_docs
```

---

# 19. Retrieval Pipeline

```text
Query
 ↓
Adaptive Router
 ↓
Source Selection
 ↓
Query Rewrite
 ↓
┌──────────┬───────────┐
↓          ↓           ↓
Cases     Docs       Realtime
↓          ↓           ↓
Vector    Vector      MySQL
Search    Search
↓          ↓
└──────┬───┘
       ↓
Result Fusion
       ↓
Deduplication
       ↓
Reranker
       ↓
Top Context
```

---

# 20. Query Rewrite

原始 Query：

```text
ESP32为什么一直掉线？
```

结合设备状态：

```text
WiFi=connected
RSSI=-47
MQTT=disconnected
log=keep alive timeout
```

Rewrite：

```text
ESP32 MQTT连接频繁断开，
WiFi信号正常，
出现MQTT keep alive timeout日志。
```

然后执行向量检索。

这样比只检索：

```text
为什么一直掉线
```

具有更高检索精度。

---

# 21. Retrieval

每个数据源独立检索。

例如：

```python
case_results = search(
    collection="fault_cases",
    query=query,
    top_k=5
)

doc_results = search(
    collection="mqtt_docs",
    query=query,
    top_k=5
)
```

产生：

```text
Cases Top5
+
Docs Top5
=
10 candidates
```

---

# 22. Result Fusion

统一结果格式：

```json
{
  "id": "F105",
  "source": "fault_cases",
  "content": "...",
  "retrieval_score": 0.91
}
```

处理：

```text
Normalize
 ↓
Merge
 ↓
Deduplicate
 ↓
Rerank
```

---

# 23. Reranker

输入：

```text
Query
+
Candidate Documents
```

例如：

```text
10 candidates
 ↓
Reranker
 ↓
Top 4
```

最终只把 Top 4 Context 传递给 Diagnosis LLM。

目标：

```text
减少Token
+
减少无关Context
+
提高诊断准确率
```

---

# 24. Diagnosis Engine

Diagnosis LLM 输入包含：

```text
System Prompt
+
Device State
+
Device Logs
+
Retrieved Context
+
User Query
```

---

# 25. Diagnosis Prompt Contract

System Prompt 核心要求：

```text
你是IoT故障诊断系统。

只能根据：
1. 当前设备状态
2. 日志
3. 检索到的技术资料
4. 已验证历史故障案例

进行分析。

不得虚构不存在的设备数据。

如果证据不足，应明确表示无法确定。

输出必须符合指定JSON Schema。
```

---

# 26. Diagnosis Output Schema

```json
{
  "fault_type": "mqtt_connection",

  "fault_name": "MQTT Keep Alive Timeout",

  "confidence": 0.91,

  "severity": "medium",

  "cause": "MQTT Keep Alive配置异常",

  "evidence": [
    "WiFi连接正常",
    "RSSI=-47",
    "keep alive timeout"
  ],

  "solutions": [
    "检查MQTT Keep Alive",
    "检查Broker Timeout"
  ]
}
```

---

# 27. Confidence

Confidence 不应完全使用 LLM 自己输出的概率。

推荐：

```text
confidence =
0.35 × retrieval_score
+
0.25 × evidence_score
+
0.20 × case_similarity
+
0.20 × llm_score
```

v1.0 也允许简化为规则型评分。

例如：

```text
>= 0.85    HIGH

0.65-0.85  MEDIUM

<0.65      LOW
```

低置信度时返回：

```json
{
  "requires_manual_inspection": true
}
```

---

# 28. 数据库设计

## device

```text
device
────────────────────
id
device_id
device_type
name
firmware_version
created_at
```

---

# 29. device_status

```text
device_status
────────────────────
id
device_id
online
wifi_status
rssi
mqtt_status
temperature
uptime
timestamp
```

---

# 30. device_log

```text
device_log
────────────────────
id
device_id
level
module
message
timestamp
```

---

# 31. fault_case

```text
fault_case
────────────────────
id
fault_id
device_type
fault_type
fault_name
symptom
logs
cause
solution
verified
verified_by
source
vector_id
created_at
updated_at
```

---

# 32. diagnosis_record

```text
diagnosis_record
────────────────────
id
diagnosis_id
device_id
query
fault_type
fault_name
cause
solution
confidence
router_type
selected_sources
retrieved_documents
created_at
```

该表非常重要。

后续实验可以统计：

```text
Router命中情况
RAG检索结果
诊断准确率
响应时间
Token使用量
```

---

# 33. MQTT Topic Design

建议：

```text
iot/{device_id}/status

iot/{device_id}/telemetry

iot/{device_id}/logs

iot/{device_id}/fault

iot/{device_id}/heartbeat
```

例如：

```text
iot/ESP32_05/status
```

Payload：

```json
{
  "wifi": "connected",
  "rssi": -47,
  "mqtt": "connected",
  "uptime": 92342
}
```

---

# 34. MCP Server 代码模块结构

推荐项目结构：

```text
iot-diagnosis-mcp/

├── app/
│
│   ├── main.py
│
│   ├── mcp/
│   │   ├── server.py
│   │   └── tools/
│   │       ├── diagnose.py
│   │       ├── device.py
│   │       ├── retrieval.py
│   │       └── knowledge.py
│
│   ├── router/
│   │   ├── hybrid_router.py
│   │   ├── rule_router.py
│   │   └── llm_router.py
│
│   ├── rag/
│   │   ├── pipeline.py
│   │   ├── retriever.py
│   │   ├── query_rewriter.py
│   │   ├── fusion.py
│   │   └── reranker.py
│
│   ├── diagnosis/
│   │   ├── engine.py
│   │   ├── prompt.py
│   │   └── confidence.py
│
│   ├── knowledge/
│   │   ├── case_service.py
│   │   ├── document_service.py
│   │   └── embedding.py
│
│   ├── device/
│   │   ├── service.py
│   │   └── mqtt.py
│
│   ├── db/
│   │   ├── mysql.py
│   │   ├── vector.py
│   │   └── models.py
│
│   ├── schemas/
│   │   ├── device.py
│   │   ├── diagnosis.py
│   │   ├── retrieval.py
│   │   └── fault_case.py
│
│   └── config.py
│
├── tests/
│
├── data/
│   ├── documents/
│   └── fault_cases/
│
├── scripts/
│   ├── ingest_documents.py
│   └── build_vector_db.py
│
├── requirements.txt
├── .env
└── README.md
```

---

# 35. 核心调用逻辑

```python
async def diagnose_fault(request):

    state = await device_service.get_status(
        request.device_id
    )

    logs = request.logs

    if not logs:
        logs = await device_service.get_logs(
            request.device_id
        )

    route = await hybrid_router.route(
        query=request.query,
        state=state,
        logs=logs
    )

    if not route.need_retrieval:
        return build_direct_response(
            state=state,
            route=route
        )

    query = query_rewriter.rewrite(
        request.query,
        state,
        logs
    )

    candidates = await retriever.retrieve(
        query=query,
        sources=route.sources
    )

    context = reranker.rerank(
        query,
        candidates
    )

    diagnosis = await diagnosis_engine.run(
        query=request.query,
        state=state,
        logs=logs,
        context=context
    )

    await diagnosis_repository.save(
        diagnosis
    )

    return diagnosis
```

---

# 36. Hybrid Router 逻辑

```python
async def route(query, state, logs):

    rule_result = rule_router.match(
        query=query,
        state=state,
        logs=logs
    )

    if rule_result.confident:
        return rule_result

    return await llm_router.route(
        query=query,
        state=state,
        logs=logs
    )
```

---

# 37. Knowledge Ingestion Pipeline

技术文档：

```text
PDF / Markdown / TXT
        ↓
Parser
        ↓
Cleaning
        ↓
Chunking
        ↓
Metadata
        ↓
Embedding
        ↓
Vector DB
```

Chunk Metadata：

```json
{
  "source": "mqtt_docs",
  "document": "MQTT_v5_spec",
  "section": "Keep Alive",
  "device_type": "ESP32"
}
```

---

# 38. Historical Case Pipeline

```text
Verified Fault
      ↓
Canonical Case
      ↓
MySQL
      ↓
Case Text Builder
      ↓
Embedding
      ↓
fault_cases Collection
```

---

# 39. 安全要求

所有具有写操作的 Tool 必须进行额外检查。

特别是：

```text
add_verified_fault_case
```

必须满足：

```text
verified == true
AND
verified_by != null
```

否则：

```text
CASE_NOT_VERIFIED
```

不得加入向量数据库。

---

# 40. Device Control

v1.0 默认禁止以下操作：

```text
restart_device
update_firmware
change_wifi
change_mqtt_config
```

因为这些属于设备控制行为，而不是诊断行为。

如果未来加入，应单独设计：

```text
IoT Control MCP
```

并增加权限与人工确认机制。

---

# 41. Error Code

统一错误：

```text
DEVICE_NOT_FOUND

DEVICE_OFFLINE

DATABASE_ERROR

VECTOR_DB_ERROR

RETRIEVAL_FAILED

LLM_ERROR

ROUTER_FAILED

INVALID_REQUEST

CASE_NOT_VERIFIED

INSUFFICIENT_EVIDENCE
```

输出：

```json
{
  "success": false,

  "error": {
    "code": "DEVICE_NOT_FOUND",
    "message": "Device ESP32_99 does not exist"
  }
}
```

---

# 42. Observability

每次诊断记录：

```text
request_id
diagnosis_id
router
selected_sources
retrieval_count
rerank_count
retrieval_latency
llm_latency
total_latency
input_tokens
output_tokens
error
```

推荐接入：

```text
Python logging
+
OpenTelemetry
```

---

# 43. RAG Evaluation

至少评估：

```text
Recall@K

Precision@K

MRR

Hit Rate

Diagnosis Accuracy

Average Latency

Token Usage
```

---

# 44. Router Evaluation

构造 Router Test Set：

```text
MQTT故障      50条
WiFi故障      50条
Sensor故障    50条
实时查询      50条
复杂组合故障   50条
```

比较：

```text
Rule Router

Embedding Router

LLM Router

Hybrid Router
```

主要指标：

```text
Routing Accuracy
Source Selection Accuracy
Average Latency
Token Cost
```

---

# 45. RAG 消融实验

实验组：

```text
A
LLM Only

B
Single-Source RAG

C
Multi-Source RAG

D
Adaptive Multi-Source RAG

E
Hybrid Adaptive Multi-Source RAG
```

评价：

```text
诊断准确率
检索Recall
平均延迟
Token消耗
错误知识引用率
```

---

# 46. 故障实验数据

建议至少覆盖：

```text
WiFi弱信号

WiFi断开

MQTT Broker不可达

MQTT认证错误

MQTT Keep Alive超时

Sensor读取失败

Sensor数据异常

设备重启

内存不足

网络延迟
```

每种故障建议准备多个表达方式和日志组合。

---

# 47. 完整业务流程

```text
                 ESP32
                    │
                    ↓
                  MQTT
                    │
                    ↓
              Device Service
                    │
                    ↓
              MySQL / Logs
                    │
                    ↓
                  Agent
                    │
                    ↓
            diagnose_fault()
                    │
                    ↓
            IoT Diagnosis MCP
                    │
                    ↓
              Hybrid Router
             /             \
          Rule             LLM
             \             /
                    ↓
            Source Selection
                    ↓
       ┌────────────┼────────────┐
       ↓            ↓            ↓
    Cases          Docs       Realtime
       ↓            ↓            ↓
       └────────────┼────────────┘
                    ↓
                 Fusion
                    ↓
                Reranker
                    ↓
              Diagnosis LLM
                    ↓
           Structured Result
                    ↓
             Web展示诊断
                    ↓
              人工实际处理
                    ↓
              是否解决？
                    ↓
                  YES
                    ↓
       add_verified_fault_case
                    ↓
                 MySQL
                    +
                Vector DB
                    ↓
             Knowledge Update
```

---

# 48. MCP 对外能力模型

最终 Agent 看到的并不是：

```text
MySQL
Chroma
MQTT
Embedding
Reranker
```

而是：

```text
IoT Diagnosis MCP

get_device_status()

get_device_logs()

search_knowledge()

search_fault_cases()

diagnose_fault()

add_verified_fault_case()
```

底层实现完全由 MCP Server 隐藏。

---

# 49. 非功能要求

## Performance

普通实时查询：

```text
目标 < 500 ms
```

RAG Query：

```text
目标 < 3 s
```

完整 LLM Diagnosis：

```text
目标 < 8 s
```

实际性能根据模型部署方式调整。

---

## Reliability

数据库失败不得导致 MCP Server 崩溃。

所有外部组件：

```text
LLM
Vector DB
MySQL
MQTT
```

必须拥有异常捕获机制。

---

## Extensibility

新增知识源时：

```text
implements Retriever
```

即可加入系统。

例如以后：

```text
GitHub Issues

厂家FAQ

设备维修手册

Internet Search

Prometheus Metrics
```

均可扩展为新的 Retrieval Source。

---

# 50. v1.0 验收标准

系统满足以下条件即认为 IoT Diagnosis MCP v1.0 完成。

### MCP

MCP Client 可以成功发现并调用所有核心 Tools。

### Device

可以查询 ESP32：

```text
状态
RSSI
MQTT连接状态
最近日志
```

### RAG

可以同时检索：

```text
技术文档
+
历史故障案例
```

### Adaptive Retrieval

简单 Query 使用 Rule Router。

复杂 Query 使用 LLM Router。

### Multi-Source

Router 能动态决定：

```text
检索哪些Source
```

而不是每次搜索全部知识库。

### Reranker

多个知识源结果能够统一排序。

### Diagnosis

能够返回：

```text
故障类型
故障原因
证据
解决方案
置信度
引用来源
```

### Knowledge Update

只有：

```text
verified = true
```

的故障案例能够进入：

```text
MySQL
+
Vector DB
```

### Traceability

每一次诊断能够查询：

```text
使用了哪个Router

搜索了哪些Source

检索到了哪些文档

最终依据哪些Context进行了判断
```

---

# 51. 系统最终技术定义

本系统定义为：

**IoT Diagnosis MCP Server**

内部核心算法：

**Hybrid Adaptive Multi-Source RAG**

整体技术链：

```text
ESP32
   ↓
MQTT
   ↓
FastAPI
   ↓
Agent
   ↓
MCP Client
   ↓
IoT Diagnosis MCP Server
   ↓
Hybrid Adaptive Router
   ↓
Multi-Source Retrieval
   ↓
Fusion
   ↓
Reranker
   ↓
LLM Diagnosis
   ↓
Human Verification
   ↓
Dynamic Knowledge Base
```

系统形成：

```text
数据采集
   ↓
故障检测
   ↓
自适应知识检索
   ↓
LLM智能诊断
   ↓
人工验证
   ↓
故障知识积累
   ↓
下一次诊断
```

的完整闭环。

---

# 52. 推荐开发顺序

Phase 1：

```text
ESP32
→ MQTT
→ MySQL
→ FastAPI
```

Phase 2：

```text
文档解析
→ Embedding
→ Vector DB
→ 基础RAG
```

Phase 3：

```text
历史故障案例库
→ Multi-Source RAG
→ Reranker
```

Phase 4：

```text
Rule Router
→ LLM Router
→ Hybrid Adaptive Retrieval
```

Phase 5：

```text
diagnose_fault
→ get_device_status
→ search_knowledge
→ add_verified_fault_case
```

将上述能力封装为：

```text
IoT Diagnosis MCP Server
```

Phase 6：

```text
Agent
→ MCP Client
→ IoT Diagnosis MCP
```

Phase 7：

```text
故障注入
→ 数据集构建
→ 对比实验
→ 消融实验
→ 论文结果
```

---

# 53. v2 可选扩展

v1 完成后可以考虑：

```text
Embedding Router

Hybrid Search
BM25 + Vector

Query Decomposition

Corrective RAG

Self-RAG

Graph RAG

Multi-Agent Diagnosis

Anomaly Detection

Time-Series Analysis

Prometheus Metrics

Remote Device Control MCP
```

但以上均不属于 v1 必需功能。
