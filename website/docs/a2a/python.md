---
outline: deep
---

# A2A — Python

## Installation

```bash
pip install mq9
```

**Requirements:** Python 3.10+

---

## Overview

Every agent is equal — each one can send tasks to others and receive tasks from others. There is no special "client" or "server" role.

- Create an `Mq9A2AAgent` with just the broker address.
- Call `connect()` to connect.
- Call `register(agent_card)` to publish your identity and start receiving tasks — it blocks until you stop.
- Use `discover()`, `send_message()`, `get_task()`, etc. to interact with other agents at any time.

---

## Quick start

### Agent A — registers and handles incoming tasks

```python
import asyncio
from a2a.helpers import new_task_from_user_message, new_text_artifact, new_text_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types.a2a_pb2 import (
    AgentCard, AgentCapabilities, AgentSkill,
    TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent,
)
from mq9.a2a import Mq9A2AAgent

agent = Mq9A2AAgent()  # defaults to public debug server

@agent.on_message
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    # Resume an existing task (multi-turn), or create a new one from this message.
    task = context.current_task or new_task_from_user_message(context.message)
    # First event must be the Task object — creates the task record on the sender's side.
    await event_queue.enqueue_event(task)

    # Tell the sender processing has started.
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    ))

    # Extract the first text part from the message.
    text = context.message.parts[0].text if context.message.parts else ""
    result = my_translate(text)  # your logic here

    # Push the result; call multiple times to stream partial output.
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        artifact=new_text_artifact(name="translation", text=result),
    ))
    # Signal task is done — the sender's stream ends here.
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
    ))

card = AgentCard(
    name="demo.agent.translator",
    description="Multilingual translation agent. Supports EN, ZH, JA, KO.",
    version="1.0.0",
    skills=[AgentSkill(id="translate", name="Translate text")],
    capabilities=AgentCapabilities(streaming=True),
)

async def main():
    await agent.connect()
    mailbox = await agent.create_mailbox(card.name)  # create mailbox, start receiving
    await agent.register(card)                       # publish to registry, become discoverable
    print("mailbox:", mailbox)
    await asyncio.Event().wait()  # keep running until Ctrl+C

asyncio.run(main())
```

### Agent B — discovers Agent A and sends a task

```python
import asyncio
from a2a.helpers import new_text_message
from a2a.types.a2a_pb2 import AgentCard, AgentCapabilities, Role, SendMessageRequest
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from mq9.a2a import Mq9A2AAgent

agent_b = Mq9A2AAgent()  # defaults to public debug server

# Register a handler to receive results sent back by Agent A.
@agent_b.on_message
async def on_result(context: RequestContext, _) -> None:
    text = context.message.parts[0].text if context.message.parts else ""
    print("Result:", text)

card_b = AgentCard(
    name="demo.agent.sender",
    description="Demo sender agent",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
)

async def main():
    await agent_b.connect()
    # Create own mailbox so Agent A has an address to write results back to.
    b_mailbox = await agent_b.create_mailbox(card_b.name)
    await agent_b.register(card_b)  # publish to registry (optional — B only needs to be reachable)

    results = await agent_b.discover("translation agent")
    target = results[0]

    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )

    # Pass reply_to so Agent A streams results back to our mailbox.
    msg_id = await agent_b.send_message(target["mailbox"], request, reply_to=b_mailbox)
    print("Sent, msg_id:", msg_id)

    # Wait for the result — it arrives via @on_message above.
    await asyncio.sleep(10)

    await agent_b.unregister()
    await agent_b.close()

asyncio.run(main())
```

Both agents register their own mailbox and are fully equal — each can send and receive. Agent B passes `reply_to=b_mailbox` so Agent A knows where to stream results back; the result arrives in Agent B's `@on_message` handler.

---

## Mq9A2AAgent

```python
Mq9A2AAgent(*, server: str = "nats://demo.robustmq.com:4222", mailbox_ttl: int = 0, request_timeout: float = 60)
```

| Parameter | Type | Description |
| --- | --- | --- |
| `server` | `str` | mq9 broker NATS URL. Defaults to the public debug server `nats://demo.robustmq.com:4222` — can be omitted during development |
| `mailbox_ttl` | `int` | Mailbox TTL in seconds (`0` = permanent) |
| `request_timeout` | `float` | Default timeout for outbound requests in seconds |

### `agent.connect`

Connect to the broker. Required before any operation.

### `agent.close`

Stop consuming messages and disconnect from the broker. Call this after the backlog is drained.

### `@agent.on_message`

Decorator — registers the async message handler:

```python
@agent.on_message
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    ...
```

### `agent.create_mailbox`

Create a mailbox and start the consumer in the background. **Returns immediately** with the mailbox address.

Parameter: `name: str` — mailbox name, typically `AgentCard.name`.

Returns `str` — the mailbox address. The agent can receive messages immediately after this call, without being in the registry.

### `agent.register`

Publish agent identity to the registry so others can discover it via `discover()`.

Must be called after `create_mailbox()`.

### `agent.unregister`

Remove this agent from the registry. Other agents can no longer discover it. The connection and consumer stay active so queued messages can still be processed. Call `close()` when ready to fully stop.

### `agent.discover`

Find other agents in the registry by natural-language description.

| Parameter | Description |
| --- | --- |
| `query` | Natural-language query string; pass `None` to list all |
| `semantic` | `True` (default) vector search; `False` keyword match |
| `limit` | Max results to return, default `10` |

Returns `list[dict]`, each entry containing `name`, `mailbox`, `agent_card`, and more.

### `agent.send_message`

Send a message to another agent.

| Parameter | Description |
| --- | --- |
| `mail_address` | Agent info dict from `discover()` (must have `mailbox`), or a raw mailbox address string |
| `request` | `SendMessageRequest` (from `a2a.types.a2a_pb2`) |

Returns `int` — the `msg_id` assigned by the broker, confirming the message was queued.

### `agent.get_task`

Get the current state of a task on another agent.

Parameters: `mail_address`, `task_id: str`. Returns `Task | None`.

### `agent.list_tasks`

List all tasks stored by another agent.

Parameters: `mail_address`, `page_size: int = 100`. Returns `list[Task]`.

### `agent.cancel_task`

Request cancellation of a running task on another agent.

Parameters: `mail_address`, `task_id: str`. Returns updated `Task | None`.

---

## Handler reference

The handler registered with `@agent.on_message` receives a2a-sdk native objects:

| Object | Type | Description |
| --- | --- | --- |
| `context.message` | `Message` | Incoming A2A message |
| `context.task_id` | `str \| None` | Task ID (auto-assigned if new) |
| `context.context_id` | `str \| None` | Context/session ID |
| `context.current_task` | `Task \| None` | Existing task if resuming a conversation |
| `event_queue` | `EventQueue` | Push response events here |

Events to enqueue (all from `a2a.types.a2a_pb2`):

| Event | When to use |
| --- | --- |
| `Task` | First event — creates the task record |
| `TaskStatusUpdateEvent(state=WORKING)` | Signal processing has started |
| `TaskArtifactUpdateEvent` | Push result content — call multiple times for streaming |
| `TaskStatusUpdateEvent(state=COMPLETED)` | Signal task is done |
| `TaskStatusUpdateEvent(state=FAILED)` | Signal failure |
| `TaskStatusUpdateEvent(state=CANCELED)` | Signal task was cancelled |
