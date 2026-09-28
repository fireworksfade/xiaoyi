"""Transactional lifecycle and provenance. Callers own commit/rollback."""
import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select, update

from app.config import get_settings
from app.memory.models import (
    Memory,
    MemoryEvidenceLink,
    MemoryIndexState,
    MemoryJob,
    MemoryRevision,
    MemorySource,
    MemoryTombstone,
    MemoryVectorOutbox,
    WorkingMemory,
)
from app.memory.schemas import MemoryWrite
from app.models import Conversation, utc_now
from app.services.artifacts import sanitize_artifact


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def fail(code, status=422):
    raise HTTPException(status_code=status, detail=code)


async def owned(db, owner, memory_id, *, include_deleted=False):
    item = await db.scalar(select(Memory).where(Memory.id == memory_id, Memory.owner_user_id == owner))
    if not item or (item.status == "deleted" and not include_deleted):
        fail("MEMORY_NOT_FOUND", 404)
    return item


async def revision(db, item, number=None):
    return await db.scalar(select(MemoryRevision).where(
        MemoryRevision.memory_id == item.id,
        MemoryRevision.revision == (number or item.current_revision),
    ))


async def tombstoned(db, owner, scope, target):
    return bool(await db.scalar(select(MemoryTombstone.id).where(
        MemoryTombstone.owner_user_id == owner, MemoryTombstone.scope == scope,
        MemoryTombstone.target_id == target,
    )))


async def tombstone(db, owner, scope, target, content_hash=None):
    if not await tombstoned(db, owner, scope, target):
        db.add(MemoryTombstone(owner_user_id=owner, scope=scope, target_id=target, content_hash=content_hash))
        await db.flush()


async def enqueue(db, owner, kind, key, payload):
    existing = await db.scalar(select(MemoryJob).where(MemoryJob.owner_user_id == owner, MemoryJob.job_key == key))
    if existing:
        return existing
    item = MemoryJob(owner_user_id=owner, kind=kind, job_key=key, payload=payload)
    db.add(item)
    await db.flush()
    return item


async def index_change(db, item, operation="upsert"):
    settings = get_settings()
    entry = MemoryVectorOutbox(
        owner_user_id=item.owner_user_id, memory_id=item.id,
        revision=item.active_revision or item.current_revision, operation=operation,
        model_fingerprint=settings.memory_embedding_fingerprint,
        collection=f"{settings.memory_collection_prefix}_{settings.memory_embedding_fingerprint}_{settings.memory_embedding_dimensions}_v1",
    )
    db.add(entry)
    await db.flush()
    await enqueue(db, item.owner_user_id, "sync_vector", f"index:{entry.id}", {"outbox_id": entry.id})


async def eligible(db, item, number=None, visited=None):
    """Revalidate transitively in SQL even while asynchronous cleanup is outstanding."""
    if item.status != "active" or not item.active_revision or item.deleted_at:
        return False
    if item.expires_at and item.expires_at.replace(tzinfo=utc_now().tzinfo) <= utc_now():
        return False
    if number is not None and number != item.active_revision:
        return False
    if await tombstoned(db, item.owner_user_id, "memory", item.id):
        return False
    visited = set(visited or ())
    if item.id in visited:
        return False
    visited.add(item.id)
    rev = await revision(db, item, item.active_revision)
    if not rev or (item.kind == "episodic" and rev.content_json.get("outcome") == "pending"):
        return False
    links = (await db.scalars(select(MemoryEvidenceLink).where(
        MemoryEvidenceLink.owner_user_id == item.owner_user_id,
        MemoryEvidenceLink.memory_id == item.id,
        MemoryEvidenceLink.revision == item.active_revision,
    ))).all()
    for link in links:
        if link.source_id:
            source = await db.get(MemorySource, link.source_id)
            if not source or source.owner_user_id != item.owner_user_id or source.access_state == "forgotten":
                return False
            if source.conversation_id and await tombstoned(db, item.owner_user_id, "conversation", source.conversation_id):
                return False
        if link.episode_id:
            episode = await db.get(Memory, link.episode_id)
            if not episode or episode.owner_user_id != item.owner_user_id or not await eligible(db, episode, link.episode_revision, visited):
                return False
    return True


