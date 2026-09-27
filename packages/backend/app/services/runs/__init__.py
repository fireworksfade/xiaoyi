"""运行服务模块 - 保持向后兼容的公开接口。

重构后的模块结构:
- event_handler.py: 事件处理、缓冲和持久化
- tool_processor.py: 工具结果处理、提案收集
- orchestrator.py: 主编排逻辑 execute_claimed_run
"""

from app.agent.runtime import build_runtime

from .event_handler import append_event
from .orchestrator import (
    _record_hook_observations,
    _stream_with_context_recovery,
    execute_claimed_run,
    process_agent_run,
)
from .tool_processor import collect_proposal

# Backward compatibility aliases for tests
_collect_proposals = collect_proposal

__all__ = [
    "append_event",
    "build_runtime",
    "execute_claimed_run",
    "process_agent_run",
    "collect_proposal",
    "_collect_proposals",
    "_record_hook_observations",
    "_stream_with_context_recovery",
]
