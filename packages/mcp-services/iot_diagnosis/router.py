from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from iot_diagnosis.llm import DiagnosisLLMClient, LLMClientError

ALLOWED_SOURCES = {
    "fault_cases",
    "mqtt_docs",
    "wifi_docs",
    "sensor_docs",
    "device_docs",
    "realtime_db",
}

# 语义路由原型：每个知识源用一段覆盖典型故障词汇的描述文本表示，
# 首次使用时生成向量并缓存，查询时按余弦相似度选择来源。
SOURCE_PROTOTYPES = {
    "mqtt_docs": (
        "MQTT broker 连接 心跳 keep alive timeout 超时 报文 publish subscribe "
        "QoS session 会话 认证 鉴权 掉线 断开 CONNACK mosquitto 重连"
    ),
    "wifi_docs": (
        "WiFi 无线 RSSI 信号强度 弱信号 断线 掉线 重连 接入点 AP 信道 "
        "干扰 packet loss 丢包 延迟 latency 关联认证"
    ),
    "sensor_docs": (
        "传感器 sensor 采样 ADC I2C SPI 校准 calibration 漂移 drift "
        "读数 量程 温度 temperature 异常值 无数据"
    ),
    "device_docs": (
        "固件 firmware OTA 升级 upgrade 重启 reboot 复位 reset 内存 heap 内存泄漏 碎片 "
        "看门狗 watchdog core dump backtrace 崩溃 crash panic 栈 存储 NVS 分区 "
        "电源管理 power management 睡眠 sleep 唤醒 wake 事件 event 日志 log GPIO"
    ),
    "fault_cases": (
        "已验证的故障案例 历史维修记录 根因分析 解决方案 verified case 类似故障 曾经发生"
    ),
}


def _cosine(left: list[float], right: list[float]) -> float:
    paired = zip(left, right, strict=True)
    dot = sum(a * b for a, b in paired)
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


