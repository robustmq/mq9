"""mq9 A2A Demo
=============
Demonstrates Mq9A2AAgent (server side) and Mq9A2AClient (client side)
communicating via the mq9 broker using the A2A protocol.

Run two terminals:

  Terminal 1 — start the agent:
    MQ9_SERVER=nats://demo.robustmq.com:4222 python a2a_demo.py agent

  Terminal 2 — send a task:
    MQ9_SERVER=nats://demo.robustmq.com:4222 python a2a_demo.py client

Or run both in the same process (agent runs in background):
    MQ9_SERVER=nats://demo.robustmq.com:4222 python a2a_demo.py both
"""

import asyncio
import os
import sys

from a2a.helpers import new_task_from_user_message, new_text_artifact, new_text_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types.a2a_pb2 import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    SendMessageRequest,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from mq9.a2a import Mq9A2AAgent

SERVER = os.environ.get("MQ9_SERVER", "nats://demo.robustmq.com:4222")

AGENT_CARD = AgentCard(
    name="demo.a2a.translator",
    description="Multilingual translation agent. "
                "Send text + target_lang (en/zh/ja), get back translated text.",
    version="1.0.0",
    skills=[
        AgentSkill(
            id="translate",
            name="Translate text",
            description="Translates text between EN, ZH, JA, KO.",
        )
    ],
    capabilities=AgentCapabilities(streaming=True),
)


# ──────────────────────────────────────────────────────────────────────────────
# Agent side
# ──────────────────────────────────────────────────────────────────────────────

def make_agent() -> Mq9A2AAgent:
    agent = Mq9A2AAgent(server=SERVER)

    @agent.on_message
    async def handle(context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=new_text_message("Translating…"),
                ),
            )
        )

        text = ""
        if context.message and context.message.parts:
            part = context.message.parts[0]
            if hasattr(part, "text"):
                text = part.text

        translated = f"[translated] {text}"

        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                artifact=new_text_artifact(name="translation", text=translated),
            )
        )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        )
        print(f"[agent] processed: '{text}' → '{translated}'")

    return agent


async def run_agent() -> None:
    agent = make_agent()
    print(f"[agent] starting — name={AGENT_CARD.name}  server={SERVER}")
    await agent.connect()
    await agent.register(AGENT_CARD)


# ──────────────────────────────────────────────────────────────────────────────
# Client side
# ──────────────────────────────────────────────────────────────────────────────

async def run_client() -> None:
    async with Mq9A2AAgent(server=SERVER) as client:
        print("[client] discovering translation agents…")
        agents = await client.discover("translation agent")
        if not agents:
            print("[client] no agents found — is the agent running?")
            return

        target = agents[0]
        print(f"[client] found agent: name={target.get('name')}  mailbox={target.get('mailbox')}")

        # ── 1. SendMessage (streaming) ─────────────────────────────────────────
        request = SendMessageRequest(
            message=new_text_message("你好，世界", role=Role.ROLE_USER)
        )

        print("\n[client] sending task…")
        task_id = None
        async for event in await client.send_message(target, request, timeout=15):
            if isinstance(event, TaskArtifactUpdateEvent):
                text = event.artifact.parts[0].text if event.artifact.parts else ""
                print(f"[client] artifact: {text}")
            elif isinstance(event, TaskStatusUpdateEvent):
                state_name = TaskState.Name(event.status.state)
                print(f"[client] status: {state_name}")
                if hasattr(event, "task_id") and event.task_id:
                    task_id = event.task_id
            elif hasattr(event, "id"):
                task_id = event.id

        # ── 2. GetTask ─────────────────────────────────────────────────────────
        if task_id:
            print(f"\n[client] GetTask task_id={task_id}")
            task = await client.get_task(target, task_id)
            if task:
                print(f"[client] task state: {TaskState.Name(task.status.state)}")

        # ── 3. ListTasks ───────────────────────────────────────────────────────
        print("\n[client] ListTasks…")
        tasks = await client.list_tasks(target)
        print(f"[client] total tasks stored: {len(tasks)}")

        print("\n[client] done.")


# ──────────────────────────────────────────────────────────────────────────────
# Combined mode: agent in background, client runs once then stops
# ──────────────────────────────────────────────────────────────────────────────

async def run_both() -> None:
    agent = make_agent()
    agent_task = asyncio.create_task(_run_agent_bg(agent))

    await asyncio.sleep(2)

    await run_client()

    await agent.stop()
    agent_task.cancel()
    try:
        await agent_task
    except (asyncio.CancelledError, Exception):
        pass


async def _run_agent_bg(agent: Mq9A2AAgent) -> None:
    await agent.connect()
    await agent.register(AGENT_CARD)


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    match mode:
        case "agent":
            asyncio.run(run_agent())
        case "client":
            asyncio.run(run_client())
        case "both":
            asyncio.run(run_both())
        case _:
            print(__doc__)
            sys.exit(1)
