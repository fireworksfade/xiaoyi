from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.common import envelope
from app.api.deps import CsrfProtected, CurrentUser, Db
from app.memory import service
from app.memory.models import Memory, MemoryJob, MemoryRevision
from app.memory.schemas import ForgetSource, MemorySearch, MemoryWrite, RevisionAction

router = APIRouter(prefix="/memories", tags=["memory"])


@router.get("")
async def list_memories(request: Request, db: Db, user: CurrentUser, kind: str | None = None,
    status: str | None = None, q: str | None = None, source: str | None = None,
    cursor: str | None = None, limit: int = Query(30, ge=1, le=100)):
    query = select(Memory).where(Memory.owner_user_id == user.id, Memory.status != "deleted")
    if kind:
        query = query.where(Memory.kind == kind)
    if status:
        query = query.where(Memory.status == status)
    if source:
        query = query.where(Memory.source_type == source)
    if q:
        query = query.where(Memory.title.contains(q, autoescape=True))
    if cursor:
        query = query.where(Memory.id > cursor)
    items = list((await db.scalars(query.order_by(Memory.id).limit(limit + 1))).all())
    return envelope(request, {"items": [await service.view(db, item) for item in items[:limit]],
        "next_cursor": items[limit - 1].id if len(items) > limit else None})


@router.post("", status_code=201)
async def create_memory(payload: MemoryWrite, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    item = await service.create(db, user.id, payload)
    await db.commit()
    return envelope(request, await service.view(db, item))


@router.post("/search")
async def search_memories(payload: MemorySearch, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    from app.memory.retrieval import search
    return envelope(request, {"items": await search(db, user.id, payload)})


@router.get("/activity")
async def activity(request: Request, db: Db, user: CurrentUser):
    jobs = (await db.scalars(select(MemoryJob).where(MemoryJob.owner_user_id == user.id).order_by(MemoryJob.created_at.desc()).limit(50))).all()
    candidates = (await db.scalars(select(Memory.id).where(Memory.owner_user_id == user.id,
        (Memory.status == "candidate") | ((Memory.status == "active") & (Memory.current_revision != Memory.active_revision))))).all()
    return envelope(request, {"candidate_count": len(candidates), "items": [{"id": j.id,
        "kind": j.kind, "status": j.status, "error_code": j.error_code, "attempts": j.attempts,
        "created_at": j.created_at.isoformat()} for j in jobs]})


@router.get("/forget-impact")
async def forget_impact(conversation_id: str, request: Request, db: Db, user: CurrentUser):
    _, items = await service.source_impact(db, user.id, conversation_id)
    return envelope(request, {"episodic": sum(i.kind == "episodic" for i in items),
        "experience": sum(i.kind == "experience" for i in items), "total": len(items)})


@router.post("/forget-source")
async def forget_source(payload: ForgetSource, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    result = await service.forget_source(db, user.id, payload.conversation_id)
    await db.commit()
    return envelope(request, result)


@router.get("/{memory_id}")
async def get_memory(memory_id: str, request: Request, db: Db, user: CurrentUser):
    return envelope(request, await service.view(db, await service.owned(db, user.id, memory_id)))


@router.patch("/{memory_id}")
async def edit_memory(memory_id: str, payload: MemoryWrite, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    item = await service.edit(db, user.id, memory_id, payload)
    await db.commit()
    return envelope(request, await service.view(db, item))


@router.get("/{memory_id}/revisions")
async def revisions(memory_id: str, request: Request, db: Db, user: CurrentUser):
    await service.owned(db, user.id, memory_id)
    rows = (await db.scalars(select(MemoryRevision).where(MemoryRevision.memory_id == memory_id).order_by(MemoryRevision.revision.desc()))).all()
    return envelope(request, {"items": [{"revision": r.revision, "title": r.title, "summary": r.summary,
        "content": r.content_json, "applicability": r.applicability_json, "review_state": r.review_state,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None} for r in rows]})


def action_endpoint(action):
    async def endpoint(memory_id: str, payload: RevisionAction, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
        item = await service.transition(db, user.id, memory_id, payload.expected_revision, action)
        await db.commit()
        return envelope(request, await service.view(db, item))
    return endpoint


for action in ("confirm", "reject", "suspend", "archive"):
    router.add_api_route("/{memory_id}/" + action, action_endpoint(action), methods=["POST"], name="memory_" + action)


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, request: Request, db: Db, user: CurrentUser, _: CsrfProtected):
    item = await service.owned(db, user.id, memory_id, include_deleted=True)
    await service.transition(db, user.id, memory_id, item.current_revision, "delete")
    await db.commit()
    return envelope(request, {"deleted": True, "index_status": "pending"})
