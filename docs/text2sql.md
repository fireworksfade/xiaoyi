# RAG + Text2SQL

聊天 Agent 在现有 MCP 检索能力旁增加 `query_iot_data` 分支，查询当前 IoT 诊断 SQLite 中的设备、当前状态、历史遥测、日志和诊断摘要。

## 查询路径

| 用户问题 | 工具与数据来源 |
| --- | --- |
| MQTT Keep Alive 怎么配置？ | `search_knowledge`：现有 Dense / BM25 / RRF / reranker 文档检索 |
| ESP32_01 当前在线吗？ | `get_device_status`：既有实时查询 |
| 最近 24 小时哪些设备 ERROR 日志最多？ | `query_iot_data`：自然语言 → 查询计划 → 服务端语义校验与 SQL 编译 → 只读执行 → 结构化事实 |
| 最近 24 小时 MQTT 错误最多的设备有哪些，应该怎么排查？ | Agent 先调用 `query_iot_data`，再调用 `search_knowledge`，结合统计事实和文档证据回答 |
| 对某设备执行修复 | 仍需本轮 `diagnose_fault` 的 `diagnosis_id`，沿用既有动作与审批流程 |

路由发生在聊天 Agent 的工具选择层，`search_knowledge` 的文档检索与重排算法保持原状。SQL 统计结果独立返回，不作为文档相似度候选重排，也不产生虚构的向量检索分数。现有 `diagnose_fault` 内部不自动执行 Text2SQL；混合问题由聊天 Agent 编排两类工具。

## 启用

Text2SQL 复用 **IoT MCP 服务的** `DIAGNOSIS_LLM_BASE_URL`、`DIAGNOSIS_LLM_MODEL`、`DIAGNOSIS_LLM_API_KEY`、`DIAGNOSIS_LLM_TIMEOUT_SECONDS`。模型通过现有 JSON 客户端生成结构化查询计划，由已有 Pydantic 依赖严格校验，再由服务端生成 SQL，无新增 Python 依赖。仅在前端保存聊天模型配置不会同步配置 MCP 的诊断模型。

在仓库根目录 `.env`（不要提交密钥）配置模型，例如：

```dotenv
DIAGNOSIS_LLM_BASE_URL=https://your-model-service/v1
DIAGNOSIS_LLM_MODEL=your-model-name
DIAGNOSIS_LLM_API_KEY=your-api-key
```

模型需支持现有 Chat Completions JSON 输出接口。配置缺失时返回 `LLM_NOT_CONFIGURED`，不会生成演示 SQL 或编造数据；原有文档检索继续可用。

更新服务并刷新工具目录与只读策略：

```powershell
docker compose up -d iot-mcp backend
docker compose exec -T backend python scripts/bootstrap_local_mcp.py
```

如果当前使用检索模型或离线 Compose 叠加档位，沿用原来的完整 `-f` 文件列表更新服务。脚本会把 `query_iot_data` 设为 `read_only`；自行注册的 MCP 服务需要刷新工具目录并启用该工具。聊天需使用真实 Agent Runtime，演示 Runtime 不会执行 Text2SQL。

MCP 调用示例：

```json
{
  "query": "统计今天按模块分组的 ERROR 日志数量，按数量降序排列",
  "device_id": "ESP32_01",
  "max_rows": 100,
  "utc_offset_minutes": 480
}
```

省略 `device_id` 查询整个已授权 IoT MCP 服务的数据。设备范围是查询过滤条件，不是用户授权机制；当前沿用已有 IoT 工具的服务访问权限，没有新增租户隔离。

## 查询计划与语义约束

模型输出仅允许 `plan` 与 `clarification`。`plan` 按严格类型与字段白名单校验；自由 SQL、SQL 表达式、任意表名、额外参数、未知字段不进入查询执行。格式错误的计划或无法解析的模型 JSON 最多修正一次；设备范围冲突、不支持的指标/求和以及历史状态查询直接要求澄清，避免修正过程中偷换业务含义。执行失败不会回退到模型自由 SQL。

