from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from iot_diagnosis.llm import DiagnosisLLMClient, LLMClientError
from iot_diagnosis.repository import DiagnosisRepository
from iot_diagnosis.retrieval import search_knowledge
from iot_diagnosis.router import RouteDecision, route_query


def _realtime_answer(query: str, state: dict[str, Any]) -> str:
    normalized = query.lower().replace(" ", "")
    if "rssi" in normalized or "信号" in normalized:
        return f"设备当前 RSSI 为 {state.get('rssi')} dBm"
    if "温度" in normalized or "temperature" in normalized:
        return f"设备当前温度为 {state.get('temperature')} °C"
    if "在线" in normalized:
        return "设备当前在线" if state.get("online") else "设备当前离线"
    if "mqtt" in normalized:
        return f"设备当前 MQTT 状态为 {state.get('mqtt_status')}"
    if "wifi" in normalized or "无线" in normalized:
        return f"设备当前 WiFi 状态为 {state.get('wifi_status')}"
    return (
        f"设备当前在线={state.get('online')}，WiFi={state.get('wifi_status')}，"
        f"RSSI={state.get('rssi')} dBm，MQTT={state.get('mqtt_status')}，"
        f"温度={state.get('temperature')} °C"
    )


def _profile(text: str, state: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    temperature = state.get("temperature")
    explicitly_wifi = "wifi" in lowered or "rssi" in lowered or "无线" in lowered
    explicitly_sensor = "sensor" in lowered or "传感器" in lowered or "温度" in lowered
    explicitly_device = (
        "内存" in lowered or "heap" in lowered or "固件" in lowered or "重启" in lowered
    )

    if ("mqtt" in lowered or "broker" in lowered) and any(
        marker in lowered
        for marker in (
            "auth",
            "unauthorized",
            "not authorized",
            "bad user name",
            "认证",
            "鉴权",
            "用户名",
            "密码",
        )
    ):
        return {
            "fault_type": "mqtt_connection",
            "fault_name": "MQTT 认证失败",
            "cause": "MQTT 用户名、密码、Client ID 或 Broker ACL 配置可能不匹配",
            "solutions": [
                "核对 MQTT 用户名和密码",
                "检查 Client ID 冲突",
                "检查 Broker ACL 与认证日志",
            ],
        }
    if ("broker" in lowered or "mqtt" in lowered) and any(
        marker in lowered
        for marker in (
            "unreachable",
            "refused",
            "不可达",
            "拒绝连接",
            "connection failed",
            "connect failed",
            "连接失败",
        )
    ):
        return {
            "fault_type": "mqtt_connection",
            "fault_name": "MQTT Broker 不可达",
            "cause": "Broker 地址、端口、DNS、路由或服务监听状态可能异常",
            "solutions": [
                "核对 Broker 地址与端口",
                "检查 DNS 和网络路由",
                "确认 Broker 服务已启动并监听目标端口",
            ],
        }
    if any(marker in lowered for marker in ("latency", "延迟", "丢包", "packet loss")):
        return {
            "fault_type": "network_connection",
            "fault_name": "网络延迟或丢包异常",
            "cause": "网络拥塞、信号质量或链路抖动可能导致请求超时和连接不稳定",
            "solutions": ["测量往返延迟与丢包率", "检查 WiFi 信号和信道拥塞", "检查上游网络负载"],
        }
    if (
        "keep alive" in lowered
        or "keepalive" in lowered
        or ("mqtt" in lowered and "timeout" in lowered)
    ):
        return {
            "fault_type": "mqtt_connection",
            "fault_name": "MQTT Keep Alive Timeout",
            "cause": "MQTT Keep Alive 参数、Broker 超时配置或客户端心跳可能异常",
            "solutions": [
                "检查 MQTT Keep Alive 参数",
                "检查 Broker 连接超时配置",
                "确认客户端心跳是否正常发送",
            ],
        }
    if explicitly_wifi and any(
        marker in lowered for marker in ("disconnect", "断开", "掉线", "未连接")
    ):
        return {
            "fault_type": "wifi_connection",
            "fault_name": "WiFi 连接断开",
            "cause": "接入点可用性、凭据、供电或重连流程可能异常",
            "solutions": ["确认接入点可用", "核对 WiFi 凭据", "检查供电和 WiFi 重连日志"],
        }
    if explicitly_wifi or (state.get("rssi") or 0) < -75:
        return {
            "fault_type": "wifi_connection",
            "fault_name": "WiFi 弱信号",
            "cause": "无线信号弱、信道拥塞或接入点距离可能导致连接不稳定",
            "solutions": ["检查天线与供电", "缩短接入点距离", "检查信道拥塞与重连日志"],
        }
    if explicitly_sensor and any(
        marker in lowered for marker in ("read failed", "读取失败", "no data", "无数据", "超时")
    ):
        return {
            "fault_type": "sensor_anomaly",
            "fault_name": "传感器读取失败",
            "cause": "传感器接线、总线通信、供电或驱动初始化可能异常",
            "solutions": ["检查接线和供电", "检查 I2C/SPI 总线错误", "重新核对驱动与设备地址"],
        }
    if explicitly_sensor or (temperature is not None and temperature >= 70):
        return {
            "fault_type": "sensor_anomaly",
            "fault_name": "传感器数据异常",
            "cause": "传感器量程、校准、采样周期或环境条件可能异常",
            "solutions": ["核对量程和采样周期", "重新校准传感器", "使用参考设备交叉验证"],
        }
    if any(marker in lowered for marker in ("heap", "内存", "out of memory", "oom")):
        return {
            "fault_type": "device_runtime",
            "fault_name": "设备内存不足",
            "cause": "堆内存持续消耗、碎片化或资源未释放可能导致运行异常",
            "solutions": ["记录空闲堆和最小空闲堆", "检查资源释放与内存泄漏", "降低缓冲区峰值占用"],
        }
    if any(marker in lowered for marker in ("重启", "reboot", "reset", "复位")):
        return {
            "fault_type": "device_runtime",
            "fault_name": "设备异常重启",
            "cause": "供电、看门狗、崩溃或固件异常可能触发设备复位",
            "solutions": ["读取复位原因", "检查供电稳定性", "收集崩溃栈和看门狗日志"],
        }
    if "mqtt" in lowered or (
        not (explicitly_wifi or explicitly_sensor or explicitly_device)
        and state.get("mqtt_status") == "disconnected"
    ):
        return {
            "fault_type": "mqtt_connection",
            "fault_name": "MQTT 连接异常",
            "cause": "Broker 可用性、网络链路或客户端连接参数可能异常",
            "solutions": [
                "检查 Broker 地址与服务状态",
                "检查客户端连接参数",
                "收集 CONNACK 和断开原因日志",
            ],
        }
    return {
        "fault_type": "device_runtime",
        "fault_name": "设备运行状态异常",
        "cause": "当前证据不足，可能与固件、内存或网络状态有关",
        "solutions": ["收集更完整日志", "检查固件版本与复位原因", "安排人工现场检查"],
    }


def diagnose(
    repository: DiagnosisRepository,
    device_id: str,
    query: str,
    supplied_logs: list[str] | None,
    use_realtime_state: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    llm_client = DiagnosisLLMClient.from_env()
    state = repository.get_device_status(device_id)
    if not state:
        raise LookupError("DEVICE_NOT_FOUND")
    log_records = repository.get_device_logs(device_id, 50) or []
    logs = supplied_logs or [str(item["message"]) for item in log_records]
    route: RouteDecision = route_query(
        query,
        state if use_realtime_state else None,
        logs,
        llm_client,
        embedding_provider=getattr(
            getattr(repository.external, "qdrant", None), "embedding_provider", None
        ),
    )

    retrieval_started = time.perf_counter()
    if route.need_retrieval:
        retrieval = search_knowledge(
            repository,
            query,
            route.sources,
            route.top_k,
            state=state if use_realtime_state else None,
            logs=logs,
        )
    else:
        realtime_content = _realtime_answer(query, state)
        retrieval = {
            "candidate_count": 0,
            "results": [
                {
                    "source": "realtime_db",
                    "id": device_id,
                    "title": "当前设备状态",
                    "content": realtime_content,
                    "score": 1.0,
                }
            ],
            "selected_sources": route.sources,
            "rewritten_query": query,
        }
    retrieval_latency_ms = round((time.perf_counter() - retrieval_started) * 1000, 3)

    primary_evidence = " ".join([query, *logs])
    direct_answer = _realtime_answer(query, state) if not route.need_retrieval else None
    profile = (
        {
            "fault_type": "realtime_state",
            "fault_name": "设备实时状态",
            "cause": direct_answer,
            "solutions": [],
            "severity": "info",
            "confidence": 1.0,
            "requires_manual_inspection": False,
        }
        if direct_answer
        else _profile(primary_evidence, state)
    )
    llm_latency_ms = route.llm_latency_ms
    input_tokens = route.input_tokens
    output_tokens = route.output_tokens
    llm_fallback_reason = None if direct_answer or llm_client.available else "LLM_NOT_CONFIGURED"
    if route.need_retrieval and llm_client.available:
        try:
            llm_response = llm_client.diagnose(query, state, logs, retrieval["results"])
            candidate = llm_response.data
            solutions = candidate.get("solutions")
            required = ("fault_type", "fault_name", "cause")
            if not all(isinstance(candidate.get(key), str) and candidate[key] for key in required):
                raise LLMClientError("LLM_RESPONSE_INVALID")
            if not isinstance(solutions, list) or not solutions:
                raise LLMClientError("LLM_RESPONSE_INVALID")
            profile = {
                "fault_type": candidate["fault_type"],
                "fault_name": candidate["fault_name"],
                "cause": candidate["cause"],
                "solutions": [str(item) for item in solutions],
                "severity": str(candidate.get("severity") or "medium"),
                "confidence": float(candidate.get("confidence") or 0.5),
                "requires_manual_inspection": bool(
                    candidate.get("requires_manual_inspection", False)
                ),
            }
            llm_latency_ms += llm_response.latency_ms
            input_tokens += llm_response.input_tokens
            output_tokens += llm_response.output_tokens
        except (LLMClientError, TypeError, ValueError):
            llm_fallback_reason = "LLM_DIAGNOSIS_FAILED"
    evidence = []
    if use_realtime_state:
        evidence.extend(
            [
                f"WiFi={state['wifi_status']}",
                f"RSSI={state['rssi']} dBm",
                f"MQTT={state['mqtt_status']}",
                f"temperature={state['temperature']} °C",
            ]
        )
    evidence.extend(logs[:5])

    retrieval_results = cast(list[dict[str, Any]], retrieval["results"])
    scores = [float(item["score"]) for item in retrieval_results]
    retrieval_score = max(scores, default=0.8 if not route.need_retrieval else 0.0)
    case_similarity = max(
        (float(item["score"]) for item in retrieval_results if item["source"] == "fault_cases"),
        default=0.0,
    )
    evidence_score = min(1.0, len(evidence) / 5)
    llm_score = min(max(float(cast(Any, profile.get("confidence", 0.82))), 0.0), 1.0)
    if not llm_client.available and profile["fault_type"] == "device_runtime":
        llm_score = 0.55
    confidence = (
        1.0
        if direct_answer
        else round(
            0.35 * retrieval_score
            + 0.25 * evidence_score
            + 0.20 * case_similarity
            + 0.20 * llm_score,
            4,
        )
    )
    severity = profile.get("severity") or (
        "high" if not state["online"] or (state.get("temperature") or 0) >= 70 else "medium"
    )
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    sources = [
        {"source_type": item["source"], "source_id": item["id"], "score": item["score"]}
        for item in retrieval_results[:4]
    ]
    request_id = str(uuid.uuid4())
    result = {
        "diagnosis_id": f"DIA_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:8].upper()}",
        "device_id": device_id,
        "fault_type": profile["fault_type"],
        "fault_name": profile["fault_name"],
        "severity": severity,
        "confidence": confidence,
        "cause": profile["cause"],
        "evidence": list(dict.fromkeys(evidence)),
        "solutions": profile["solutions"],
        "requires_manual_inspection": bool(
            profile.get("requires_manual_inspection", confidence < 0.65)
        ),
        "route": {
            "router": route.router,
            "retrieval_required": route.need_retrieval,
            "selected_sources": route.sources,
        },
        "sources": sources,
        "observability": {
            "request_id": request_id,
            "retrieval_count": int(retrieval["candidate_count"]),
            "rerank_count": len(retrieval_results) if route.need_retrieval else 0,
            "retrieval_latency_ms": retrieval_latency_ms,
            "llm_latency_ms": round(llm_latency_ms, 3),
            "total_latency_ms": elapsed,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "llm_fallback_reason": llm_fallback_reason,
            "error": None,
        },
    }
    if direct_answer:
        result["answer"] = direct_answer
        result["realtime_state"] = state
    repository.save_diagnosis(
        {
            **result,
            "request_id": request_id,
            "query": query,
            "trace_contexts": retrieval_results[:4],
        }
    )
    return result
