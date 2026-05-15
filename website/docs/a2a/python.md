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
from a2a.helpers import new_text_artifact, new_text_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types.a2a_pb2 import (
    AgentCard, AgentCapabilities, AgentSkill,
    TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent,
)
from mq9.a2a import Mq9A2AAgent

agent = Mq9A2AAgent()  # defaults to public debug server

@agent.on_message(group_name="demo.agent.translator.workers", deliver="earliest", num_msgs=10, max_wait_ms=500)
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    # The following follows the A2A protocol's standard event sequence: WORKING → Artifact → COMPLETED

    # A2A protocol: send WORKING first to tell the sender processing has started.
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    ))

    # A2A protocol: a Message consists of one or more Parts (text / data / file).
    # Extract the text content from the first Part.
    text = context.message.parts[0].text if context.message.parts else ""
    result = my_translate(text)  # your logic here

    # A2A protocol: push result as an Artifact — call multiple times for streaming.
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        artifact=new_text_artifact(name="translation", text=result),
    ))
    # A2A protocol: send COMPLETED last to signal the task is done.
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

# All messages arrive here — both reply events and new incoming tasks.
# Use context.task_id to tell them apart: match it against a task_id you sent
# to identify a reply; anything else is a new incoming task.
@agent_b.on_message(group_name="demo.agent.sender.workers", deliver="earliest", num_msgs=10, max_wait_ms=500)
async def handle_incoming(context: RequestContext, _: EventQueue) -> None:
    text = context.message.parts[0].text if context.message.parts else ""
    print(f"Message received task_id={context.task_id}: {text}")
    # Business logic holds the task_id and decides what this message means.

card_b = AgentCard(
    name="demo.agent.sender",
    description="Demo sender agent",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
)

async def main():
    await agent_b.connect()
    b_mailbox = await agent_b.create_mailbox(card_b.name)
    await agent_b.register(card_b)

    results = await agent_b.discover("translation agent")
    target = results[0]

    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )

    # With reply_to, returns (msg_id, task_id).
    # The framework stamps task_id on every reply event — readable via context.task_id.
    msg_id, task_id = await agent_b.send_message(target["mailbox"], request, reply_to=b_mailbox)
    print(f"Sent, msg_id={msg_id}, task_id={task_id}")

    # Wait for the reply to arrive via @on_message above.
    await asyncio.sleep(10)

    await agent_b.unregister()
    await agent_b.close()

asyncio.run(main())
```

`send_message` with `reply_to` returns `(msg_id, task_id)`. The framework stamps `task_id` on every reply event so your `@on_message` handler can read it from `context.task_id`. All messages — replies and new incoming tasks — arrive in the same handler; business logic decides what each `task_id` means.

---

## Mq9A2AAgent

```python
Mq9A2AAgent(*, server: str = "nats://demo.robustmq.com:4222", request_timeout: float = 60)
```

| Parameter | Type | Description |
| --- | --- | --- |
| `server` | `str` | mq9 broker NATS URL. Defaults to the public debug server `nats://demo.robustmq.com:4222` — can be omitted during development |
| `request_timeout` | `float` | Default timeout for outbound requests in seconds |

### `agent.connect`

Connect to the broker. Required before any operation.

### `agent.close`

Stop consuming messages and disconnect from the broker. Call this after the backlog is drained.

### `@agent.on_message`

Decorator — registers the async message handler. Consumer options can be set here:

```python
# plain
@agent.on_message
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    ...

# with consumer options
@agent.on_message(group_name="my-group", num_msgs=20)
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    ...
```

| Parameter | Description |
| --- | --- |
| `group_name` | Consumer group name. Defaults to `{mailbox}.workers` — ensures consumption resumes from the last offset after a restart |
| `deliver` | Where to start: `"earliest"` (default) resumes from last offset, `"latest"` only receives new messages |
| `num_msgs` | Number of messages to fetch per poll, default `10` |
| `max_wait_ms` | Max wait per fetch when no messages are available, milliseconds, default `500` |

### `agent.create_mailbox`

Create a mailbox and start the consumer in the background. **Returns immediately** with the mailbox address.

| Parameter | Description |
| --- | --- |
| `name` | Mailbox name, typically `AgentCard.name` |
| `ttl` | Mailbox TTL in seconds (`0` = permanent, default) |

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
| `reply_to` | Your own mailbox address. When set, the framework generates a `task_id` and stamps it on every reply event — readable as `context.task_id` in your `@on_message` handler |

- Without `reply_to`: returns `int` (`msg_id` assigned by the broker)
- With `reply_to`: returns `(msg_id, task_id)` — hold onto `task_id` to identify replies in your handler

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