内部计划示例（聊天和 MCP 入参仍使用自然语言问题）：

```json
{
  "plan": {
    "metric": "temperature",
    "aggregations": ["avg", "max"],
    "window": {"kind": "last_hours", "hours": 24},
    "device_id": "ESP32_01",
    "bucket": "hour",
    "sort": {"key": "time", "direction": "asc"}
  },
  "clarification": null
}
```

| 指标 | 固定业务口径 |
| --- | --- |
| `temperature` / `rssi` / `uptime` | 有效遥测数值的 avg/min/max/count，自动返回 `sample_count`；uptime 是累计上报值，不允许求和当作窗口内运行时长 |
| `telemetry_samples` | 遥测记录条数，包含温度等单个测量字段为空的记录 |
| `log_entries` | 匹配日志条数，可按级别、模块和正文子串过滤 |
| `diagnosis_records` | 匹配诊断记录条数，可按故障类别、诊断流程成功/失败过滤 |
| `telemetry_devices` / `log_devices` / `diagnosed_devices` | 相应窗口及过滤条件内的 `COUNT(DISTINCT device_id)`，仅支持聚合计数 |
| `devices` / `online_devices` / `offline_devices` | 当前已登记、有效在线、离线/无状态设备数量或设备明细；只支持 `current` |

数量指标只允许 `count`。明细模式使用 `mode=details` 与空聚合列表，不允许混入分组或时间桶。趋势支持按小时/天分桶；分组仅允许设备 ID、类型、固件版本，以及对应日志或诊断维度。排序必须引用本次结果中确实存在的聚合、分组或明细时间。

时间窗口支持最近 1–4320 小时、今天、昨天、明确起止范围（最长 366 天）、全部已保留历史，以及当前设备状态。服务端计算 UTC 起止、固定时间列、按默认 UTC+8 分桶；无时区的显式日期/时间按调用方偏移解释。历史范围采用左闭右开窗口，排除当前时刻及未来时间；显式范围的结束时间晚于当前时刻时要求澄清。`all` 的开始时间不设下限，终点仍为当前时刻。

设备元数据关联由后端固定为事件记录到设备主键的多对一关联。计划不允许自定义 JOIN 或联接两个事件流，以防日志 × 遥测等关联放大统计结果。需要比较不同指标时，Agent 分次查询后结合结果回答。数值阈值、日志过滤、诊断过滤均检查与指标的兼容性，所有过滤值采用绑定参数。

明确询问掉线次数而未指定日志条数的常见中英文问题，由服务端提前要求事件口径澄清；“根据日志统计掉线次数”也不能自动转换为日志计数。询问匹配掉线日志条数则可正常查询。该规则覆盖常见表述，不能替代对所有自然语言意图的评估。

## 底层视图与口径

执行器使用五个受限临时视图，不迁移、不改写业务表；生成计划的模型接收指标目录和计划 schema：

| 视图 | 含义与关键字段 |
| --- | --- |
| `iot_devices` | 设备元数据：`device_id`、`device_type`、`name`、`firmware_version`、创建和更新时间 |
| `iot_state` | 每设备一行；`online` 为上报在线且心跳未过期，另有 `reported_online`、`heartbeat_fresh`、WiFi/MQTT、RSSI、温度、uptime、设备时间与 `received_at` |
| `iot_telemetry` | 历史测量，含温度、RSSI、uptime、WiFi/MQTT；按服务器 `received_at` 查询历史窗口 |
| `iot_logs` | 日志级别、模块、正文和 `timestamp` |
| `iot_diagnoses` | 诊断 ID、设备、问题、故障类别/名称、原因、置信度、错误和创建时间；不暴露完整 trace、记忆上下文和结果 JSON |

