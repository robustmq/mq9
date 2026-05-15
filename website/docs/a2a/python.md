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
    mailbox = await agent.register(card)
    print("mailbox:", mailbox)
    await asyncio.Event().wait()  # keep running until Ctrl+C

asyncio.run(main())
```

### Agent B — discovers Agent A and sends a task

```python
import asyncio
from a2a.helpers import new_text_message
from a2a.types.a2a_pb2 import Role, SendMessageRequest
from mq9.a2a import Mq9A2AAgent

async def main():
    agent = Mq9A2AAgent()  # defaults to public debug server
    await agent.connect()

    results = await agent.discover("translation agent")
    target = results[0]

    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )

    msg_id = await agent.send_message(target["mailbox"], request)
    print("Sent, msg_id:", msg_id)

    await agent.close()

asyncio.run(main())
```

Agent B does not need to register to send messages. However, to receive results back from the executing agent, it must first create its own mailbox and include the callback address in the message headers — otherwise communication is one-way. If Agent B also wants to act as an executor and receive tasks from others, it builds its own `AgentCard` and calls `register()`.

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

### `agent.register`

Publish agent identity, create a mailbox, and start the consumer in the background. **Returns immediately** with the mailbox address.

Parameter: `agent_card` — `AgentCard` (from `a2a.types.a2a_pb2`). The `name` field is used as both the mailbox address and registry key.

Returns `str` — the mailbox address other agents use to send tasks here.

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
