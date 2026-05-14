# mq9 Python SDK

Async Python client for the mq9 NATS-based Agent messaging broker.

## Requirements

- Python 3.10+
- [nats-py](https://github.com/nats-io/nats.py) >= 2.6.0

## Installation

```bash
pip install .
```

## Quick start

```python
import asyncio
from mq9 import Mq9Client, Priority

async def main():
    async with Mq9Client("nats://localhost:4222") as client:
        # Create a mailbox
        address = await client.mailbox_create(name="agent.inbox", ttl=3600)

        # Send a message
        msg_id = await client.send(address, b"hello world", priority=Priority.URGENT)

        # Fetch messages
        messages = await client.fetch(address, group_name="workers", num_msgs=10)
        for msg in messages:
            print(msg.msg_id, msg.payload)
            await client.ack(address, "workers", msg.msg_id)

        # Background consumer
        async def handler(msg):
            print("received:", msg.payload)

        consumer = await client.consume(address, handler, group_name="workers", auto_ack=True)
        await asyncio.sleep(5)
        await consumer.stop()

asyncio.run(main())
```

## API reference

### `Mq9Client(server, *, request_timeout, reconnect_attempts, reconnect_delay)`

| Method | Description |
|--------|-------------|
| `connect()` | Connect to the NATS server |
| `close()` | Drain and close the connection |
| `mailbox_create(*, name, ttl)` | Create a mailbox; returns `mail_address` |
| `send(mail_address, payload, *, priority, key, delay, ttl, tags)` | Send a message; returns `msg_id` |
| `fetch(mail_address, *, group_name, deliver, from_time, from_id, force_deliver, num_msgs, max_wait_ms)` | Fetch messages |
| `ack(mail_address, group_name, msg_id)` | Acknowledge a message |
| `consume(mail_address, handler, *, group_name, deliver, num_msgs, max_wait_ms, auto_ack, error_handler)` | Start background consumer; returns `Consumer` |
| `query(mail_address, *, key, limit, since)` | Query messages |
| `delete(mail_address, msg_id)` | Delete a message |
| `agent_register(agent_card)` | Register an agent |
| `agent_unregister(mailbox)` | Unregister an agent |
| `agent_report(report)` | Report agent status |
| `agent_discover(*, text, semantic, limit, page)` | Discover agents |

### `Consumer`

| Attribute / Method | Description |
|--------------------|-------------|
| `is_running` | `True` while the consume loop is active |
| `processed_count` | Number of messages successfully handled |
| `stop()` | Cancel the loop and wait for it to finish |

### `Priority`

`Priority.NORMAL`, `Priority.URGENT`, `Priority.CRITICAL`

### `Mq9Error`

Raised when the broker returns a non-empty `error` field.

## Running tests

```bash
pip install ".[dev]"
pytest
```