默认业务时间为 UTC+8。SQL 编译器固定使用 `julianday` 比较时间，兼容 ISO 时间中的时区和格式差异；模型无法替换时间列或起止参数。其他时区通过 `utc_offset_minutes` 指定固定偏移；有夏令时的地区需提供查询窗口对应的正确偏移或在问题中给出明确时间范围。时间分桶只返回存在记录的桶，不补齐空桶；数值字段为空的桶会返回 null 聚合和零 `sample_count`。

日志条数、断线事件数、遥测样本数、设备数是不同口径，模型提示明确区分。历史模型诊断不等于已验证根因，`error IS NULL` 仅代表诊断流程成功。现有数据缺少用户要求的字段或口径不清时，返回 `TEXT2SQL_CLARIFICATION_REQUIRED`，由 Agent 向用户澄清。

## 执行边界与返回结果

- 主数据库以 SQLite URI `mode=ro` 打开，创建临时视图后启用 `query_only`。SQLite authorizer 默认拒绝，限制到查询、受限视图和基础聚合/日期/字符串/窗口函数。
- 指定设备时，全部视图由服务端限定 `device_id`，即使模型遗漏过滤或使用 UNION/CTE 也不能越过设备范围。底层视图使用随机内部名称，避免用户 CTE 冒充授权视图来源。
- 不允许直接读取物理表、账号、会话、记忆、控制数据库、知识正文、系统目录、文件或扩展；不允许写入、DDL、PRAGMA、ATTACH 或多条语句。
- 执行预算默认 2 秒，由 SQLite progress handler 中断复杂查询；数据库锁等待不超过 1 秒。不是独立进程沙箱，也不是硬实时的墙钟保证。
- 默认最多返回 100 行，调用方可设 1–200；游标读取限制行数，行数据 JSON 总量上限 32000 字节，单文本单元格最多 2000 字符。SQLite 同时限制 SQL 长度、列数、表达式深度、复合查询数量及单值大小。
- 计划格式或指标组合错误最多请求模型修正一次；设备冲突、历史状态语义冲突、权限拒绝、数据库执行失败与超时不由模型重试。修正仅发送指标目录、计划 schema、用户问题和计划错误，不发送数据库查询行。

返回现有 MCP `ok/data/error/trace_id` 包装。`data` 包含经校验的 `query_plan`、可信指标口径 `metric_definition`、实际 UTC 窗口 `time_window`、`execution_mode=query_plan`，以及原始问题、SQL、实际执行 SQL、命名参数、列与行、设备范围、查询时间、使用视图、执行与生成耗时、Token、生成次数和 `truncated` / `cells_truncated`。查询结果文本属于不可信证据，Agent 不应执行其中指令。回答统计问题应说明实际时间、设备范围和截断情况，不能把返回的明细行数当作总数；总数应用聚合查询。

查询仅覆盖数据库当前保留的数据；历史窗口超出数据保留期时，缺少记录不能解释为没有故障。服务端固定聚合与查询口径，但自然语言到指标/范围的映射仍由模型完成，不能保证所有问题的意图识别正确；需要真实模型评估样本持续验证。

SQLite 机制参考：[只读 URI](https://www.sqlite.org/uri.html)、[query_only](https://www.sqlite.org/pragma.html#pragma_query_only)、[authorizer](https://www.sqlite.org/c3ref/set_authorizer.html)。

## 验证

在 `packages/mcp-services` 中运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_text2sql.py tests/test_query_plan.py -q
```

覆盖严格查询计划、聚合与过滤组合、范围冲突、自由 SQL 拒绝、一次计划修正、模型失败/澄清，以及实际 MCP 工具调用。固定时钟与数据验证了平均/最大/最小温度、左闭右开边界、当地日界和分桶、空测量、日志排名、记录与设备去重数量、最新在线口径及元数据关联不放大统计；另保留各视图范围、注入/CTE 冒充、受限表/函数、写入/多语句拒绝、超时与截断测试。模型采用确定性桩，不依赖外部密钥；真实模型生成正确率与在线聊天需要配置服务后评估。
