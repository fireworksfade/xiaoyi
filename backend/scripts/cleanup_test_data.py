import argparse
import asyncio

from sqlalchemy import delete, or_, select

from app.db import SessionFactory
from app.models import (
    AgentRun,
    Conversation,
    MCPServer,
    MCPTool,
    Message,
    RunEvent,
)


async def main(apply: bool) -> None:
    async with SessionFactory() as db:
        test_servers = list(
            (
                await db.scalars(
                    select(MCPServer).where(
                        or_(
                            MCPServer.server_key.like("test-%"),
                        )
                    )
                )
            ).all()
        )
        test_conversations = list(
            (
                await db.scalars(
                    select(Conversation).where(
                        Conversation.title == "测试对话"
                    )
                )
            ).all()
        )
        server_ids = [item.id for item in test_servers]
        conversation_ids = [item.id for item in test_conversations]
        run_ids = list(
            (
                await db.scalars(
                    select(AgentRun.id).where(AgentRun.conversation_id.in_(conversation_ids))
                )
            ).all()
        ) if conversation_ids else []
        print(
            {
                "servers": len(server_ids),
                "conversations": len(conversation_ids),
                "runs": len(run_ids),
                "apply": apply,
            }
        )
        if not apply:
            return

        if run_ids:
            await db.execute(delete(RunEvent).where(RunEvent.run_id.in_(run_ids)))
            await db.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))
        if conversation_ids:
            await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
            await db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
        if server_ids:
            await db.execute(delete(MCPTool).where(MCPTool.server_id.in_(server_ids)))
            await db.execute(delete(MCPServer).where(MCPServer.id.in_(server_ids)))
        await db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
