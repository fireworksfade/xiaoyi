"""批量生成真实故障案例：注入故障 → 诊断 → 修复闭环 → 自动沉淀。

在 iot-diagnosis-mcp 容器内运行：
    python scripts/generate_fault_cases.py [--rounds 2]

每条案例的流程（走真实 MCP/ MQTT 链路，与服务内闭环完全一致）：
1. 经 MQTT 向设备发布 inject_fault(normal) 清空历史故障标志，再注入目标场景
2. 等待故障遥测/日志经 MQTTIngestor 落库
3. 经 MCP 调 diagnose_fault 取得 diagnosis_id
4. 低风险动作经 execute_device_action 直发；高风险动作经
   create_remediation_proposal + decide_remediation_proposal 立即批准
5. 轮询 get_action_result 直至恢复验证收敛（verify_status succeeded/failed），
   失败自动重试一次
6. 校验案例库计数递增（修复完成事件由诊断服务异步归档）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

try:  # mcp>=2.x 内置的 httpx 工厂，便于注入 Bearer 头
    from mcp.shared._httpx_utils import create_mcp_http_client
except ImportError:  # pragma: no cover - 兼容旧版包结构
    from mcp.client.streamable_http import create_mcp_http_client

DIAGNOSIS_URL = os.getenv("CASE_GEN_DIAGNOSIS_URL", "http://127.0.0.1:9001/mcp")
CONTROL_URL = os.getenv("CASE_GEN_CONTROL_URL", "http://iot-control-mcp:9002/mcp")
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
ISSUED_BY = "case-generator"

SCENARIOS4 = ("mqtt_timeout", "wifi_weak", "sensor_error", "unstable")
DEVICES = tuple(f"ESP32_{i:02d}" for i in range(1, 13))

DIAGNOSIS_QUERY = {
    "mqtt_timeout": "设备 MQTT 频繁掉线，日志持续报 keep alive timeout，无法维持与 Broker 的连接",
    "wifi_weak": "WiFi 信号弱，RSSI 低于 -80 dBm，连接不稳定且频繁断开",
    "sensor_error": "温度传感器读数异常，长时间卡在 78°C 高温不变，与现场实际温度不符",
    "unstable": "设备间歇性离线，网络时断时续，RSSI 在诊断阈值附近波动",
}

LOW_ACTION = {
    "mqtt_timeout": "reconnect_mqtt",
    "wifi_weak": "reconnect_wifi",
    "sensor_error": "calibrate_sensor",
    "unstable": "reconnect_wifi",
}

ACTION_REASON = {
    "reconnect_mqtt": "诊断确认 MQTT 连接超时，重置连接并重新接入 Broker",
    "reconnect_wifi": "诊断确认 WiFi 弱信号/间歇离线，重新扫描并连接 AP",
    "calibrate_sensor": "诊断确认传感器读数卡死异常，执行零点校准清除异常值",
    "restart_device": "诊断确认运行时异常，远程重启设备以清除异常状态",
    "update_firmware": "诊断确认运行时异常疑似固件问题，升级固件到修复版本",
}


@dataclass(frozen=True)
class CasePlan:
    device_id: str
    scenario: str
    action: str
    parameters: dict[str, Any]
    high_risk: bool
    query: str = ""

    @property
    def mode(self) -> str:
        return "proposal" if self.high_risk else "direct"

    @property
    def diagnosis_query(self) -> str:
        return self.query or DIAGNOSIS_QUERY[self.scenario]


def build_plans(rounds: int) -> list[CasePlan]:
    """两轮覆盖 12 节点 × 4 类故障；第二轮穿插 3 条高风险提案路径。"""
    plans: list[CasePlan] = []
    for round_index in range(rounds):
        for offset, device_id in enumerate(DEVICES):
            scenario = SCENARIOS4[(offset + round_index) % len(SCENARIOS4)]
            plans.append(
                CasePlan(
                    device_id=device_id,
                    scenario=scenario,
                    action=LOW_ACTION[scenario],
                    parameters={},
                    high_risk=False,
                    query=DIAGNOSIS_QUERY[scenario],
                )
            )
    if rounds >= 2:
        # 覆盖第二轮中 scenario 对应的高风险动作（restart 适用于
        # mqtt_connection/device_runtime/sensor_anomaly，固件升级适用于运行时异常）
        plans[len(DEVICES) + 3] = CasePlan(
            device_id=DEVICES[3],
            scenario="mqtt_timeout",
            action="restart_device",
            parameters={},
            high_risk=True,
            query=DIAGNOSIS_QUERY["mqtt_timeout"],
        )
        plans[len(DEVICES) + 6] = CasePlan(
            device_id=DEVICES[6],
            scenario="unstable",
            action="update_firmware",
            parameters={"version": "1.3.1"},
            high_risk=True,
            query=DIAGNOSIS_QUERY["unstable"],
        )
        plans[len(DEVICES) + 9] = CasePlan(
            device_id=DEVICES[9],
            scenario="wifi_weak",
            action="restart_device",
            parameters={},
            high_risk=True,
            query=DIAGNOSIS_QUERY["wifi_weak"],
        )
    return plans


# 多样化模式：同一底层故障场景配以不同的现场症状叙述，
# 让诊断引擎产出不同的故障定名与根因分析，避免案例内容同质化。
VARIETY_PLANS: tuple[tuple[str, str, str, dict[str, Any], bool, str], ...] = (
    (
        "ESP32_01",
        "mqtt_timeout",
        "reconnect_mqtt",
        {},
        False,
        "设备每次建立 MQTT 连接后几秒内就断开，回执显示 broker 主动关闭连接，怀疑是 Broker 侧会话过期或重连风暴导致",
    ),
    (
        "ESP32_02",
        "mqtt_timeout",
        "restart_device",
        {},
        True,
        "MQTT 频繁报 authentication failed，连接被 Broker 拒绝，设备侧凭证可能配置错误导致反复重连失败",
    ),
    (
        "ESP32_03",
        "mqtt_timeout",
        "reconnect_mqtt",
        {},
        False,
        "设备上报数据持续丢包，publish 超时重试明显增多，网络往返延迟变大，疑似无线链路质量劣化拖垮了 MQTT 会话",
    ),
    (
        "ESP32_04",
        "wifi_weak",
        "reconnect_wifi",
        {},
        False,
        "设备所在车间新增大功率变频器后 WiFi 信道干扰加剧，信号强度尚可但误码率上升、吞吐下降，需要重选信道重连",
    ),
    (
        "ESP32_05",
        "wifi_weak",
        "restart_device",
        {},
        True,
        "设备部署在金属机柜内，WiFi 信号被屏蔽衰减，偶尔出现关联失败 assoc rejected，需复位射频模块重新扫描接入点",
    ),
    (
        "ESP32_06",
        "sensor_error",
        "calibrate_sensor",
        {},
        False,
        "温度读数相比相邻设备系统性偏高约 5 摄氏度，疑似 ADC 参考电压漂移或校准系数失效，需要执行零点重新标定",
    ),
    (
        "ESP32_07",
        "sensor_error",
        "restart_device",
        {},
        True,
        "温度读数间歇性跳变为异常值，其余时段正常，疑似接线端子氧化接触不良或电磁干扰造成采样毛刺，先重启设备观察",
    ),
    (
        "ESP32_08",
        "unstable",
        "reconnect_wifi",
        {},
        False,
        "设备夜间时段反复离线数分钟后自行恢复，白天正常，怀疑 AP 负载均衡或终端节能策略把设备踢下线，需重建关联",
    ),
    (
        "ESP32_09",
        "unstable",
        "update_firmware",
        {"version": "1.3.1"},
        True,
        "设备固件版本较旧，长时间运行后 WiFi 驱动疑似内存泄漏导致周期性掉线，建议升级到 1.3.1 修复版本",
    ),
    (
        "ESP32_10",
        "mqtt_timeout",
        "reconnect_mqtt",
        {},
        False,
        "设备跨 NAT 网关接入 MQTT，长时间空闲后连接静默失效，TCP 仍在但 PINGREQ 无响应，疑似 NAT 表项超时未续保",
    ),
    (
        "ESP32_11",
        "sensor_error",
        "calibrate_sensor",
        {},
        False,
        "温度传感器已连续使用三年以上，读数与标准温度计偏差逐年增大，老化漂移超出允许误差，需现场校准修正",
    ),
    (
        "ESP32_12",
        "unstable",
        "restart_device",
        {},
        True,
        "设备每日 DHCP 租约到期续约失败导致 IP 丢失断网数分钟后自动恢复，网络配置异常需复位网络栈观察",
    ),
    (
        "ESP32_02",
        "memory_leak",
        "restart_device",
        {},
        True,
        "设备长时间运行后越来越卡，日志里 free heap 持续下降并出现 out of memory 分配失败，疑似固件内存泄漏",
    ),
    (
        "ESP32_05",
        "memory_leak",
        "restart_device",
        {},
        True,
        "设备遥测上传正常但每日凌晨重启一次，串口日志记录 heap allocation failed，怀疑缓冲区未释放耗尽内存",
    ),
    (
        "ESP32_09",
        "memory_leak",
        "update_firmware",
        {"version": "1.3.1"},
        True,
        "设备运行 48 小时后响应迟缓，空闲堆从 180KB 降至 30KB 以下并触发 OOM，官方修复版本声称解决内存泄漏，建议升级",
    ),
    (
        "ESP32_03",
        "watchdog_reset",
        "restart_device",
        {},
        True,
        "设备每天多次自动重启，日志反复出现 Task watchdog got triggered 与 panic abort，复位后短时间内再次复现",
    ),
    (
        "ESP32_07",
        "watchdog_reset",
        "update_firmware",
        {"version": "1.3.1"},
        True,
        "设备看门狗反复超时复位，uptime 始终不超过十分钟，串口记录 uart_event 任务阻塞，疑似固件任务调度缺陷",
    ),
    (
        "ESP32_11",
        "watchdog_reset",
        "restart_device",
        {},
        True,
        "设备远程重启后数小时再次失联，日志显示看门狗触发任务阻塞转储，需要确认是软件死锁还是外部中断风暴",
    ),
)


def build_variety_plans() -> list[CasePlan]:
    return [
        CasePlan(
            device_id=device_id,
            scenario=scenario,
            action=action,
            parameters=parameters,
            high_risk=high_risk,
            query=query,
        )
        for device_id, scenario, action, parameters, high_risk, query in VARIETY_PLANS
    ]


class McpCaller:
    """持有单个 MCP 流式 HTTP 会话，顺序调用工具并解析统一信封。"""

    def __init__(self, name: str, url: str, token: str) -> None:
        self.name = name
        self.url = url
        self.token = token
        self._client = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "McpCaller":
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        self._client = create_mcp_http_client(headers=headers) if headers else None
        self._stack = streamable_http_client(self.url, http_client=self._client)
        read_stream, write_stream = await self._stack.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc_info)
        await self._stack.__aexit__(*exc_info)

    async def call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self._session is not None
        result = await self._session.call_tool(tool, arguments=arguments)
        envelope = getattr(result, "structured_content", None)
        if not isinstance(envelope, dict):
            envelope = json.loads(result.content[0].text)
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise RuntimeError(
                f"{self.name}.{tool} failed: {error.get('code')} {error.get('message')}"
            )
        return envelope["data"]


class FaultInjector:
    """经 MQTT 下行通道注入模拟故障。"""

    def __init__(self) -> None:
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="case-generator",
        )
        self.client.connect(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

    def inject(self, device_id: str, scenario: str) -> str:
        command_id = f"CMD_INJ_{uuid.uuid4().hex[:8].upper()}"
        payload = json.dumps(
            {
                "command_id": command_id,
                "action": "inject_fault",
                "parameters": {"scenario": scenario},
            },
            ensure_ascii=False,
        )
        info = self.client.publish(f"iot/{device_id}/cmd", payload, qos=1)
        info.wait_for_publish(timeout=10)
        return command_id

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


async def case_total(diagnosis: McpCaller) -> int:
    data = await diagnosis.call("list_fault_cases", {"limit": 1})
    return int(data["total"])


async def wait_for_archive(diagnosis: McpCaller, baseline: int, timeout: float) -> int | None:
    """等待修复完成事件异步归档为案例，返回最终总数；超时返回 None。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        total = await case_total(diagnosis)
        if total > baseline:
            return total
        await asyncio.sleep(3)
    return None


