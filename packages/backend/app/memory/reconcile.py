"""反例处理：采用经验明确失败时暂停并生成待确认修订（spec 6.3/7.6）。"""

from app.db import SessionFactory
from app.memory.models import Memory, MemoryActionLink
from app.memory.schemas import MemoryWrite
from app.memory.service import edit, index_change, revision


async def reconcile(job):
    async with SessionFactory() as db:
        memory = await db.get(Memory, job.payload["memory_id"])
        link = await db.get(MemoryActionLink, job.payload["link_id"])
        if (
            not memory
            or not link
            or memory.owner_user_id != job.owner_user_id
            or link.owner_user_id != job.owner_user_id
        ):
            return
        if memory.status in {"deleted", "archived", "rejected"}:
            return
        if not job.payload.get("scope_matched"):
            # 适用范围与失败动作不一致：只记范围问题（反馈已落库），不暂停经验。
            return
        # A late counterexample to an old version must not pause a newly reviewed version.
        used_revision = job.payload.get(
            "revision", memory.active_revision or memory.current_revision
        )
        if memory.active_revision and memory.active_revision != used_revision:
            return
        # 明确反例：立即暂停（召回即排除），生成待确认修订；不自动覆盖反例。
        memory.status = "suspended"
        await index_change(db, memory, "purge")
        rev = await revision(db, memory, used_revision)
        if not rev or not rev.content_json:
            return
        reason = f"反例冲突（命令 {link.command_id}），暂停并生成待确认修订"
        from sqlalchemy import select

        from app.memory.models import MemoryRevision

        if await db.scalar(
            select(MemoryRevision.id).where(
                MemoryRevision.memory_id == memory.id, MemoryRevision.change_reason == reason
            )
        ):
            return
        content = dict(rev.content_json or {})
        limitations = list(content.get("limitations") or [])
        device = (link.arguments or {}).get("device_id")
        limitations.append(
            {
                "text": f"反例：命令 {link.command_id} 在 {device or '该设备'} 上执行后仍失败，需人工复核适用条件。"
            }
        )
        content["limitations"] = limitations
        payload = MemoryWrite(
            kind="experience",
            title=rev.title,
            summary=rev.summary,
            content=content,
            applicability=rev.applicability_json,
            expected_revision=memory.current_revision,
            change_reason=reason,
        )
        await edit(db, memory.owner_user_id, memory.id, payload)
        await db.commit()