def semantic_sources(
    query: str,
    embedding_provider: Any | None,
) -> list[str]:
    """按查询向量与知识源原型向量的相似度选择检索来源，失败返回空列表。"""
    if embedding_provider is None:
        return []
    try:
        cache = _prototype_cache.setdefault(getattr(embedding_provider, "name", "default"), {})
        provider_dims = getattr(embedding_provider, "dimensions", None)
        if cache.get("dims") != provider_dims or len(cache.get("vectors", {})) < len(
            SOURCE_PROTOTYPES
        ):
            cache["vectors"] = {
                source: embedding_provider.embed(text) for source, text in SOURCE_PROTOTYPES.items()
            }
            cache["dims"] = provider_dims
        query_vector = embedding_provider.embed(query, is_query=True)
        scored = sorted(
            (
                (source, _cosine(query_vector, vector))
                for source, vector in cache["vectors"].items()
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        topic_sources = [source for source, _ in scored if source != "fault_cases"]
        if not topic_sources:
            return []
        # fault_cases 恒定入选，主题源必须从其余来源中挑选，
        # 否则案例原型得分最高时会导致主题文档源全部丢失
        top_source = topic_sources[0]
        top_score = dict(scored)[top_source]
        selected = ["fault_cases", top_source]
        second = dict(scored).get(topic_sources[1]) if len(topic_sources) > 1 else 0.0
        if second and second >= 0.9 * top_score:
            selected.append(topic_sources[1])
        return selected
    except Exception:
        return []


_prototype_cache: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class RouteDecision:
    fault_type: str
    need_retrieval: bool
    sources: list[str]
    top_k: int
    router: str
    llm_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_fault_type(text: str) -> str:
    lowered = text.lower()
    if (
        "mqtt" in lowered
        or "broker" in lowered
        or "keep alive" in lowered
        or "unauthorized" in lowered
        or "bad user name" in lowered
    ):
        return "mqtt"
    if (
        "wifi" in lowered
        or "rssi" in lowered
        or "无线" in lowered
        or "latency" in lowered
        or "packet loss" in lowered
        or "延迟" in lowered
        or "丢包" in lowered
    ):
        return "wifi"
    if "温度" in lowered or "sensor" in lowered or "传感器" in lowered:
        return "sensor"
    if any(
        marker in lowered
        for marker in (
            "内存",
            "heap",
            "重启",
            "reboot",
            "reset",
            "watchdog",
            "固件",
            "firmware",
            "oom",
        )
    ):
        return "device"
    return "unknown"


def route_query(
    query: str,
    state: dict[str, Any] | None = None,
    logs: list[str] | None = None,
    llm_client: DiagnosisLLMClient | None = None,
    embedding_provider: Any | None = None,
) -> RouteDecision:
    normalized = query.lower().replace(" ", "")
    realtime_patterns = (
        "当前rssi",
        "现在rssi",
        "rssi多少",
        "当前温度",
        "现在温度",
        "温度多少",
        "设备在线",
        "是否在线",
        "在线吗",
        "mqtt状态",
        "mqtt连接状态",
        "wifi状态",
        "wifi连接状态",
        "当前状态",
    )
    diagnostic_markers = ("为什么", "原因", "故障", "异常", "断开", "超时", "失败")
    fault_type = infer_fault_type(" ".join([query, *(logs or [])]))

    if any(pattern in normalized for pattern in realtime_patterns) and not any(
        marker in normalized for marker in diagnostic_markers
    ):
        return RouteDecision(
            fault_type=fault_type,
            need_retrieval=False,
            sources=["realtime_db"],
            top_k=1,
            router="rule",
        )

    # 语义路由：一次查询向量化（约 10ms）即可完成来源选择，省去一次
    # 完整的 LLM Router 往返；失败时才回落到 LLM Router / 关键词映射。
    provider = embedding_provider
    if provider is None:
        try:
            from iot_diagnosis.embeddings import embedding_provider_from_env

            provider = embedding_provider_from_env()
        except Exception:
            provider = None
    semantic = semantic_sources(query, provider)
    if semantic:
        sources = [*semantic, *(["realtime_db"] if state else [])]
        return RouteDecision(
            fault_type=fault_type,
            need_retrieval=True,
            sources=list(dict.fromkeys(sources)),
            top_k=5,
            router="semantic",
        )

    client = llm_client or DiagnosisLLMClient.from_env()
    if client.available:
        try:
            response = client.route(query, state, logs or [])
            data = response.data
            sources = validate_sources(list(data.get("sources") or []))
            if not sources:
                raise ValueError("INVALID_REQUEST")
            top_k = min(max(int(data.get("top_k") or 5), 1), 20)
            return RouteDecision(
                fault_type=str(data.get("fault_type") or fault_type),
                need_retrieval=bool(data.get("need_retrieval", True)),
                sources=sources,
                top_k=top_k,
                router="llm",
                llm_latency_ms=response.latency_ms,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
        except (LLMClientError, TypeError, ValueError):
            pass

    source_map = {
        "mqtt": ["fault_cases", "mqtt_docs", "realtime_db"],
        "wifi": ["fault_cases", "wifi_docs", "realtime_db"],
        "sensor": ["fault_cases", "sensor_docs", "realtime_db"],
        "device": ["fault_cases", "device_docs", "realtime_db"],
        "unknown": ["fault_cases", "device_docs", "realtime_db"],
    }
    sources = source_map[fault_type]
    if state and state.get("mqtt_status") == "disconnected" and "mqtt_docs" not in sources:
        sources = ["fault_cases", "mqtt_docs", *sources[1:]]
    return RouteDecision(
        fault_type=fault_type,
        need_retrieval=True,
        sources=list(dict.fromkeys(sources)),
        top_k=5,
        router="heuristic_fallback",
    )


def validate_sources(sources: list[str]) -> list[str]:
    invalid = set(sources) - ALLOWED_SOURCES
    if invalid:
        raise ValueError("INVALID_REQUEST")
    return list(dict.fromkeys(sources))
