"""mq9 A2A Demo
=============
Two-way A2A communication: Agent B sends a task to Agent A and receives
the result back via its own mailbox.

Run two terminals:

  Terminal 1 — start Agent A (translator):
    MQ9_SERVER=nats://demo.robustmq.com:4222 python a2a_demo.py agent

  Terminal 2 — run Agent B (sender + receiver):
    MQ9_SERVER=nats://demo.robustmq.com:4222 python a2a_demo.py client

Or run both in the same process:
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

# ── Agent cards ────────────────────────────────────────────────────────────────

AGENT_A_CARD = AgentCard(
    name="demo.agent.translator",
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

AGENT_B_CARD = AgentCard(
    name="demo.agent.sender",
    description="Demo sender agent that dispatches translation tasks.",
    version="1.0.0",
    skills=[],
    capabilities=AgentCapabilities(streaming=False),
)


# ──────────────────────────────────────────────────────────────────────────────
# Agent A — translator (receives tasks, writes results back to caller)
# ──────────────────────────────────────────────────────────────────────────────

def make_agent_a() -> Mq9A2AAgent:
    agent = Mq9A2AAgent(server=SERVER)

    @agent.on_message
    async def handle(context: RequestContext, event_queue: EventQueue) -> None:
        # Resume an existing task (multi-turn), or create a new one.
        task = context.current_task or new_task_from_user_message(context.message)
        # First event must be the Task object — creates the task record on the sender's side.
        await event_queue.enqueue_event(task)

        # Tell Agent B we've started processing.
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

        # Extract the first text part from the incoming message.
        text = ""
        if context.message and context.message.parts:
            part = context.message.parts[0]
            if hasattr(part, "text"):
                text = part.text

        # Do the actual work — replace with real logic.
        translated = f"[translated] {text}"

        # Send the result back as an artifact.
        # Because Agent B passed its mailbox as reply_to, _ForwardingEventQueue
        # delivers this event directly to Agent B's @on_message handler.
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                artifact=new_text_artifact(name="translation", text=translated),
            )
        )
        # Signal completion — Agent B's handler will receive this as the last event.
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        )
        print(f"[agent-a] processed: '{text}' → '{translated}'")

    return agent


async def run_agent() -> None:
    agent = make_agent_a()
    print(f"[agent-a] starting — name={AGENT_A_CARD.name}  server={SERVER}")
    await agent.connect()
    mailbox = await agent.create_mailbox(AGENT_A_CARD.name)
    print(f"[agent-a] mailbox={mailbox}")
    await agent.register(AGENT_A_CARD)
    print(f"[agent-a] registered in discovery")
    try:
        await asyncio.Event().wait()  # keep running until Ctrl+C
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await agent.unregister()
        await agent.close()


# ──────────────────────────────────────────────────────────────────────────────
# Agent B — sender + receiver
# Registers its own mailbox, sends a task with reply_to=own mailbox,
# and handles the incoming result via @on_message just like any other agent.
# ──────────────────────────────────────────────────────────────────────────────

def make_agent_b(done_event: asyncio.Event) -> Mq9A2AAgent:
    agent = Mq9A2AAgent(server=SERVER)

    @agent.on_message
    async def handle(context: RequestContext, _) -> None:
        # Agent B receives result events sent back by Agent A.
        if context.message and context.message.parts:
            part = context.message.parts[0]
            if hasattr(part, "text"):
                print(f"[agent-b] received result: {part.text}")
        # Signal the main coroutine that the result arrived.
        done_event.set()

    return agent


async def run_client() -> None:
    done = asyncio.Event()
    agent_b = make_agent_b(done)
    await agent_b.connect()

    # Agent B creates its own mailbox so Agent A has an address to write results back to.
    # register() is optional here — B only needs to be reachable, not discoverable.
    b_mailbox = await agent_b.create_mailbox(AGENT_B_CARD.name)
    await agent_b.register(AGENT_B_CARD)
    print(f"[agent-b] mailbox={b_mailbox}")

    # Discover Agent A.
    print("[agent-b] discovering translation agents…")
    agents = await agent_b.discover("translation agent")
    if not agents:
        print("[agent-b] no agents found — is agent-a running?")
        await agent_b.unregister()
        await agent_b.close()
        return

    target = agents[0]
    print(f"[agent-b] found: name={target.get('name')}  mailbox={target.get('mailbox')}")

    # Send the task, passing our own mailbox as reply_to.
    # Agent A will stream result events back to this address.
    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )
    print("\n[agent-b] sending task…")
    msg_id = await agent_b.send_message(
        target["mailbox"],
        request,
        reply_to=b_mailbox,
    )
    print(f"[agent-b] sent, msg_id={msg_id}")

    # Wait for the result to arrive in our @on_message handler (max 30s).
    print("[agent-b] waiting for result…")
    try:
        await asyncio.wait_for(done.wait(), timeout=30)
    except asyncio.TimeoutError:
        print("[agent-b] timed out waiting for result")

    print("\n[agent-b] done.")
    await agent_b.unregister()
    await agent_b.close()


# ──────────────────────────────────────────────────────────────────────────────
# Combined mode: Agent A in background, Agent B runs once then stops
# ──────────────────────────────────────────────────────────────────────────────

async def run_both() -> None:
    agent_a = make_agent_a()
    await agent_a.connect()
    a_mailbox = await agent_a.create_mailbox(AGENT_A_CARD.name)
    await agent_a.register(AGENT_A_CARD)
    print(f"[agent-a] mailbox={a_mailbox}")

    # Give the consumer a moment to start before Agent B sends.
    await asyncio.sleep(1)

    await run_client()

    await agent_a.unregister()
    await agent_a.close()


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
