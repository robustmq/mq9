---
title: Python SDK — mq9
description: mq9 Python SDK API reference and usage guide.
---

# Python SDK

## Install

```bash
pip install mq9
```

Requires Python 3.10+. The only runtime dependency is `nats-py`.

## Quick start

```python
import asyncio
from mq9 import Mq9Client, Priority

async def main():
    async with Mq9Client("nats://localhost:4222") as client:
        # Create a mailbox
        address = await client.mailbox_create(name="agent.inbox", ttl=3600)

        # Send a message
        await client.send(address, {"task": "analyze", "data": "..."})

        # Consume messages
        async def handler(msg):
            print(f"Received: {msg.payload}")

        consumer = await client.consume(address, handler, group_name="workers")
        await asyncio.sleep(10)
        await consumer.stop()

asyncio.run(main())
```

## Mq9Client

```python
Mq9Client(
    server: str,
    *,
    request_timeout: float = 5.0,
    reconnect_attempts: int = 5,
    reconnect_delay: float = 2.0,
)
```

Supports async context manager — `async with Mq9Client(...) as client`.

### connect / close

```python
await client.connect()
await client.close()
```

---

## Mailbox

### mailbox_create

```python
await client.mailbox_create(
    *,
    name: str | None = None,   # omit to let broker auto-generate
    ttl: int = 0,              # seconds; 0 = never expires
) -> str                       # returns mail_address
```

```python
address = await client.mailbox_create(name="agent.inbox", ttl=3600)
# auto-generated address
address = await client.mailbox_create(ttl=7200)
```

---

## Messaging

### send

```python
await client.send(
    mail_address: str,
    payload: bytes | str | dict,
    *,
    priority: Priority = Priority.NORMAL,
    key: str | None = None,        # dedup key — broker keeps only latest for same key
    delay: int | None = None,      # delay delivery N seconds
    ttl: int | None = None,        # message-level TTL in seconds
    tags: list[str] | None = None, # e.g. ["billing", "vip"]
) -> int                           # msg_id; -1 for delayed messages
```

```python
# Normal send
msg_id = await client.send("agent.inbox", {"task": "analyze"})

# Urgent priority
msg_id = await client.send("agent.inbox", b"alert", priority=Priority.URGENT)

# Dedup key — broker retains only the latest message for the same key
msg_id = await client.send("task.status", {"status": "running"}, key="state")

# Delayed delivery
msg_id = await client.send("agent.inbox", "hello", delay=60)

# With tags
msg_id = await client.send("orders.inbox", payload, tags=["billing", "vip"])
```

### fetch

```python
await client.fetch(
    mail_address: str,
    *,
    group_name: str | None = None,   # omit for stateless consumption
    deliver: str = "latest",         # "latest" | "earliest" | "from_time" | "from_id"
    from_time: int | None = None,    # unix timestamp, used with deliver="from_time"
    from_id: int | None = None,      # used with deliver="from_id"
    force_deliver: bool = False,     # reset offset and restart from deliver policy
    num_msgs: int = 100,
    max_wait_ms: int = 500,
) -> list[Message]
```

```python
# Stateless — each call starts fresh
messages = await client.fetch("task.inbox", deliver="earliest")

# Stateful — broker records offset per group
messages = await client.fetch("task.inbox", group_name="workers")

# After processing, ACK to advance offset
for msg in messages:
    await client.ack("task.inbox", "workers", msg.msg_id)
```

### ack

```python
await client.ack(
    mail_address: str,
    group_name: str,
    msg_id: int,
) -> None
```

### consume

Runs an automatic fetch loop in the background. Returns immediately.

```python
consumer = await client.consume(
    mail_address: str,
    handler: Callable[[Message], Awaitable[None]],
    *,
    group_name: str | None = None,
    deliver: str = "latest",
    num_msgs: int = 10,
    max_wait_ms: int = 500,
    auto_ack: bool = True,
    error_handler: Callable[[Message, Exception], Awaitable[None]] | None = None,
) -> Consumer
```

- If `handler` raises an exception the message is **not ACKed** (stays for retry).
- `error_handler=None` logs the error and continues the loop.

```python
async def handler(msg):
    data = json.loads(msg.payload)
    print(data)

async def on_error(msg, exc):
    print(f"Failed on msg {msg.msg_id}: {exc}")

consumer = await client.consume(
    "task.inbox",
    handler,
    group_name="workers",
    error_handler=on_error,
)

# Stop later
await consumer.stop()
print(consumer.processed_count)
```

### query

Inspect mailbox contents without affecting consumption offset.

```python
await client.query(
    mail_address: str,
    *,
    key: str | None = None,
    limit: int | None = None,
    since: int | None = None,   # unix timestamp
) -> list[Message]
```

### delete

```python
await client.delete(mail_address: str, msg_id: int) -> None
```

---

## Agent management

### agent_register

```python
await client.agent_register(agent_card: dict) -> None
```

`agent_card` must contain a `mailbox` field. The rest is upper-layer protocol content (e.g. A2A AgentCard).

```python
from a2a.types import AgentCard  # a2a python sdk

card = AgentCard(...).model_dump()
card["mailbox"] = f"mq9://broker/{address}"
await client.agent_register(card)
```

### agent_unregister

```python
await client.agent_unregister(mailbox: str) -> None
```

### agent_report

```python
await client.agent_report(report: dict) -> None
# report must contain "mailbox" field
```

### agent_discover

```python
await client.agent_discover(
    *,
    text: str | None = None,       # full-text keyword search
    semantic: str | None = None,   # semantic search (takes priority over text)
    limit: int = 20,
    page: int = 1,
) -> list[dict]
```

```python
# Find payment-related agents
agents = await client.agent_discover(text="payment invoice")

# Semantic search
agents = await client.agent_discover(semantic="process a refund request")

# List all
agents = await client.agent_discover()
```

---

## Data types

### Priority

```python
class Priority(str, Enum):
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"
```

Same-priority messages follow FIFO. Across priorities: `CRITICAL > URGENT > NORMAL`.

### Message

```python
@dataclass
class Message:
    msg_id: int
    payload: bytes
    priority: Priority
    create_time: int    # unix timestamp (seconds)
```

### Consumer

```python
class Consumer:
    is_running: bool
    processed_count: int
    async def stop(self) -> None
```

### Mq9Error

Raised when the broker returns a non-empty error field, or when the client is not connected.

```python
from mq9 import Mq9Error

try:
    await client.mailbox_create(name="agent.inbox")
except Mq9Error as e:
    print(e)  # "mailbox agent.inbox already exists"
```
