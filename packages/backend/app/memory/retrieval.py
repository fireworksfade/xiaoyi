import asyncio
import json
import re

from sqlalchemy import or_, select

from app.config import get_settings
from app.memory.models import Memory, MemoryRevision
from app.memory.schemas import MemorySearch
from app.memory.service import eligible
from app.services.token_estimator import DEFAULT_ESTIMATOR


def terms(text):
    words = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())
    return list(dict.fromkeys(words))[:40]


async def search(db, owner, query: MemorySearch):
    if not owner or not get_settings().memory_enabled:
        return []
    tokens = terms(query.query)
    if not tokens:
        return []
    vector_scores = {}
    mode = "keyword"
    try:
        from app.memory.indexing import vector_search
        vector_scores = await asyncio.wait_for(vector_search(owner, query), get_settings().memory_recall_timeout_ms / 1000)
        if vector_scores:
            mode = "hybrid"
    except (Exception, TimeoutError):
        pass
    rows = (await db.execute(select(Memory, MemoryRevision).join(MemoryRevision,
        (MemoryRevision.memory_id == Memory.id) & (MemoryRevision.revision == Memory.active_revision)).where(
        Memory.owner_user_id == owner, Memory.status == "active",
        or_(*[MemoryRevision.search_text.contains(token, autoescape=True) for token in tokens], Memory.id.in_(vector_scores)),
    ).order_by(Memory.updated_at.desc()).limit(30))).all()
    ranked = []
    for item, rev in rows:
        if not await eligible(db, item, rev.revision):
            continue
        scope = rev.applicability_json
        uncertain = []
        for field, actual in (("mcp_server_id", query.mcp_server_id), ("device_types", query.device_type), ("device_ids", query.device_id)):
            expected = scope.get(field)
            if not expected:
                continue
            if actual is None:
                uncertain.append("适用性待核实: " + field)
            elif actual not in (expected if isinstance(expected, list) else [expected]):
                break
        else:
            score = sum(token in rev.search_text.lower() for token in tokens) / len(tokens) + vector_scores.get(item.id, 0)
            if score > 0:
                ranked.append((score, item, rev, uncertain))
    ranked.sort(key=lambda row: row[0], reverse=True)
    result, counts, signatures = [], {"experience": 0, "episodic": 0}, set()
    budget = min(2000, get_settings().memory_context_max_tokens)
    for _, item, rev, uncertain in ranked:
        if counts[item.kind] >= (4 if item.kind == "experience" else 2):
            continue
        signature = (item.kind, rev.summary, json.dumps(rev.applicability_json, sort_keys=True))
        if signature in signatures:
            continue
        # Preserve the whole summary/conditions. Omit oversized entries instead of cutting qualifiers.
        entry = {"memory_id": item.id, "revision": rev.revision, "kind": item.kind, "title": rev.title,
            "excerpt": rev.summary, "applicability": rev.applicability_json,
            "uncertainty": uncertain + ["历史参考不证明当前根因"], "retrieval_mode": mode}
        cost = DEFAULT_ESTIMATOR.estimate_text(json.dumps(entry, ensure_ascii=False))
        if cost > min(450, budget):
            continue
        result.append(entry)
        counts[item.kind] += 1
        signatures.add(signature)
        budget -= cost
        if len(result) >= query.top_k:
            break
    if result:
        from app.memory.service import record_usage
        await record_usage(db, owner, result, run_id=query.run_id, stage="retrieved")
    return result
