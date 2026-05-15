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

agent = Mq9A2AAgent(server="nats://demo.robustmq.com:4222")

@agent.on_message
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    task = context.current_task or new_task_from_user_message(context.message)
    await event_queue.enqueue_event(task)

    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    ))

    text = context.message.parts[0].text if context.message.parts else ""
    result = my_translate(text)  # your logic here

    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        artifact=new_text_artifact(name="translation", text=result),
    ))
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
    ))

card = AgentCard(
    name="agent-a",
    description="Multilingual translation agent. Supports EN, ZH, JA, KO.",
    version="1.0.0",
    skills=[AgentSkill(id="translate", name="Translate text")],
    capabilities=AgentCapabilities(streaming=True),
)

async def main():
    await agent.connect()
    await agent.register(card)   # blocks until stop() or Ctrl+C

asyncio.run(main())
```

### Agent B — discovers Agent A and sends a task

```python
import asyncio
from a2a.helpers import new_text_message
from a2a.types.a2a_pb2 import (
    AgentCard, Role, SendMessageRequest,
    TaskArtifactUpdateEvent, TaskStatusUpdateEvent,
)
from mq9.a2a import Mq9A2AAgent

async def main():
    agent = Mq9A2AAgent(server="nats://demo.robustmq.com:4222")
    await agent.connect()

    # Discover Agent A by natural-language description
    results = await agent.discover("translation agent")
    target = results[0]

    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )

    async for event in await agent.send_message(target, request, timeout=30):
        if isinstance(event, TaskArtifactUpdateEvent):
            print("Result:", event.artifact.parts[0].text)
        elif isinstance(event, TaskStatusUpdateEvent):
            print("Status:", event.status.state)

    await agent.close()

asyncio.run(main())
```

Agent B does not need to register — `connect()` alone is enough to discover and send. If Agent B also wants to receive tasks, it builds its own `AgentCard` and calls `register()`.

---

## API reference

### `Mq9A2AAgent`

#### Constructor

```python
Mq9A2AAgent(*, server: str, mailbox_ttl: int = 0, request_timeout: float = 60)
```

| Parameter | Type | Description |
| --- | --- | --- |
| `server` | `str` | mq9 broker NATS URL |
| `mailbox_ttl` | `int` | Mailbox TTL in seconds (`0` = permanent) |
| `request_timeout` | `float` | Default timeout for outbound requests in seconds |

#### Connection

| Method | Description |
| --- | --- |
| `await agent.connect()` | Connect to the broker. Required before any operation. |
| `await agent.close()` | Disconnect from the broker. |
| `async with agent` | Context manager — calls `connect()` / `close()`. |

#### Registration (receive tasks)

| Method | Description |
| --- | --- |
| `@agent.on_message` | Decorator — registers async handler `(RequestContext, EventQueue) → None` |
| `await agent.register(agent_card)` | Publish identity, create mailboxes, start receiving. Blocks until stopped. |
| `await agent.stop()` | Gracefully unregister and disconnect. |

`register()` derives the agent name and mailbox address from `agent_card.name`. Two mailboxes are created automatically:

| Mailbox | Purpose |
| --- | --- |
| `{name}` | Main inbox — receives incoming tasks and control messages |
| `{name}.tasks` | Task store — persists task state, survives restarts |

#### Discovery & outbound operations

The `agent` parameter in all methods below accepts either an agent info dict from `discover()` (must have a `mailbox` key) or a raw mailbox address string.

| Method | Description |
| --- | --- |
| `await agent.discover(query, *, semantic, limit)` | Find agents by natural-language query. `semantic=True` (default) uses vector search; `False` uses keyword match. Pass `None` to list all. |
| `await agent.send_message(agent, request, *, timeout)` | Send a task and stream back A2A events (`Task`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`). |
| `await agent.get_task(agent, task_id)` | Get current state of a task by ID. Returns `Task \| None`. |
| `await agent.list_tasks(agent, *, page_size)` | List all tasks stored by an agent. Returns `list[Task]`. |
| `await agent.cancel_task(agent, task_id)` | Request task cancellation. Returns updated `Task \| None`. |

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
