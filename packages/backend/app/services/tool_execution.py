"""Shared tool execution for platform chat tool calls."""

from app.agent.remediation_correlation import RemediationCorrelationState
from app.memory.boundary import finish, prepare, rediagnose


class ToolPreparationError(Exception):
    """Preparation failed before the remote tool was called."""

    def __init__(self, cause):
        super().__init__(str(cause))
        self.cause = cause


class ToolExecutor:
    def __init__(self, run_id, server_id, correlation=None):
        self.run_id = run_id
        self.server_id = server_id
        self.correlation = correlation if correlation is not None else RemediationCorrelationState()

    def prepare_arguments(self, tool_name, arguments, *, issued_by=None):
        self.correlation.begin_tool_call(tool_name, arguments)
        prepared = self.correlation.prepare_arguments(tool_name, arguments)
        if issued_by is not None:
            prepared = dict(prepared or {})
            prepared.pop("issued_by", None)
            if tool_name == "execute_device_action":
                prepared["issued_by"] = issued_by
        return prepared

    def record_result(self, tool_name, output):
        self.correlation.record_tool_result(tool_name, output)
        diagnosis = output.get("rediagnosis") if isinstance(output, dict) else None
        if diagnosis:
            self.correlation.record_tool_result(
                "diagnose_fault", {"ok": True, "data": diagnosis["diagnosis"]}
            )

    def restore(self, events):
        for event in events:
            if event.data.get("server_id") != self.server_id:
                continue
            name = event.data.get("tool_name")
            if event.event_type == "tool.started":
                self.correlation.begin_tool_call(name, event.data.get("arguments"))
            elif event.event_type == "tool.finished":
                self.record_result(name, event.data.get("output"))

    async def execute(self, tool_name, arguments, call, *, internal_call=None):
        """Callbacks own transport and authorization; results expose structured_content."""
        action_link = None
        if self.run_id:
            try:
                arguments, action_link = await prepare(
                    self.run_id, self.server_id, tool_name, arguments
                )
            except Exception as exc:
                raise ToolPreparationError(exc) from exc
        result = await call(tool_name, arguments)
        output = result.structured_content
        if self.run_id and isinstance(output, dict):
            link = await finish(
                self.run_id, self.server_id, tool_name, arguments, output, action_link
            )
            if link:
                diagnosis = await rediagnose(
                    self.run_id, self.server_id, link.id, internal_call or call
                )
                if diagnosis:
                    result.structured_content = {**output, "rediagnosis": diagnosis}
        self.record_result(tool_name, result.structured_content)
        return result
