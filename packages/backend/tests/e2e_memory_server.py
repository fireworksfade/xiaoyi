"""Isolated real HTTP/worker/database fixture for the browser memory acceptance flow.

Only the external model and device tool facts are deterministic. No production
test endpoints are added, and every invocation gets a disposable SQLite database.
"""

import os
import tempfile
import uuid
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="xiaoyi-memory-e2e-") as folder:
        os.environ.update(
            {
                "DATABASE_URL": "sqlite+aiosqlite:///" + (Path(folder) / "memory.db").as_posix(),
                "AGENT_RUNTIME": "mock",
                "DB_AUTO_UPGRADE": "true",
                "MEMORY_ENABLED": "true",
                "MEMORY_JOB_POLL_SECONDS": "0.05",
                "MEMORY_AUTO_CAPTURE": "true",
                "MEMORY_AUTO_PROPOSE_EXPERIENCE": "true",
                "MEMORY_QDRANT_URL": "",
                "MEMORY_EMBEDDING_URL": "",
                "RUN_ARTIFACT_ROOT": str(Path(folder) / "artifacts"),
                "SESSION_COOKIE_SECURE": "false",
            }
        )
        import uvicorn

        from app.agent.runtime import RuntimeEvent
        from app.db import SessionFactory
        from app.memory import boundary, extraction, service
        from app.memory.models import Memory
        from app.memory.schemas import MemoryWrite
        from app.services.runs import orchestrator

        class DiagnosisRuntime:
            run_id = None

            async def stream(self, messages, mcp_servers):
                output = {
                    "ok": True,
                    "data": {
                        "diagnosis_id": "DIA_20260930_" + uuid.uuid4().hex[:8].upper(),
                        "device_id": "memory-e2e-device",
                        "fault_name": "MQTT 心跳异常",
                        "cause": "心跳配置需核实",
                        "evidence": ["心跳超时，根因尚未确认"],
                    },
                }
                await boundary.finish(
                    self.run_id, "memory-e2e-service", "diagnose_fault", {}, output
                )
                yield RuntimeEvent("tool.finished", {"tool_name": "diagnose_fault", **output})
                answer = "诊断完成：MQTT 心跳异常，根因需核实。"
                yield RuntimeEvent("answer.delta", {"delta": answer})
                yield RuntimeEvent("answer.final", {"content": answer})

        async def deterministic_extract(job):
            async with SessionFactory() as db:
                episode = await db.get(Memory, job.payload["memory_id"])
                if not episode or not await service.eligible(db, episode, job.payload["revision"]):
                    return
                rev = await service.revision(db, episode, job.payload["revision"])
                await service.create(
                    db,
                    job.owner_user_id,
                    MemoryWrite(
                        title="MQTT 排查经验 " + episode.id[:8],
                        summary="先核实心跳配置；单次诊断不确认根因。",
                        content={
                            "claims": [
                                {
                                    "text": "心跳配置可能导致 MQTT 超时",
                                    "epistemic_status": "hypothesis",
                                    "evidence_refs": [episode.id],
                                }
                            ],
                            "procedure": ["检查心跳配置后再考虑重连"],
                            "limitations": ["需要现场证据确认"],
                        },
                        applicability=rev.applicability_json,
                    ),
                    source_type="task",
                    event_key="e2e-experience:" + episode.id,
                    episode=episode,
                )
                await db.commit()

        orchestrator.build_runtime = lambda settings: DiagnosisRuntime()
        extraction.extract = deterministic_extract
        from app.main import app

        @app.middleware("http")
        async def identify_fixture(request, call_next):
            response = await call_next(request)
            response.headers["x-request-id"] = "memory-e2e-" + response.headers.get(
                "x-request-id", "fixture"
            )
            return response

        uvicorn.run(app, host="127.0.0.1", port=18001)


if __name__ == "__main__":
    main()
