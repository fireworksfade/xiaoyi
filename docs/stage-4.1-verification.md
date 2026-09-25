# Stage 4.1 验证报告：OpenTelemetry 可观测性

## 完成时间
2026-09-26

## 实现内容

### 1. 基础设施
- ✅ Jaeger all-in-one 容器 (v1.60)
- ✅ OTLP HTTP exporter (端口 4318)
- ✅ Jaeger UI (端口 16686)

### 2. 后端集成
文件：`packages/backend/app/telemetry.py`

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def configure_telemetry(app, service_name: str, otlp_endpoint: str):
    """配置 OpenTelemetry 追踪"""
    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    
    exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
```

集成到 `packages/backend/app/main.py`:
- 自动追踪所有 HTTP 请求
- 服务名称: `xiaoyi-backend`
- 端点: `http://jaeger:4318`

### 3. MCP 服务集成
文件：`packages/mcp-services/common/telemetry.py`

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def configure_telemetry(service_name: str, otlp_endpoint: str):
    """配置 OpenTelemetry 追踪"""
    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)
    
    exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
```

集成到 `packages/mcp-services/iot_mcp/server.py`:
- 追踪 MCP 工具调用
- 服务名称: `xiaoyi-iot-mcp`
- 端点: `http://jaeger:4318`

### 4. 验证工具

#### 快速验证脚本
文件：`scripts/test-telemetry.sh`
```bash
#!/bin/bash
# 检查服务状态、Jaeger UI、telemetry 初始化
bash scripts/test-telemetry.sh
```

#### 完整验证脚本
文件：`scripts/verify_telemetry.py`
```python
# 测试 MCP 工具调用，生成追踪数据
# 查询 Jaeger API，验证追踪链路
python scripts/verify_telemetry.py
```

## 验证结果

### 服务状态
```
✅ backend (healthy) - 端口 8000
✅ iot-mcp (healthy) - 端口 9000
✅ jaeger (running) - 端口 16686, 4318
✅ mqtt (running) - 端口 1883
✅ qdrant (healthy) - 端口 6333
```

### Telemetry 初始化
```
✅ Backend: OpenTelemetry configured: service=xiaoyi-backend, endpoint=http://jaeger:4318
✅ MCP: OpenTelemetry configured: service=xiaoyi-iot-mcp, endpoint=http://jaeger:4318
```

### Jaeger 服务发现
```
✅ xiaoyi-backend - 找到 5 条追踪
✅ xiaoyi-iot-mcp - 找到 10 条追踪
```

### 追踪操作类型
MCP 服务追踪的操作：
- `initialize` - MCP 会话初始化
- `notifications/initialized` - 初始化通知
- `tools/call list_devices` - 列出设备
- `tools/call get_device_status` - 获取设备状态（含 MQTT）
- `tools/call diagnose_fault` - 故障诊断（含 RAG）
- `tools/list` - 列出可用工具

### 测试用例
1. ✅ MCP 客户端连接
2. ✅ 工具调用追踪（list_devices, get_device_status, diagnose_fault）
3. ✅ 追踪数据上报到 Jaeger
4. ✅ Jaeger UI 可访问

## 使用指南

### 查看追踪
1. 打开 Jaeger UI: http://localhost:16686
2. 选择服务：`xiaoyi-backend` 或 `xiaoyi-iot-mcp`
3. 点击 "Find Traces" 查看最近的追踪
4. 点击追踪查看详细的 span 时间线

### 快速测试
```bash
# 基础验证
bash scripts/test-telemetry.sh

# 完整验证（含诊断流程）
python scripts/verify_telemetry.py
```

### 手动触发追踪
```python
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("http://localhost:9000/mcp") as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("diagnose_fault", {
            "device_id": "AIR_CONDITIONER_001",
            "query": "制冷效果差"
        })
```

## 下一步

### Stage 4.2: 增强错误处理
- [ ] 定义 MCP 错误分类
- [ ] 实现自动重试装饰器
- [ ] 添加错误聚合端点

### 追踪增强（可选）
- [ ] 添加自定义 span attributes（设备 ID、查询内容）
- [ ] 追踪 RAG 检索性能（检索时间、命中数量）
- [ ] 追踪 MQTT 消息延迟（发送 → 接收）
- [ ] 添加业务指标（诊断成功率、设备在线率）

## 参考资料
- Jaeger UI: http://localhost:16686
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- OTLP Specification: https://opentelemetry.io/docs/specs/otlp/