async def create(db, owner, payload: MemoryWrite, *, source_type="user", event_key=None, source=None, episode=None):
    if event_key:
        if await tombstoned(db, owner, "event", event_key):
            return None
        existing = await db.scalar(select(Memory).where(Memory.owner_user_id == owner, Memory.event_key == event_key))
        if existing:
            return existing
    if source and source.conversation_id and await tombstoned(db, owner, "conversation", source.conversation_id):
        return None
    item = Memory(owner_user_id=owner, kind=payload.kind, title=payload.title.strip(), source_type=source_type, event_key=event_key)
    db.add(item)
    await db.flush()
    rev = make_revision(item, owner, payload, 1)
    db.add(rev)
    await db.flush()
    if source:
        db.add(MemoryEvidenceLink(owner_user_id=owner, memory_id=item.id, revision=1, source_id=source.id))
    if episode:
        db.add(MemoryEvidenceLink(owner_user_id=owner, memory_id=item.id, revision=1, episode_id=episode.id, episode_revision=episode.current_revision))
    if payload.confirm:
        await transition(db, owner, item.id, 1, "confirm")
    return item


def make_revision(item, owner, payload, number):
    content = sanitize_artifact(payload.content)
    applicability = sanitize_artifact(payload.applicability)
    summary = sanitize_artifact({"summary": payload.summary})["summary"]
    data = {"title": payload.title, "summary": summary, "content": content, "applicability": applicability}
    return MemoryRevision(
        memory_id=item.id, revision=number, title=payload.title, summary=summary,
        content_json=content, applicability_json=applicability,
        search_text=json.dumps(data, ensure_ascii=False), content_hash=digest(data),
        change_reason=payload.change_reason, created_by=owner,
    )


async def edit(db, owner, memory_id, payload):
    item = await owned(db, owner, memory_id)
    expected = payload.expected_revision
    if expected is None or expected != item.current_revision:
        fail("MEMORY_VERSION_CONFLICT", 409)
    if item.kind != payload.kind or item.status in {"archived", "rejected"}:
        fail("MEMORY_INVALID_TRANSITION")
    result = await db.execute(update(Memory).where(
        Memory.id == item.id, Memory.owner_user_id == owner, Memory.current_revision == expected,
    ).values(current_revision=expected + 1, title=payload.title, updated_at=utc_now()))
    if result.rowcount != 1:
        fail("MEMORY_VERSION_CONFLICT", 409)
    db.add(make_revision(item, owner, payload, expected + 1))
    links = (await db.scalars(select(MemoryEvidenceLink).where(MemoryEvidenceLink.memory_id == item.id, MemoryEvidenceLink.revision == expected))).all()
    for link in links:
        db.add(MemoryEvidenceLink(owner_user_id=owner, memory_id=item.id, revision=expected + 1,
            source_id=link.source_id, episode_id=link.episode_id, episode_revision=link.episode_revision, relation=link.relation))
    await db.flush()
    await db.refresh(item)
    if payload.confirm:
        await transition(db, owner, item.id, item.current_revision, "confirm")
    return item


async def transition(db, owner, memory_id, expected, action):
    item = await owned(db, owner, memory_id, include_deleted=action == "delete")
    if action == "delete" and item.status == "deleted":
        return item
    if expected != item.current_revision:
        fail("MEMORY_VERSION_CONFLICT", 409)
    rev = await revision(db, item)
    allowed = {"confirm": {"candidate", "active", "suspended"}, "reject": {"candidate", "active", "suspended"},
        "suspend": {"active"}, "archive": {"active", "candidate", "suspended", "rejected"},
        "delete": {"candidate", "active", "suspended", "rejected", "archived"}}
    if item.status not in allowed[action]:
        fail("MEMORY_INVALID_TRANSITION")
    result = await db.execute(update(Memory).where(Memory.id == item.id, Memory.current_revision == expected, Memory.status == item.status).values(updated_at=utc_now()))
    if result.rowcount != 1:
        fail("MEMORY_VERSION_CONFLICT", 409)
    if action == "confirm":
        if rev.review_state == "rejected":
            fail("MEMORY_INVALID_TRANSITION")
        links = (await db.scalars(select(MemoryEvidenceLink).where(MemoryEvidenceLink.memory_id == item.id, MemoryEvidenceLink.revision == expected))).all()
        for link in links:
            if link.source_id:
                source = await db.get(MemorySource, link.source_id)
                if source and source.access_state == "forgotten":
                    fail("MEMORY_SOURCE_UNAVAILABLE")
            if link.episode_id:
                episode = await db.get(Memory, link.episode_id)
                if not episode or not await eligible(db, episode, link.episode_revision):
                    fail("MEMORY_SOURCE_UNAVAILABLE")
        item.status, item.active_revision = "active", expected
        rev.review_state, rev.reviewed_by, rev.reviewed_at = "confirmed", owner, utc_now()
    elif action == "reject":
        if item.active_revision == expected:
            fail("MEMORY_INVALID_TRANSITION")
        rev.review_state = "rejected"
        if item.active_revision is None:
            item.status = "rejected"
    else:
        item.status = {"suspend": "suspended", "archive": "archived", "delete": "deleted"}[action]
        if action == "delete":
            item.deleted_at = utc_now()
            await tombstone(db, owner, "memory", item.id, rev.content_hash)
            if item.event_key:
                await tombstone(db, owner, "event", item.event_key)
            await enqueue(db, owner, "revalidate_dependents", f"delete:{item.id}", {"memory_id": item.id})
    await db.flush()
    await index_change(db, item, "upsert" if item.status == "active" else "purge")
    return item


