"""后端原生记忆工具（spec 10.2）。

只读的 search_memory/get_memory 自动绑定当前 Run 用户；propose_memory 只能
创建候选，不能设置 confirmed 状态，也不能指定 owner 或触碰确认接口。
工具在 OpenAIAgentsRuntime 内通过 FunctionTool 工厂接入；处理器独立成函数，
便于在不依赖 agents SDK 的测试中直接验证行为。
"""
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionFactory
from app.memory.models import MemorySource
from app.memory.retrieval import search
from app.memory.schemas import MemorySearch, MemoryWrite
from app.memory.service import create, digest, owned, tombstoned, view
from app.models import AgentRun

MEMORY_TOOL_SPECS = [
    {
        "name": "search_memory",
        "description": "在当前用户自己的历史记忆中检索（只读，自动绑定当前用户，不能跨用户）。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或问题描述"},
                "device_id": {"type": "string", "description": "可选，设备 ID"},
                "device_type": {"type": "string", "description": "可选，设备类型"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_memory",
        "description": "查看当前用户某条记忆的正文、版本与来源摘要（只读）。",
        "parameters": {
            "type": "object",
            "properties": {"memory_id": {"type": "string"}},
            "required": ["memory_id"],
        },
    },
    {
        "name": "propose_memory",
        "description": "提议一条经验记忆候选，仅进入待确认队列，用户确认前不会用于召回。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "content": {
                    "type": "object",
                    "description": "经验内容：claims（事实/假设）、procedure（步骤）、limitations（限制）",
                },
                "applicability": {"type": "object", "description": "适用条件：mcp_server_id/device_ids 等"},
            },
            "required": ["title", "summary", "content"],
        },
    },
]


async def _run_context(run_id):
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if not run:
            return None
        return run.user_id, run.conversation_id


async def handle_memory_tool(run_id, name, arguments):
    arguments = arguments or {}
    context = await _run_context(run_id) if run_id else None
    if not context:
        return {"error": "RUN_NOT_FOUND"}
    owner, conversation_id = context
    if name == "search_memory":
        query = str(arguments.get("query") or "").strip()
        if not query:
            return {"error": "MEMORY_INVALID_CONTENT"}
        async with SessionFactory() as db:
            items = await search(db, owner, MemorySearch(query=query[:2000],
                device_id=arguments.get("device_id"), device_type=arguments.get("device_type"), run_id=run_id))
            await db.commit()
        return {"items": items}
    if name == "get_memory":
        async with SessionFactory() as db:
            try:
                item = await owned(db, owner, str(arguments.get("memory_id") or ""))
                result = await view(db, item)
            except HTTPException as exc:
                return {"error": exc.detail}
        return {"item": result}
    if name == "propose_memory":
        return await _propose(owner, conversation_id, run_id, arguments)
    return {"error": "MEMORY_TOOL_UNKNOWN"}


async def _propose(owner, conversation_id, run_id, arguments):
    async with SessionFactory() as db:
        if await tombstoned(db, owner, "conversation", conversation_id):
            return {"error": "MEMORY_SOURCE_UNAVAILABLE"}
        source = await db.scalar(select(MemorySource).where(
            MemorySource.owner_user_id == owner, MemorySource.source_key == f"agent:{run_id}"))
        if not source:
            source = MemorySource(owner_user_id=owner, source_key=f"agent:{run_id}", source_type="agent",
                source_id=run_id, run_id=run_id, conversation_id=conversation_id,
                excerpt={"note": "模型在任务中提议的记忆候选"}, content_hash=digest(arguments))
            db.add(source)
            await db.flush()
        content = dict(arguments.get("content") or {})
        # 模型只能提出假设，且证据引用绑定本次任务来源，不能自称已观察/已验证。
        content["claims"] = [{"text": str(claim.get("text") or "")[:500], "epistemic_status": "hypothesis",
            "evidence_refs": [source.id]} for claim in content.get("claims", []) if isinstance(claim, dict)]
        try:
            payload = MemoryWrite(kind="experience", title=str(arguments.get("title") or "")[:160],
                summary=str(arguments.get("summary") or "")[:1200], content=content,
                applicability=dict(arguments.get("applicability") or {}))
        except ValidationError as exc:
            code = next((e["type"] for e in exc.errors() if str(e["type"]).startswith("MEMORY_")), None)
            return {"error": code or "MEMORY_INVALID_CONTENT"}
        item = await create(db, owner, payload, source_type="task",
            event_key=f"propose:{digest([payload.title, payload.summary, payload.content])}", source=source)
        await db.commit()
        if not item:
            return {"deduplicated": True, "status": "exists"}
        return {"id": item.id, "status": item.status, "revision": item.current_revision,
            "note": "候选待用户确认；确认前不会进入正常召回"}


def build_memory_tools(run_id, make_tool):
    """make_tool(name, description, parameters, handler) -> tool 对象；供 runtime 注入 SDK 工厂。
    run_id 为当前 Run，工具在调用时由服务端解析 owner，模型不能指定。"""
    if not get_settings().memory_enabled or not run_id:
        return []

    async def invoke(name, raw_input):
        try:
            arguments = json.loads(raw_input or "{}")
        except json.JSONDecodeError:
            arguments = {}
        try:
            return json.dumps(await handle_memory_tool(run_id, name, arguments if isinstance(arguments, dict) else {}), ensure_ascii=False)
        except Exception as exc:  # 工具失败不拖垮整个 Run
            return json.dumps({"error": "MEMORY_TOOL_FAILED", "message": str(exc)[:200]}, ensure_ascii=False)

    tools = []
    for spec in MEMORY_TOOL_SPECS:
        tools.append(make_tool(spec["name"], spec["description"], spec["parameters"],
            lambda raw, _name=spec["name"]: invoke(_name, raw)))
    return tools
