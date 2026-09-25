"""Unified IoT MCP Server - combines Diagnosis and Control services.

This server hosts both diagnosis and control tools on a single port,
simplifying deployment from 2 containers to 1.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from common.results import failure, success
from common.telemetry import setup_telemetry

# Diagnosis imports
from iot_diagnosis.auth import auth_configuration as diagnosis_auth_configuration
from iot_diagnosis.diagnosis import diagnose
from iot_diagnosis.embeddings import retrieval_model_status
from iot_diagnosis.ingestion import ingest_text
from iot_diagnosis.mqtt import MQTTIngestor
from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retention import RetentionService
from iot_diagnosis.retrieval import search_fault_cases as retrieve_fault_cases
from iot_diagnosis.retrieval import search_knowledge as retrieve_knowledge

# Control imports
from iot_control import actions, remediation_events
from iot_control.auth import auth_configuration as control_auth_configuration
from iot_control.mqtt import ControlMQTT
from iot_control.repository import ControlRepository

logger = logging.getLogger("xiaoyi.iot_mcp.server")

# Initialize repositories
diagnosis_repository = DiagnosisRepository(
    os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    int(os.getenv("DIAGNOSIS_OFFLINE_AFTER_SECONDS", "120")),
)

control_repository = ControlRepository(
    os.getenv("CONTROL_DATABASE_PATH", "data/iot_control.db"),
    command_timeout_seconds=int(os.getenv("CONTROL_COMMAND_TIMEOUT_SECONDS", "30")),
    verify_window_seconds=int(os.getenv("CONTROL_VERIFY_WINDOW_SECONDS", "60")),
    proposal_ttl_minutes=int(os.getenv("CONTROL_PROPOSAL_TTL_MINUTES", "30")),
)

# Use diagnosis auth as primary (control can share the same token)
auth_settings, token_verifier = diagnosis_auth_configuration()


@asynccontextmanager
async def service_lifespan(_server):
    """Lifecycle manager for both diagnosis and control services."""
    diagnosis_ingestor = None
    diagnosis_sync_task = None
    diagnosis_retention_task = None
    control_mqtt = None
    control_watchdog = None

    # Start diagnosis MQTT ingestor
    if os.getenv("MQTT_ENABLED", "false").lower() == "true":
        diagnosis_ingestor = MQTTIngestor(diagnosis_repository)
        diagnosis_ingestor.start()
        logger.info("Diagnosis MQTT ingestor started")

    # Start diagnosis external sync
    sync_interval = max(0.0, float(os.getenv("DIAGNOSIS_SYNC_RETRY_SECONDS", "30")))
    if sync_interval:
        async def retry_external_writes() -> None:
            while True:
                await asyncio.sleep(sync_interval)
                await asyncio.to_thread(diagnosis_repository.retry_external_sync)

        diagnosis_sync_task = asyncio.create_task(retry_external_writes())
        logger.info(f"Diagnosis sync task started (interval: {sync_interval}s)")

    # MARKER_RETENTION
    retention_interval_hours = max(0.0, float(os.getenv("DIAGNOSIS_RETENTION_INTERVAL_HOURS", "24")))
    if retention_interval_hours:
        retention = RetentionService(diagnosis_repository)

        async def background_retention() -> None:
            while True:
                await asyncio.sleep(retention_interval_hours * 3600)
                try:
                    await asyncio.to_thread(retention.execute)
                except Exception:
                    logger.exception("Retention execution failed")

        diagnosis_retention_task = asyncio.create_task(background_retention())
        logger.info(f"Diagnosis retention task started (interval: {retention_interval_hours}h)")

    # Start control MQTT and timeout processor
    if os.getenv("MQTT_ENABLED", "false").lower() == "true":
        control_mqtt = ControlMQTT(control_repository)
        control_mqtt.start()
        logger.info("Control MQTT started")

        async def background_worker() -> None:
            while True:
                await asyncio.sleep(2)
                try:
                    await asyncio.to_thread(control_repository.process_timeouts)
                except Exception:
                    logger.exception("Timeout processing failed")

        control_watchdog = asyncio.create_task(background_worker())
        logger.info("Control timeout processor started")

    yield

    # Cleanup
    if diagnosis_sync_task:
        diagnosis_sync_task.cancel()
    if diagnosis_retention_task:
        diagnosis_retention_task.cancel()
    if control_watchdog:
        control_watchdog.cancel()
    if diagnosis_ingestor:
        diagnosis_ingestor.stop()
    if control_mqtt:
        control_mqtt.stop()

    logger.info("Unified IoT MCP server shutdown complete")


mcp = MCPServer(
    "unified-iot-mcp",
    title="Unified IoT MCP Server",
    description="Combined diagnosis and control services for ESP32 IoT devices",
    version="2.0.0",
    lifespan=service_lifespan,
)



# ============================================================================
# DIAGNOSIS TOOLS
# ============================================================================


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def diagnose_fault(
    device_id: Annotated[str, Field(min_length=1, max_length=120)],
    query: Annotated[str, Field(min_length=1, max_length=2000)],
    logs: Annotated[list[str] | None, Field(max_length=100)] = None,
    use_realtime_state: bool = True,
) -> dict[str, Any]:
    """执行设备状态、日志、自适应多源检索、重排和结构化故障诊断。"""
    try:
        return success(diagnose(diagnosis_repository, device_id, query, logs, use_realtime_state))
    except LookupError:
        message = f"Device {device_id} does not exist"
        return failure("DEVICE_NOT_FOUND", message)
    except Exception:
        message = "诊断流程执行失败"
        logger.exception(message)
        return failure("LLM_ERROR", message, retryable=True)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def get_diagnosis_trace(
    diagnosis_id: Annotated[str, Field(min_length=1, max_length=120)],
) -> dict[str, Any]:
    """按诊断 ID 查询路由、检索上下文、耗时、Token 和错误记录。"""
    item = diagnosis_repository.get_diagnosis_trace(diagnosis_id)
    return success(item) if item else failure("DIAGNOSIS_NOT_FOUND", f"Diagnosis {diagnosis_id} does not exist")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def get_device_status(
    device_id: Annotated[str, Field(min_length=1, max_length=120)],
) -> dict[str, Any]:
    """查询设备在线状态、WiFi、RSSI、MQTT、温度、uptime 和最近上报时间。"""
    item = diagnosis_repository.get_device_status(device_id)
    return success(item) if item else failure("DEVICE_NOT_FOUND", f"Device {device_id} does not exist")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def list_devices(
    device_type: str | None = None,
    online: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """列出已发现设备及其最新状态，可按设备类型和当前在线状态过滤。"""
    return success(diagnosis_repository.list_devices(device_type, online, limit, offset))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def get_device_logs(
    device_id: Annotated[str, Field(min_length=1, max_length=120)],
    limit: int = 50,
    level: str | None = None,
) -> dict[str, Any]:
    """读取指定设备最近日志，可按日志级别过滤。"""
    items = diagnosis_repository.get_device_logs(device_id, limit, level)
    if items is None:
        return failure("DEVICE_NOT_FOUND", f"Device {device_id} does not exist")
    return success({"device_id": device_id, "logs": items})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def search_knowledge(
    query: str,
    sources: list[str] | None = None,
    top_k: int = 5,
    strategy: str | None = None,
) -> dict[str, Any]:
    """按指定来源或 Adaptive Router 的选择执行多源知识检索和统一重排。"""
    try:
        return success(retrieve_knowledge(diagnosis_repository, query, sources, top_k, strategy=strategy))
    except ValueError:
        return failure("INVALID_REQUEST", "包含不支持的知识源")
    except Exception:
        logger.exception("知识检索失败")
        return failure("RETRIEVAL_FAILED", "知识检索失败", retryable=True)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def list_knowledge_documents(
    source: str | None = None,
    device_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """列出已摄取知识文档及分块数量，不返回大段正文。"""
    return success(diagnosis_repository.list_knowledge_documents(source, device_type, limit, offset))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def list_fault_cases(
    device_type: Annotated[str | None, Field(max_length=120)] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0, le=100_000)] = 0,
) -> dict[str, Any]:
    """分页列出已验证故障案例（含沉淀来源与根因摘要，不含逐条日志）。"""
    return success(diagnosis_repository.list_fault_cases(device_type, limit, offset))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def search_fault_cases(
    query: Annotated[str, Field(min_length=1, max_length=2000)],
    device_type: Annotated[str | None, Field(max_length=120)] = "ESP32",
    fault_type: Annotated[str | None, Field(max_length=120)] = None,
    top_k: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict[str, Any]:
    """检索已由人工确认的历史故障案例。"""
    try:
        results = retrieve_fault_cases(diagnosis_repository, query, device_type, fault_type, top_k)
        return success({"results": results})
    except Exception:
        logger.exception("故障案例检索失败")
        return failure("RETRIEVAL_FAILED", "故障案例检索失败", retryable=True)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def list_diagnoses(
    device_id: Annotated[str | None, Field(max_length=120)] = None,
    fault_type: Annotated[str | None, Field(max_length=120)] = None,
    status: Annotated[str, Field(pattern="^(all|succeeded|failed)$")] = "all",
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0, le=100_000)] = 0,
) -> dict[str, Any]:
    """列出诊断历史摘要，可过滤设备、故障类型及成功或失败状态。"""
    return success(diagnosis_repository.list_diagnoses(device_id, fault_type, status, limit, offset))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def add_verified_fault_case(
    device_id: Annotated[str, Field(min_length=1, max_length=120)],
    fault_type: Annotated[str, Field(min_length=1, max_length=120)],
    fault_name: Annotated[str, Field(min_length=1, max_length=300)],
    symptoms: Annotated[list[str], Field(min_length=1, max_length=20)],
    logs: Annotated[list[str], Field(min_length=1, max_length=50)],
    cause: Annotated[str, Field(min_length=1, max_length=4000)],
    solution: Annotated[str, Field(min_length=1, max_length=4000)],
    verified: bool,
    verified_by: Annotated[str | None, Field(max_length=160)] = None,
) -> dict[str, Any]:
    """仅在人工确认信息完整时写入故障案例并加入检索索引。"""
    if not verified or not verified_by or not verified_by.strip():
        return failure("CASE_NOT_VERIFIED", "故障案例必须经过人工确认")
    try:
        return success(
            diagnosis_repository.add_verified_fault_case(
                {
                    "device_id": device_id,
                    "fault_type": fault_type,
                    "fault_name": fault_name,
                    "symptoms": symptoms,
                    "logs": logs,
                    "cause": cause,
                    "solution": solution,
                    "verified_by": verified_by.strip(),
                }
            )
        )
    except Exception:
        logger.exception("故障案例写入失败")
        return failure("DATABASE_ERROR", "故障案例写入失败", retryable=True)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def ingest_knowledge_text(
    source: str,
    document_id: Annotated[str, Field(min_length=1, max_length=120)],
    title: Annotated[str, Field(min_length=1, max_length=300)],
    content: Annotated[str, Field(min_length=1, max_length=200_000)],
    device_type: Annotated[str | None, Field(max_length=120)] = "ESP32",
    chunk_size: Annotated[int | None, Field(ge=64, le=4000)] = None,
    overlap: Annotated[int | None, Field(ge=0, le=1000)] = None,
) -> dict[str, Any]:
    """摄取已提取的文本或 Markdown，按结构感知 + token 分块后写入知识库和向量索引。"""
    try:
        return success(
            ingest_text(
                diagnosis_repository,
                source=source,
                document_id=document_id,
                title=title,
                content=content,
                device_type=device_type,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )
    except ValueError as exc:
        return failure(str(exc), "知识文档参数无效")
    except Exception:
        logger.exception("知识文档写入失败")
        return failure("DATABASE_ERROR", "知识文档写入失败", retryable=True)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def delete_knowledge_document(
    source: str,
    document_id: Annotated[str, Field(min_length=1, max_length=120)],
) -> dict[str, Any]:
    """从 SQLite 和 Qdrant 向量索引中删除整个知识文档。"""
    try:
        return success(diagnosis_repository.delete_knowledge_document(source=source, document_id=document_id))
    except ValueError as exc:
        return failure(str(exc), "知识文档参数无效")
    except Exception:
        logger.exception("知识文档删除失败")
        return failure("DATABASE_ERROR", "知识文档删除失败", retryable=True)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def delete_fault_case(
    fault_id: Annotated[str, Field(min_length=2, max_length=32)],
) -> dict[str, Any]:
    """删除一条已验证故障案例，并同步清理 Qdrant 向量。"""
    try:
        return success(diagnosis_repository.delete_fault_case(fault_id))
    except ValueError:
        return failure("FAULT_ID_INVALID", "案例编号无效")
    except Exception:
        logger.exception("故障案例删除失败")
        return failure("DATABASE_ERROR", "故障案例删除失败", retryable=True)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def rebuild_vector_index(
    sources: Annotated[list[str] | None, Field(max_length=5)] = None,
) -> dict[str, Any]:
    """以 SQLite 中的知识分块和已确认案例为准，批量重建 Qdrant 向量索引。"""
    try:
        return success(diagnosis_repository.rebuild_vector_index(sources))
    except ValueError:
        return failure("INVALID_REQUEST", "包含不支持的知识源")
    except Exception:
        logger.exception("向量索引重建失败")
        return failure("VECTOR_REBUILD_FAILED", "向量索引重建失败", retryable=True)


# ============================================================================
# CONTROL TOOLS
# ============================================================================


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def list_device_actions(
    device_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None,
) -> dict[str, Any]:
    """列出可下发的设备修复动作、风险级别、参数与适用故障类型。"""
    return success({"actions": actions.action_catalog()})


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def execute_device_action(
    device_id: Annotated[str, Field(min_length=1, max_length=120)],
    action: Annotated[str, Field(min_length=1, max_length=120)],
    reason: Annotated[str, Field(min_length=1, max_length=2000)],
    diagnosis_id: Annotated[str, Field(min_length=21, max_length=21, pattern=r"^DIA_\d{8}_[A-F0-9]{8}$")],
    parameters: Annotated[dict[str, Any] | None, Field(max_properties=10)] = None,
    issued_by: Annotated[str, Field(max_length=160)] = "agent",
) -> dict[str, Any]:
    """下发低风险修复动作（重启/改配置等高风险动作会被拒绝并要求走提案审批）。"""
    item = actions.get_action(action)
    if not item:
        return failure("UNKNOWN_ACTION", f"Action {action} is not supported")
    if item["risk_level"] != actions.LOW_RISK:
        return failure(
            "ACTION_REQUIRES_APPROVAL",
            "高风险动作需要人工批准，请改用 create_remediation_proposal 创建修复提案",
            details={"action": action, "risk_level": item["risk_level"]},
        )
    if error_code := actions.validate_parameters(action, parameters):
        return failure(error_code, "动作参数无效")

    # Verify diagnosis exists and matches device
    diagnosis = diagnosis_repository.get_diagnosis_trace(diagnosis_id)
    if not diagnosis:
        return failure("DIAGNOSIS_NOT_FOUND", f"诊断记录 {diagnosis_id} 不存在", retryable=False)
    if diagnosis.get("device_id") != device_id:
        return failure("DIAGNOSIS_DEVICE_MISMATCH", "诊断记录与设备 ID 不匹配", retryable=False)

    command = control_repository.create_command(
        device_id=device_id,
        action=action,
        risk_level=item["risk_level"],
        parameters=parameters,
        reason=reason,
        issued_by=issued_by,
        diagnosis_id=diagnosis_id,
    )

    # Send via MQTT if available
    if control_mqtt:
        delivered = control_mqtt.send_command(device_id, command)
        return success({**command, "delivered": delivered})
    else:
        return failure("MQTT_UNAVAILABLE", "设备控制通道未启用", retryable=True)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def create_remediation_proposal(
    device_id: Annotated[str, Field(min_length=1, max_length=120)],
    action: Annotated[str, Field(min_length=1, max_length=120)],
    reason: Annotated[str, Field(min_length=1, max_length=4000)],
    impact: Annotated[str, Field(min_length=1, max_length=4000)],
    diagnosis_id: Annotated[str, Field(min_length=21, max_length=21, pattern=r"^DIA_\d{8}_[A-F0-9]{8}$")],
    parameters: Annotated[dict[str, Any] | None, Field(max_properties=10)] = None,
) -> dict[str, Any]:
    """为高风险动作创建修复提案，等待人工批准后才会执行。"""
    item = actions.get_action(action)
    if not item:
        return failure("UNKNOWN_ACTION", f"Action {action} is not supported")
    if item["risk_level"] != actions.HIGH_RISK:
        return failure(
            "ACTION_NOT_HIGH_RISK",
            "低风险动作可直接执行，请改用 execute_device_action",
            details={"action": action, "risk_level": item["risk_level"]},
        )
    if error_code := actions.validate_parameters(action, parameters):
        return failure(error_code, "动作参数无效")

    # Verify diagnosis exists and matches device
    diagnosis = diagnosis_repository.get_diagnosis_trace(diagnosis_id)
    if not diagnosis:
        return failure("DIAGNOSIS_NOT_FOUND", f"诊断记录 {diagnosis_id} 不存在", retryable=False)
    if diagnosis.get("device_id") != device_id:
        return failure("DIAGNOSIS_DEVICE_MISMATCH", "诊断记录与设备 ID 不匹配", retryable=False)

    proposal = control_repository.create_proposal(
        device_id=device_id,
        action=action,
        parameters=parameters,
        reason=reason,
        impact=impact,
        diagnosis_id=diagnosis_id,
    )
    return success(proposal)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def get_action_result(
    command_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None,
    proposal_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None,
) -> dict[str, Any]:
    """按命令 ID 或提案 ID 查询执行与恢复验证状态。"""
    if not command_id and not proposal_id:
        return failure("INVALID_REQUEST", "command_id 与 proposal_id 至少提供一个")
    if command_id:
        command = control_repository.get_command(command_id)
        if command is None:
            return failure("COMMAND_NOT_FOUND", f"Command {command_id} does not exist")
        return success({"command": command})
    assert proposal_id is not None
    proposal = control_repository.get_proposal(proposal_id)
    if proposal is None:
        return failure("PROPOSAL_NOT_FOUND", f"Proposal {proposal_id} does not exist")
    command = control_repository.get_command(proposal["command_id"]) if proposal["command_id"] else None
    return success({"proposal": proposal, "command": command})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False))
def list_remediation_proposals(
    status: Annotated[str | None, Field(pattern="^(pending|approved|rejected|expired)$")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
    offset: Annotated[int, Field(ge=0, le=100_000)] = 0,
) -> dict[str, Any]:
    """列出修复提案，可按状态过滤并分页；过期待提案会自动标记为 expired。"""
    return success(control_repository.list_proposals(status, limit, offset))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
def decide_remediation_proposal(
    proposal_id: Annotated[str, Field(min_length=1, max_length=120)],
    decision: Annotated[str, Field(pattern="^(approved|rejected)$")],
    decided_by: Annotated[str, Field(min_length=1, max_length=160)],
    expected_version: Annotated[int, Field(ge=1)],
) -> dict[str, Any]:
    """人工决策修复提案；批准后立即下发命令并进入恢复验证（仅限已授权后端调用）。"""
    proposal = control_repository.get_proposal(proposal_id)
    if proposal is None:
        return failure("PROPOSAL_NOT_FOUND", f"Proposal {proposal_id} does not exist")

    # Verify diagnosis if approving
    if decision == "approved":
        diagnosis = diagnosis_repository.get_diagnosis_trace(proposal["diagnosis_id"])
        if not diagnosis:
            return failure("DIAGNOSIS_NOT_FOUND", f"诊断记录 {proposal['diagnosis_id']} 不存在", retryable=False)
        if diagnosis.get("device_id") != proposal["device_id"]:
            return failure("DIAGNOSIS_DEVICE_MISMATCH", "诊断记录与设备 ID 不匹配", retryable=False)

    try:
        proposal, command = control_repository.decide_proposal(
            proposal_id,
            decision,
            decided_by,
            expected_version,
            risk_level_of=actions.risk_level,
        )
    except LookupError:
        return failure("PROPOSAL_NOT_FOUND", f"Proposal {proposal_id} does not exist")
    except ValueError as exc:
        return failure(str(exc), "提案决策被拒绝")

    delivered = None
    if command is not None:
        if control_mqtt:
            delivered = control_mqtt.send_command(proposal["device_id"], command)
        else:
            return failure("MQTT_UNAVAILABLE", "设备控制通道未启用", retryable=True)

    return success({**proposal, "command": command, "delivered": delivered})


@mcp.custom_route("/ready", methods=["GET"])
async def ready_check(_request: Request) -> JSONResponse:
    """Health check endpoint for Docker healthcheck."""
    return JSONResponse({"status": "ready"})


if __name__ == "__main__":
    host = os.getenv("IOT_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("IOT_MCP_PORT", "9000"))

    # Setup OpenTelemetry tracing
    setup_telemetry("xiaoyi-iot-mcp")

    logger.info(f"Starting unified IoT MCP server on {host}:{port}")

    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
    )

