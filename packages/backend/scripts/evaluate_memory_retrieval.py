"""Online Qwen/Qdrant acceptance with an isolated SQL database and collection.

Run from packages/backend; no production memories or vector collections are used.
"""

import argparse
import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="memory-retrieval-eval-") as folder:
        os.environ.update(
            {
                "DATABASE_URL": "sqlite+aiosqlite:///" + (Path(folder) / "eval.db").as_posix(),
                "MEMORY_QDRANT_URL": "http://127.0.0.1:6333",
                "MEMORY_EMBEDDING_URL": "http://127.0.0.1:9010",
                "MEMORY_COLLECTION_PREFIX": "memory_acceptance_" + uuid.uuid4().hex,
                "NO_PROXY": "127.0.0.1,localhost",
            }
        )
        asyncio.run(evaluate(args.output))


async def evaluate(output=None):
    import httpx
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import Base, SessionFactory, engine
    from app.memory import indexing, service
    from app.memory.models import MemoryVectorOutbox
    from app.memory.retrieval import search
    from app.memory.schemas import MemorySearch, MemoryWrite

    samples = [
        ("heartbeat", "心跳配置排查", "无线信号正常但周期性断连时，核实心跳间隔与代理超时配置。"),
        ("power", "电池供电排查", "低温时供电电压下降可能造成设备突然重启；先测电池负载电压。"),
        ("storage", "日志磁盘清理", "存储空间耗尽导致新日志无法写入时，应先导出重要日志再清理。"),
        (
            "failure",
            "重连失败记录",
            "MQTT 重连命令执行失败，连接仍未恢复；不要以 ACK 作为恢复证据，应获取实时状态和错误日志。",
        ),
    ]
    queries = [
        ("intermittent disconnects", "heartbeat"),
        ("cold weather voltage sag", "power"),
        ("filesystem capacity exhausted", "storage"),
        ("broker reconnect unsuccessful", "failure"),
    ]
    settings = get_settings()
    base = settings.memory_qdrant_url + "/collections/" + indexing.collection()
    report = {
        "model": settings.memory_embedding_model,
        "dimensions": settings.memory_embedding_dimensions,
        "dataset_size": 6,
        "online": [],
        "portable": [],
    }
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        ids = {}
        async with SessionFactory() as db:
            for key, title, summary in samples:
                item = await service.create(
                    db,
                    "eval-owner",
                    MemoryWrite(
                        title=title,
                        summary=summary,
                        content={
                            "claims": [{"text": summary, "epistemic_status": "user_asserted"}],
                            "procedure": [summary],
                        },
                        confirm=True,
                    ),
                )
                ids[key] = item.id
            foreign = await service.create(
                db,
                "other-owner",
                MemoryWrite(
                    title=samples[0][1],
                    summary=samples[0][2],
                    content={"procedure": [samples[0][2]]},
                    confirm=True,
                ),
            )
            unsuitable = await service.create(
                db,
                "eval-owner",
                MemoryWrite(
                    title="其他设备心跳经验",
                    summary=samples[0][2],
                    content={"procedure": [samples[0][2]]},
                    applicability={"mcp_server_id": "other-service", "device_ids": ["same-name"]},
                    confirm=True,
                ),
            )
            await db.commit()
            entries = list((await db.scalars(select(MemoryVectorOutbox))).all())
        for entry in entries:
            await indexing.sync(SimpleNamespace(payload={"outbox_id": entry.id}))
        for query, expected in queries:
            started = time.perf_counter()
            async with SessionFactory() as db:
                results = await search(
                    db,
                    "eval-owner",
                    MemorySearch(query=query, mcp_server_id="eval-service", device_id="same-name"),
                )
            row = {
                "query": query,
                "expected": expected,
                "correct": bool(results and results[0]["memory_id"] == ids[expected]),
                "mode": results[0]["retrieval_mode"] if results else "empty",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "isolated": not any(r["memory_id"] in {foreign.id, unsuitable.id} for r in results),
            }
            report["online"].append(row)
        settings.memory_embedding_url = None
        for query, expected in [
            ("周期性断连", "heartbeat"),
            ("低温供电", "power"),
            ("空间耗尽", "storage"),
            ("重连命令执行失败", "failure"),
        ]:
            async with SessionFactory() as db:
                results = await search(
                    db,
                    "eval-owner",
                    MemorySearch(query=query, mcp_server_id="eval-service", device_id="same-name"),
                )
            report["portable"].append(
                {
                    "query": query,
                    "expected": expected,
                    "correct": bool(results and results[0]["memory_id"] == ids[expected]),
                    "mode": results[0]["retrieval_mode"] if results else "empty",
                }
            )
        report["passed"] = all(
            row["correct"] and row["isolated"] and row["mode"] == "hybrid"
            for row in report["online"]
        ) and all(row["correct"] and row["mode"] == "keyword" for row in report["portable"])
    finally:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(base)
            report["collection_removed"] = response.status_code in {200, 404}
        await engine.dispose()
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if not report.get("passed") or not report["collection_removed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