async def view(db, item):
    rev = await revision(db, item)
    sources = (await db.scalars(select(MemorySource).join(MemoryEvidenceLink, MemoryEvidenceLink.source_id == MemorySource.id).where(
        MemoryEvidenceLink.memory_id == item.id, MemoryEvidenceLink.revision == item.current_revision,
        MemorySource.owner_user_id == item.owner_user_id,
    ))).all()
    index = await db.scalar(select(MemoryIndexState).where(MemoryIndexState.memory_id == item.id, MemoryIndexState.revision == (item.active_revision or item.current_revision)))
    return {"id": item.id, "kind": item.kind, "status": item.status, "title": item.title,
        "current_revision": item.current_revision, "active_revision": item.active_revision,
        "summary": rev.summary, "content": rev.content_json, "applicability": rev.applicability_json,
        "review_state": rev.review_state, "source_type": item.source_type,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
        "index_status": index.status if index else "excluded" if not await eligible(db, item) else "pending",
        "sources": [{"id": s.id, "source_type": s.source_type, "run_id": s.run_id,
            "conversation_id": s.conversation_id, "diagnosis_id": s.diagnosis_id,
            "command_id": s.command_id, "mcp_server_id": s.mcp_server_id,
            "access_state": s.access_state, "excerpt": {} if s.access_state == "forgotten" else s.excerpt,
            "content_hash": s.content_hash} for s in sources]}


async def source_impact(db, owner, conversation_id):
    conversation = await db.get(Conversation, conversation_id)
    sources = (await db.scalars(select(MemorySource).where(MemorySource.owner_user_id == owner, MemorySource.conversation_id == conversation_id))).all()
    if (not conversation or conversation.user_id != owner) and not sources:
        fail("MEMORY_SOURCE_UNAVAILABLE", 404)
    source_ids = [s.id for s in sources]
    links = (await db.scalars(select(MemoryEvidenceLink).where(MemoryEvidenceLink.owner_user_id == owner))).all()
    affected = {link.memory_id for link in links if link.source_id in source_ids}
    while True:
        expanded = affected | {link.memory_id for link in links if link.episode_id in affected}
        if expanded == affected:
            break
        affected = expanded
    items = (await db.scalars(select(Memory).where(Memory.owner_user_id == owner, Memory.id.in_(affected), Memory.status != "deleted"))).all()
    return sources, items


async def forget_source(db, owner, conversation_id):
    sources, items = await source_impact(db, owner, conversation_id)
    await tombstone(db, owner, "conversation", conversation_id)
    for source in sources:
        source.access_state, source.excerpt = "forgotten", {}
    for item in items:
        if item.kind == "episodic":
            await transition(db, owner, item.id, item.current_revision, "delete")
        else:
            item.status = "suspended"
            await index_change(db, item, "purge")
    job = await enqueue(db, owner, "revalidate_dependents", f"forget:{conversation_id}", {"conversation_id": conversation_id})
    await db.execute(delete(WorkingMemory).where(WorkingMemory.owner_user_id == owner, WorkingMemory.conversation_id == conversation_id))
    return {"affected_count": len(items), "job_id": job.id}


async def run_finished(db, run):
    if get_settings().memory_enabled and get_settings().memory_auto_capture:
        await enqueue(db, run.user_id, "capture_episode", f"run:{run.id}", {"run_id": run.id})


async def working_fact(db, run, key, fact):
    item = await db.scalar(select(WorkingMemory).where(WorkingMemory.owner_user_id == run.user_id, WorkingMemory.conversation_id == run.conversation_id))
    if not item:
        item = WorkingMemory(owner_user_id=run.user_id, conversation_id=run.conversation_id, run_id=run.id, facts={})
        db.add(item)
    item.run_id = run.id
    item.facts = {**item.facts, key: sanitize_artifact(fact)}
    item.version = (item.version or 0) + 1
    item.expires_at = utc_now() + timedelta(hours=get_settings().memory_working_ttl_hours)
