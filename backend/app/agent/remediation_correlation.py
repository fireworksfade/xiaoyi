from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DIAGNOSIS_TOOL = "diagnose_fault"
REMEDIATION_TOOLS = {"execute_device_action", "create_remediation_proposal"}


class RemediationCorrelationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class RemediationCorrelationState:
    """可信的 Run 内诊断关联状态。

    状态只从 diagnose_fault 的成功工具输出写入；模型不能自行创建或覆盖。
    按设备保存可兼容同一个 Agent Run 中依次诊断多台设备的情况。
    """

    diagnosis_by_device: dict[str, str] = field(default_factory=dict)

    def begin_tool_call(self, tool_name: str, arguments: dict[str, Any] | None) -> None:
        if tool_name != DIAGNOSIS_TOOL or not isinstance(arguments, dict):
            return
        device_id = arguments.get("device_id")
        if isinstance(device_id, str) and device_id:
            # 新诊断开始时先清除该设备的旧关联，失败时不能误用旧 diagnosis_id。
            self.diagnosis_by_device.pop(device_id, None)

    def record_tool_result(self, tool_name: str, output: object) -> None:
        if tool_name != DIAGNOSIS_TOOL or not isinstance(output, dict):
            return
        if output.get("ok") is not True:
            return
        data = output.get("data")
        if not isinstance(data, dict):
            return
        diagnosis_id = data.get("diagnosis_id")
        device_id = data.get("device_id")
        if (
            isinstance(diagnosis_id, str)
            and diagnosis_id
            and isinstance(device_id, str)
            and device_id
        ):
            self.diagnosis_by_device[device_id] = diagnosis_id

    def prepare_arguments(
        self, tool_name: str, arguments: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if tool_name not in REMEDIATION_TOOLS:
            return arguments
        prepared = dict(arguments or {})
        device_id = prepared.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            raise RemediationCorrelationError(
                "DEVICE_ID_REQUIRED", "修复动作必须指定本轮已诊断的设备"
            )
        trusted_id = self.diagnosis_by_device.get(device_id)
        if trusted_id is None:
            raise RemediationCorrelationError(
                "DIAGNOSIS_REQUIRED",
                f"设备 {device_id} 在当前运行中尚无成功诊断，不能执行修复",
            )
        supplied_id = prepared.get("diagnosis_id")
        if supplied_id not in (None, "", trusted_id):
            raise RemediationCorrelationError(
                "DIAGNOSIS_CONTEXT_MISMATCH",
                "修复参数中的 diagnosis_id 与当前运行的真实诊断结果不一致",
            )
        # 即使模型漏传也由可信运行时注入；模型无法覆盖真实关联。
        prepared["diagnosis_id"] = trusted_id
        return prepared
