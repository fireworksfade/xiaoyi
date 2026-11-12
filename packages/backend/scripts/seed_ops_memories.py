"""Load the curated ops memories (seed/ops_memories.json) for one user.

Episodes record real reproductions on the QEMU fleet (command and diagnosis IDs are kept as
evidence); experiences generalise them and link back to their episodes. Every memory goes
through the normal memory service, so validation, revisions, confirmation and vector
indexing behave exactly as for memories created in the UI.

Re-running is safe: each memory has a stable event key. Unchanged memories are left alone; an
experience whose seed entry changed gets a new revision (and is confirmed when the entry says so).

  python -m scripts.seed_ops_memories --username admin
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionFactory
from app.memory.models import Memory, MemoryEvidenceLink
from app.memory.schemas import MemoryWrite
from app.memory.service import create, edit, make_revision, revision, transition
from app.models import MCPServer, User

SEED_FILE = Path(__file__).resolve().parents[1] / "seed" / "ops_memories.json"
EVENT_PREFIX = "ops-seed:"


def scoped(applicability: dict, server_id: str) -> dict:
    """Memories apply to the IoT MCP service and ESP32 devices, not to one lab device."""
    return {**applicability, "mcp_server_id": server_id, "device_types": ["ESP32"]}


def resolve_refs(content: dict, episodes: dict[str, Memory]) -> dict:
    """`episode:<slug>` in evidence_refs becomes the episode's memory ID."""
    resolved = json.loads(json.dumps(content))
    for claim in resolved.get("claims", []):
        claim["evidence_refs"] = [
            episodes[ref.split(":", 1)[1]].id if ref.startswith("episode:") else ref
            for ref in claim.get("evidence_refs", [])
        ]
    return resolved


async def refresh(db, owner: str, memory: Memory, payload: MemoryWrite,
                  linked: list[Memory], confirm: bool) -> bool:
    """An experience whose seed entry changed (e.g. a candidate verified later) gets a new
    revision with the new evidence instead of a duplicate memory."""
    current = await revision(db, memory)
    if make_revision(memory, owner, payload, 0).content_hash != current.content_hash:
        update = payload.model_copy(update={
            "expected_revision": memory.current_revision,
            "change_reason": "运维种子更新：补充复现证据",
        })
        memory = await edit(db, owner, memory.id, update)
        known = set((await db.scalars(select(MemoryEvidenceLink.episode_id).where(
            MemoryEvidenceLink.memory_id == memory.id,
            MemoryEvidenceLink.revision == memory.current_revision))).all())
        for episode in linked:
            if episode.id not in known:
                db.add(MemoryEvidenceLink(
                    owner_user_id=owner, memory_id=memory.id, revision=memory.current_revision,
                    episode_id=episode.id, episode_revision=episode.current_revision))
        await db.flush()
    elif not (confirm and memory.status == "candidate"):
        return False
    if confirm and (memory.status != "active" or memory.active_revision != memory.current_revision):
        await transition(db, owner, memory.id, memory.current_revision, "confirm")
    return True


async def seed(username: str, server_key: str, path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    counts = {"created": 0, "updated": 0, "kept": 0}
    async with SessionFactory() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            raise SystemExit(f"user {username!r} not found")
        server = await db.scalar(select(MCPServer).where(MCPServer.server_key == server_key))
        if server is None:
            raise SystemExit(f"MCP server {server_key!r} not registered; run scripts.bootstrap_local_mcp")

        async def existing(slug: str) -> Memory | None:
            return await db.scalar(select(Memory).where(
                Memory.owner_user_id == user.id, Memory.event_key == EVENT_PREFIX + slug))

        episodes: dict[str, Memory] = {}
        for item in data["episodes"]:
            memory = await existing(item["slug"])
            if memory is None:
                payload = MemoryWrite(
                    kind="episodic",
                    title=item["title"],
                    summary=item["summary"],
                    content=item["content"],
                    applicability=scoped(item.get("applicability", {}), server.id),
                    confirm=True,
                )
                memory = await create(db, user.id, payload, source_type="user",
                                      event_key=EVENT_PREFIX + item["slug"])
                counts["created"] += 1
            else:
                counts["kept"] += 1
            episodes[item["slug"]] = memory
        await db.flush()

        for item in data["experiences"]:
            linked = [episodes[slug] for slug in item.get("episodes", [])]
            payload = MemoryWrite(
                kind="experience",
                title=item["title"],
                summary=item["summary"],
                content=resolve_refs(item["content"], episodes),
                applicability=scoped(item.get("applicability", {}), server.id),
            )
            memory = await existing(item["slug"])
            if memory is not None:
                changed = await refresh(db, user.id, memory, payload, linked, item.get("confirm", True))
                counts["updated" if changed else "kept"] += 1
                continue
            memory = await create(db, user.id, payload, source_type="user",
                                  event_key=EVENT_PREFIX + item["slug"],
                                  episode=linked[0] if linked else None)
            for episode in linked[1:]:
                db.add(MemoryEvidenceLink(
                    owner_user_id=user.id, memory_id=memory.id, revision=1,
                    episode_id=episode.id, episode_revision=episode.current_revision))
            await db.flush()
            # Verified experiences are enabled; unverified ones stay candidates for review.
            if item.get("confirm", True):
                await transition(db, user.id, memory.id, 1, "confirm")
            counts["created"] += 1
        await db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--server-key", default="iot-mcp-local")
    parser.add_argument("--file", type=Path, default=SEED_FILE)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(seed(args.username, args.server_key, args.file)), ensure_ascii=False))


if __name__ == "__main__":
    main()