async def execute_and_verify(
    control: McpCaller, plan: CasePlan, diagnosis_id: str
) -> tuple[str, str]:
    """下发修复动作并轮询恢复验证结果；验证失败自动重试一次。"""
    reason = ACTION_REASON[plan.action]
    last_status = "unknown"
    for attempt in (1, 2):
        if plan.high_risk:
            proposal = await control.call(
                "create_remediation_proposal",
                {
                    "device_id": plan.device_id,
                    "action": plan.action,
                    "reason": reason,
                    "impact": "批量案例生成演练：设备短暂中断后自动恢复",
                    "parameters": plan.parameters,
                    "diagnosis_id": diagnosis_id,
                },
            )
            decided = await control.call(
                "decide_remediation_proposal",
                {
                    "proposal_id": proposal["proposal_id"],
                    "decision": "approved",
                    "decided_by": ISSUED_BY,
                    "expected_version": int(proposal["version"]),
                },
            )
            command = decided.get("command") or {}
        else:
            command = await control.call(
                "execute_device_action",
                {
                    "device_id": plan.device_id,
                    "action": plan.action,
                    "reason": reason,
                    "parameters": plan.parameters,
                    "issued_by": ISSUED_BY,
                    "diagnosis_id": diagnosis_id,
                },
            )
        command_id = command.get("command_id")
        if not command_id:
            raise RuntimeError(f"command_id missing in response: {command}")

        deadline = time.monotonic() + VERIFY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            result = await control.call("get_action_result", {"command_id": command_id})
            command = result.get("command") or {}
            verify_status = command.get("verify_status")
            status = command.get("status")
            if verify_status in ("succeeded", "failed") or status == "timeout":
                last_status = verify_status or status
                break
            await asyncio.sleep(5)
        else:
            last_status = "deadline"
        if last_status == "succeeded":
            return command_id, last_status
        print(
            f"    verify={last_status} (attempt {attempt})，重试或跳过",
            flush=True,
        )
    return command_id, last_status


