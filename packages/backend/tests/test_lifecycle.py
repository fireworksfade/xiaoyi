import asyncio
from types import MappingProxyType

from app.agent.lifecycle import HookContext, HookObservation, LifecycleHooks


def test_lifecycle_hooks_preserve_order_and_isolate_timeout() -> None:
    hooks = LifecycleHooks(timeout_ms=5)

    async def first(_context: HookContext) -> HookObservation:
        return HookObservation("first", MappingProxyType({}))

    async def slow(_context: HookContext) -> None:
        await asyncio.sleep(0.05)

    async def last(_context: HookContext) -> HookObservation:
        return HookObservation("last", MappingProxyType({}))

    hooks.register("after_tool", "first", first)
    hooks.register("after_tool", "slow", slow)
    hooks.register("after_tool", "last", last)
    observations = asyncio.run(hooks.emit("after_tool", HookContext(run_id="run")))
    assert [item.name for item in observations] == ["first", "hook.failed", "last"]
    assert observations[1].data["hook"] == "slow"
