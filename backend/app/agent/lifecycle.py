"""Small, static and observation-only agent lifecycle hooks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping


@dataclass(frozen=True, slots=True)
class HookContext:
    run_id: str
    workflow_id: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    request_id: str | None = None
    event_type: str | None = None
    tool_name: str | None = None
    server_name: str | None = None
    call_id: str | None = None
    sanitized_input_summary: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    sanitized_output_summary: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    timestamps: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class HookObservation:
    name: str
    data: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


Hook = Callable[[HookContext], Awaitable[HookObservation | None]]


class LifecycleHooks:
    POINTS = ("before_run", "after_tool", "after_gate", "after_run", "on_error")

    def __init__(self, timeout_ms: int = 500) -> None:
        self.timeout_seconds = max(timeout_ms, 1) / 1000
        self._hooks: dict[str, list[tuple[str, Hook]]] = {point: [] for point in self.POINTS}

    def register(self, point: str, name: str, hook: Hook) -> None:
        if point not in self._hooks:
            raise ValueError(f"unknown hook point: {point}")
        self._hooks[point].append((name, hook))

    def set_timeout_ms(self, timeout_ms: int) -> None:
        self.timeout_seconds = max(timeout_ms, 1) / 1000

    async def emit(self, point: str, context: HookContext) -> list[HookObservation]:
        if point not in self._hooks:
            raise ValueError(f"unknown hook point: {point}")
        observations: list[HookObservation] = []
        for name, hook in self._hooks[point]:
            try:
                observation = await asyncio.wait_for(hook(context), self.timeout_seconds)
                if observation is not None:
                    observations.append(observation)
            except Exception as exc:
                observations.append(
                    HookObservation(
                        "hook.failed", MappingProxyType({"hook": name, "error": type(exc).__name__})
                    )
                )
        return observations


DEFAULT_HOOKS = LifecycleHooks()