async def run_case(
    diagnosis: McpCaller,
    control: McpCaller,
    injector: FaultInjector,
    plan: CasePlan,
    baseline: int,
    fault_wait: float,
) -> dict[str, Any]:
    injector.inject(plan.device_id, "normal")
    await asyncio.sleep(3)
    injector.inject(plan.device_id, plan.scenario)
    await asyncio.sleep(fault_wait)

    diagnosis_result = await diagnosis.call(
        "diagnose_fault",
        {
            "device_id": plan.device_id,
            "query": plan.diagnosis_query,
            "use_realtime_state": True,
        },
    )
    diagnosis_id = diagnosis_result["diagnosis_id"]

    command_id, verify_status = await execute_and_verify(control, plan, diagnosis_id)
    if verify_status != "succeeded":
        return {
            "device_id": plan.device_id,
            "scenario": plan.scenario,
            "action": plan.action,
            "mode": plan.mode,
            "diagnosis_id": diagnosis_id,
            "command_id": command_id,
            "verify_status": verify_status,
            "archived": False,
        }

    total = await wait_for_archive(diagnosis, baseline, ARCHIVE_TIMEOUT_SECONDS)
    return {
        "device_id": plan.device_id,
        "scenario": plan.scenario,
        "action": plan.action,
        "mode": plan.mode,
        "diagnosis_id": diagnosis_id,
        "command_id": command_id,
        "verify_status": verify_status,
        "archived": total is not None,
        "case_total": total,
    }


