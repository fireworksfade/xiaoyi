"""Acceptance counterexamples: execution gates, withdrawal, faults and stale vectors."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_memory import _clean_memory as _clean_memory
from test_memory import _experience_payload, _failed_repair, _make_running_run, _set_rediagnosis

from app.config import get_settings
from app.db import SessionFactory
from app.memory import actions, boundary, capture, indexing, service, worker
from app.memory.models import (
    Memory,
    MemoryActionLink,
    MemoryEvidenceLink,
    MemoryFeedback,
    MemoryJob,
    MemorySource,
)
from app.memory.retrieval import search
from app.memory.schemas import MemorySearch, MemoryWrite
from app.models import AgentRun, Conversation, RunStatus, utc_now


@pytest.mark.parametrize(
    "data",
    [{"command": {"command_id": "C", "status": "timed_out"}}, {"delivery_status": "unknown"}],
)
async def test_unresolved_outcomes_require_recovery_before_new_action(data):
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    async with SessionFactory() as db:
        stored = await db.get(MemoryActionLink, link.id)
        stored.tracking_until = utc_now() - timedelta(seconds=1)
        await db.commit()
    await actions.save_result(link.id, {"ok": True, "data": data})
    with pytest.raises(HTTPException, match="REPAIR_RESULT_UNRESOLVED"):
        await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    # Same textual device ID on another service is independent.
    await actions.reserve(run.id, "srv-2", "execute_device_action", {"device_id": "d1"})


async def test_run_deadline_is_an_execution_gate():
    run = await _make_running_run()
    async with SessionFactory() as db:
        stored = await db.get(AgentRun, run.id)
        stored.started_at = utc_now() - timedelta(
            minutes=get_settings().agent_run_max_runtime_minutes + 1
        )
        await db.commit()
    with pytest.raises(HTTPException, match="RUN_DEADLINE_REACHED"):
        await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    async with SessionFactory() as db:
        assert not await db.scalar(select(MemoryActionLink.id))


async def test_retrieved_memories_are_not_implicitly_adopted_and_paused_refs_rejected():
    run = await _make_running_run()
    async with SessionFactory() as db:
        item = await service.create(db, run.user_id, _experience_payload(confirm=True))
        refs = [{"memory_id": item.id, "revision": 1}]
        await service.record_usage(db, run.user_id, refs, run_id=run.id)
        await db.commit()
    failed = await _failed_repair(run)
    await _set_rediagnosis(failed.id, "DIA_NEW", memories=refs)
    link = await actions.reserve(
        run.id, "srv-1", "execute_device_action", {"device_id": "d1", "diagnosis_id": "DIA_NEW"}
    )
    assert link.applied_memory_ids == []
    async with SessionFactory() as db:
        await service.transition(db, run.user_id, item.id, 1, "suspend")
        await db.commit()
    with pytest.raises(HTTPException, match="MEMORY_SOURCE_UNAVAILABLE"):
        await actions.reserve(
            run.id, "srv-1", "execute_device_action", {"device_id": "d2"}, applied_memory_refs=refs
        )


async def test_memory_capture_outage_preserves_failure_and_diagnosis(monkeypatch):
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})

    async def broken(*args, **kwargs):
        raise RuntimeError("injected memory outage")

    monkeypatch.setattr(actions, "record_tool", broken)
    monkeypatch.setattr(boundary, "record_tool", broken)
    monkeypatch.setattr(boundary, "search", broken)
    await boundary.finish(
        run.id,
        "srv-1",
        "execute_device_action",
        {},
        {"ok": True, "data": {"command": {"command_id": "C", "status": "failed"}}},
        link,
    )
    calls = []

    async def call(tool, arguments):
        calls.append(tool)
        return SimpleNamespace(
            structured_content={
                "ok": True,
                "data": {"diagnosis_id": "DIA_NEW", "device_id": "d1", "new_evidence": ["new log"]},
            }
        )

    result = await boundary.rediagnose(run.id, "srv-1", link.id, call)
    assert result["diagnosis_id"] == "DIA_NEW"
    assert calls == ["get_device_status", "get_device_logs", "diagnose_fault"]
    async with SessionFactory() as db:
        assert (await db.get(MemoryActionLink, link.id)).outcome == "failed"


async def test_pause_survives_late_episode_result():
    run = await _make_running_run()
    async with SessionFactory() as db:
        source = await capture.record_tool(
            db,
            run,
            "srv-1",
            "execute_device_action",
            {},
            {
                "ok": True,
                "data": {
                    "command": {
                        "command_id": "C",
                        "device_id": "d1",
                        "status": "applied",
                        "verify_status": "succeeded",
                    }
                },
            },
        )
        item = await capture.capture_source(db, source)
        await service.transition(db, run.user_id, item.id, 1, "suspend")
        await db.commit()
        source.excerpt = {"command": {"command_id": "C", "device_id": "d1", "status": "failed"}}
        await capture.capture_source(db, source)
        await db.commit()
        assert item.current_revision == 2 and item.status == "suspended"
        assert await search(db, run.user_id, MemorySearch(query="诊断")) == []


async def test_forget_rebuilds_multisource_candidate_without_private_text():
    run = await _make_running_run()
    async with SessionFactory() as db:
        other = Conversation(user_id=run.user_id, title="retained")
        db.add(other)
        await db.flush()
        sources = [
            MemorySource(
                owner_user_id=run.user_id,
                source_key=f"s{i}",
                source_type="tool",
                source_id=f"s{i}",
                conversation_id=cid,
                excerpt={"fact": fact},
                content_hash=f"h{i}",
            )
            for i, cid, fact in [
                (1, run.conversation_id, "PRIVATE_REMOVED"),
                (2, other.id, "INDEPENDENT_FACT"),
            ]
        ]
        db.add_all(sources)
        await db.flush()
        payload = _experience_payload(confirm=True)
        payload.summary = "PRIVATE_REMOVED"
        item = await service.create(db, run.user_id, payload, source=sources[0])
        db.add(
            MemoryEvidenceLink(
                owner_user_id=run.user_id, memory_id=item.id, revision=1, source_id=sources[1].id
            )
        )
        await db.commit()
        await service.forget_source(db, run.user_id, run.conversation_id)
        await db.commit()
        view = await service.view(db, item)
        assert item.status == "suspended" and item.current_revision == 2
        assert "PRIVATE_REMOVED" not in str(view)
        assert "INDEPENDENT_FACT" in str(view)
        old = await service.revision(db, item, 1)
        assert old.content_json == {} and old.summary == ""
        await service.transition(db, run.user_id, item.id, 2, "confirm")
        await db.commit()
        assert await service.eligible(db, item)


async def test_deleted_content_is_purged_without_another_user_event():
    async with SessionFactory() as db:
        item = await service.create(db, "user-a", _experience_payload(confirm=True))
        await service.transition(db, "user-a", item.id, 1, "delete")
        assert await db.scalar(select(MemoryJob.id).where(MemoryJob.kind == "purge_memory_content"))
        item.deleted_at = utc_now() - timedelta(days=31)
        await db.commit()
    await worker.purge_expired()
    async with SessionFactory() as db:
        item = await db.get(Memory, item.id)
        rev = await service.revision(db, item)
        assert not rev.summary and not rev.content_json and not rev.search_text


async def test_stale_vector_version_hash_and_fingerprint_are_rejected(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "memory_qdrant_url", "https://qdrant.invalid")
    monkeypatch.setattr(settings, "memory_embedding_url", "https://embed.invalid")
    async with SessionFactory() as db:
        item = await service.create(
            db,
            "user-a",
            MemoryWrite(
                title="obsoleteonly",
                summary="obsoleteonly",
                content={"procedure": ["old"]},
                confirm=True,
            ),
        )
        await service.edit(
            db,
            "user-a",
            item.id,
            MemoryWrite(
                title="replacement",
                summary="replacement",
                content={"procedure": ["new"]},
                expected_revision=1,
                confirm=True,
            ),
        )
        await db.commit()
        current = await service.revision(db, item)
    payload = {
        "owner_user_id": "user-a",
        "memory_id": item.id,
        "revision": 1,
        "status": "active",
        "content_hash": current.content_hash,
        "model_fingerprint": settings.memory_embedding_fingerprint,
    }

    def handler(request):
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200, json={"data": [{"embedding": [0.0] * settings.memory_embedding_dimensions}]}
            )
        return httpx.Response(
            200, json={"result": {"points": [{"score": 0.9, "payload": payload}]}}
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        indexing.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(handler), **kw),
    )
    for field, bad in [
        ("revision", 1),
        ("content_hash", "obsolete"),
        ("model_fingerprint", "other"),
    ]:
        payload.update(
            revision=2,
            content_hash=current.content_hash,
            model_fingerprint=settings.memory_embedding_fingerprint,
        )
        payload[field] = bad
        async with SessionFactory() as db:
            assert await search(db, "user-a", MemorySearch(query="obsoleteonly")) == []
    payload.update(
        revision=2,
        content_hash=current.content_hash,
        model_fingerprint=settings.memory_embedding_fingerprint,
    )
    async with SessionFactory() as db:
        found = await search(db, "user-a", MemorySearch(query="obsoleteonly"))
        assert found[0]["revision"] == 2


async def test_rediagnosis_cancellation_lease_and_pinned_budget():
    run = await _make_running_run()
    async with SessionFactory() as db:
        stored = await db.get(AgentRun, run.id)
        stored.runtime_state = {"repair_budget": {"limit": 1}}
        await db.commit()
    link = await _failed_repair(run)
    seen, entered, release = [], asyncio.Event(), asyncio.Event()

    async def call(tool, arguments):
        seen.append(tool)
        if tool == "get_device_status":
            entered.set()
            await release.wait()
        if tool == "diagnose_fault":
            assert arguments["repair_context"]["remaining_attempts"] == 0
        return SimpleNamespace(
            structured_content={
                "ok": True,
                "data": {"diagnosis_id": "DIA_NEW", "new_evidence": True},
            }
        )

    task = asyncio.create_task(boundary.rediagnose(run.id, "srv-1", link.id, call))
    await entered.wait()
    assert await boundary.rediagnose(run.id, "srv-1", link.id, call) is None
    release.set()
    assert (await task)["diagnosis_id"] == "DIA_NEW"
    assert seen.count("diagnose_fault") == 1
    async with SessionFactory() as db:
        stored = await db.get(AgentRun, run.id)
        stored.status = RunStatus.FAILED
        await db.commit()
    assert await boundary.rediagnose(run.id, "srv-1", link.id, call) is None


async def test_inconclusive_feedback_can_converge_to_failure():
    run = await _make_running_run()
    async with SessionFactory() as db:
        item = await service.create(db, run.user_id, _experience_payload(confirm=True))
        refs = [{"memory_id": item.id, "revision": 1}]
        await service.record_usage(db, run.user_id, refs, run_id=run.id)
        await db.commit()
    link = await actions.reserve(
        run.id, "srv-1", "execute_device_action", {"device_id": "d1"}, applied_memory_refs=refs
    )
    await actions.save_result(
        link.id, {"ok": True, "data": {"command": {"command_id": "C_LATE", "status": "timed_out"}}}
    )
    await actions.save_result(
        link.id, {"ok": True, "data": {"command": {"command_id": "C_LATE", "status": "failed"}}}
    )
    async with SessionFactory() as db:
        feedback = (
            await db.scalars(select(MemoryFeedback).where(MemoryFeedback.memory_id == item.id))
        ).all()
        assert len(feedback) == 1 and feedback[0].outcome == "failed"
        assert (await db.get(Memory, item.id)).status == "suspended"


async def test_late_old_counterexample_preserves_new_confirmed_version():
    from app.memory.reconcile import reconcile

    run = await _make_running_run()
    async with SessionFactory() as db:
        item = await service.create(db, run.user_id, _experience_payload(confirm=True))
        refs = [{"memory_id": item.id, "revision": 1}]
        await service.record_usage(db, run.user_id, refs, run_id=run.id)
        await db.commit()
    link = await actions.reserve(
        run.id, "srv-1", "execute_device_action", {"device_id": "d1"}, applied_memory_refs=refs
    )
    async with SessionFactory() as db:
        payload = _experience_payload(confirm=True)
        payload.expected_revision = 1
        await service.edit(db, run.user_id, item.id, payload)
        await db.commit()
    await actions.save_result(
        link.id, {"ok": True, "data": {"command": {"command_id": "C_OLD", "status": "failed"}}}
    )
    async with SessionFactory() as db:
        job = await db.scalar(select(MemoryJob).where(MemoryJob.kind == "reconcile_experience"))
    await reconcile(job)
    async with SessionFactory() as db:
        stored = await db.get(Memory, item.id)
        assert stored.status == "active" and stored.active_revision == stored.current_revision == 2


async def test_optional_memory_outage_does_not_change_completed_run(monkeypatch):
    from app.services.runs.orchestrator import execute_claimed_run

    run = await _make_running_run()

    async def broken(*args, **kwargs):
        raise RuntimeError("injected optional memory outage")

    monkeypatch.setattr(service, "working_snapshot", broken)
    monkeypatch.setattr(service, "enqueue", broken)
    monkeypatch.setattr(boundary, "search", broken)
    await execute_claimed_run(run.id)
    async with SessionFactory() as db:
        assert (await db.get(AgentRun, run.id)).status == RunStatus.COMPLETED


async def test_verified_recovery_stops_same_device_actions():
    run = await _make_running_run()
    link = await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    await actions.save_result(
        link.id,
        {
            "ok": True,
            "data": {
                "command": {
                    "command_id": "C_RECOVERED",
                    "status": "applied",
                    "verify_status": "succeeded",
                }
            },
        },
    )
    with pytest.raises(HTTPException, match="REPAIR_ALREADY_RECOVERED"):
        await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d1"})
    await actions.reserve(run.id, "srv-1", "execute_device_action", {"device_id": "d2"})


async def test_failed_job_retry_is_owner_scoped_and_cannot_duplicate_running_work():
    from app.api.memories import retry_memory_job

    request = SimpleNamespace(state=SimpleNamespace(request_id="test"))
    async with SessionFactory() as db:
        job = await service.enqueue(db, "user-a", "propose_experience", "retry-test", {})
        job.status, job.attempts, job.error_code = "failed", 8, "MEMORY_MODEL_UNAVAILABLE"
        await db.commit()
        with pytest.raises(HTTPException, match="MEMORY_JOB_NOT_FOUND"):
            await retry_memory_job(job.id, request, db, SimpleNamespace(id="user-b"), None)
        result = await retry_memory_job(job.id, request, db, SimpleNamespace(id="user-a"), None)
        assert result["data"]["queued"] is True
        await db.refresh(job)
        assert job.status == "pending" and job.attempts == 0 and job.error_code is None
        with pytest.raises(HTTPException, match="MEMORY_INVALID_TRANSITION"):
            await retry_memory_job(job.id, request, db, SimpleNamespace(id="user-a"), None)


async def test_rediagnosis_receives_original_hypothesis_and_owned_diagnosis_body():
    run = await _make_running_run()
    link = await _failed_repair(run)
    async with SessionFactory() as db:
        stored = await db.get(MemoryActionLink, link.id)
        stored.diagnosis_id = "DIA_PRIOR"
        stored.arguments = {**stored.arguments, "reason": "prior hypothesis"}
        for owner, key, cause in [
            (run.user_id, "srv-1:DIA_PRIOR", "owned hypothesis"),
            ("other", "srv-1:DIA_PRIOR", "foreign secret"),
        ]:
            db.add(
                MemorySource(
                    owner_user_id=owner,
                    source_key=key,
                    source_type="tool",
                    source_id="DIA_PRIOR",
                    diagnosis_id="DIA_PRIOR",
                    mcp_server_id="srv-1",
                    excerpt={"cause": cause},
                    content_hash="hash",
                )
            )
        await db.commit()

    async def call(tool, arguments):
        if tool == "diagnose_fault":
            context = arguments["repair_context"]
            assert context["previous_hypothesis"] == "prior hypothesis"
            assert context["previous_diagnosis"] == {"cause": "owned hypothesis"}
        return SimpleNamespace(
            structured_content={
                "ok": True,
                "data": {"diagnosis_id": "DIA_NEW", "new_evidence": True},
            }
        )

    assert (await boundary.rediagnose(run.id, "srv-1", link.id, call))["diagnosis_id"] == "DIA_NEW"