VERIFY_TIMEOUT_SECONDS = 150.0
ARCHIVE_TIMEOUT_SECONDS = 60.0


async def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-generate verified fault cases")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--fault-wait", type=float, default=14.0)
    parser.add_argument("--limit", type=int, default=None, help="仅执行前 N 条（冒烟验证用）")
    parser.add_argument(
        "--mode",
        choices=("standard", "variety"),
        default="standard",
        help="standard: 机群×场景矩阵；variety: 差异化症状叙述 × 多动作组合",
    )
    parser.add_argument("--start", type=int, default=0, help="跳过前 N 条计划（分批执行用）")
    args = parser.parse_args()

    plans = build_variety_plans() if args.mode == "variety" else build_plans(args.rounds)
    if args.start > 0:
        plans = plans[args.start :]
    if args.limit is not None:
        plans = plans[: args.limit]
    token = os.getenv("DIAGNOSIS_MCP_BEARER_TOKEN", "")
    injector = FaultInjector()
    results: list[dict[str, Any]] = []
    try:
        async with (
            McpCaller("diagnosis", DIAGNOSIS_URL, token) as diagnosis,
            McpCaller("control", CONTROL_URL, token) as control,
        ):
            baseline = await case_total(diagnosis)
            print(f"baseline cases: {baseline}, plan: {len(plans)} cases", flush=True)
            for index, plan in enumerate(plans, start=1):
                print(
                    f"[{index}/{len(plans)}] {plan.device_id} {plan.scenario} "
                    f"-> {plan.action} ({plan.mode})",
                    flush=True,
                )
                try:
                    outcome = await run_case(
                        diagnosis, control, injector, plan, baseline, args.fault_wait
                    )
                except Exception as exc:  # 单条失败不中断整批
                    print(f"    ERROR: {exc}", flush=True)
                    outcome = {
                        "device_id": plan.device_id,
                        "scenario": plan.scenario,
                        "action": plan.action,
                        "mode": plan.mode,
                        "error": str(exc),
                        "archived": False,
                    }
                results.append(outcome)
                baseline = outcome.get("case_total", baseline)
                print(f"    -> {json.dumps(outcome, ensure_ascii=False)}", flush=True)
            # 收尾：清除全部设备上的故障标志（unstable 等持久标志不在修复动作覆盖范围内）
            for device_id in DEVICES:
                injector.inject(device_id, "normal")
            print("cleanup: all devices restored to normal", flush=True)
    finally:
        injector.close()

    archived = sum(1 for item in results if item.get("archived"))
    summary = {
        "planned": len(plans),
        "archived": archived,
        "failed": len(results) - archived,
        "final_total": results[-1].get("case_total") if results else None,
    }
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
