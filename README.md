# mq9

The mailbox for AI Agents.

Running multiple Agents? They need to talk to each other. mq9 handles it — reliably, asynchronously, at any scale.

mq9 is a self-hosted async messaging broker built specifically for Agent-to-Agent communication. Deploy once, every Agent gets a mailbox. Send to any Agent, online or offline — mq9 stores it and delivers when they're back.

---

## Why mq9

| Need | HTTP | Redis pub/sub | Kafka | mq9 |
| ---- | ---- | ------------- | ----- | --- |
| Agent offline when message arrives | Lost | Lost | Complex setup | Stored, auto-delivered |
| Many ephemeral Agents | OK | OK | Wasteful | Native fit |
| One-to-one async delivery | OK | Workaround | Workaround | Native |
| Broadcast to unknown subscribers | No | Fire-and-forget | Topic | Public mailbox |
| Auto-cleanup, no manual management | No | TTL hack | No | Built-in TTL |
| Self-hosted, single binary | Yes | Yes | Heavy | Yes |

---

## API

Six operations. That's the entire protocol.

```python
mb.create(ttl=3600)                              # create a mailbox
mb.send(mail_id, payload, priority="normal")     # send a message
mb.receive(mail_id)                              # receive messages (all unexpired + realtime)
mb.fetch(mail_id)                                # fetch mailbox contents
mb.delete(mail_id, msg_id)                       # delete a message
mb.list()                                        # discover public mailboxes
```

### Quick start

```bash
docker run -d --name mq9 -p 4222:4222 mq9/mq9:latest
pip install mq9
```

```python
from mq9 import Mailbox

mb = Mailbox("nats://localhost:4222")

# Create mailboxes
agent_a = mb.create(ttl=3600)   # → {"mail_id": "m-uuid-001"}
agent_b = mb.create(ttl=3600)   # → {"mail_id": "m-uuid-002"}

# Agent A sends to Agent B (even if B is offline)
mb.send(agent_b["mail_id"], {
    "from": agent_a["mail_id"],
    "type": "task",
    "payload": "analyze this"
})

# Agent B subscribes — gets all pending messages immediately, then realtime
mb.receive(agent_b["mail_id"], callback=lambda msg: print(msg))
```

### Priority

```text
high    → processed first
normal  → standard
low     → background
```

### Private and public mailboxes

**Private** — `mail_id` is system-generated and unguessable. Share it with whoever needs to reach you. Security boundary: knowing the `mail_id` is the only credential needed.

**Public** — user-defined name, auto-registered to PUBLIC.LIST. Used for task queues, capability announcements, broadcast channels.

```python
# Public mailbox — discoverable via mb.list()
mb.create(ttl=86400, public=True, name="task.queue", desc="main task queue")

# Competing workers — only one Agent handles each message
mb.receive("task.queue", resume="workers", callback=handle_task)
```

---

## Eight scenarios mq9 solves

1. **Sub-Agent reports result to parent** — Parent may be sleeping. Message waits, delivered on reconnect.
2. **Orchestrator tracks worker state** — Workers create public mailboxes, orchestrator subscribes. TTL expiry = offline signal.
3. **Task broadcast, one worker picks it up** — Public mailbox + resume group. No coordination needed.
4. **Alert to all handlers** — Public mailbox. Handlers that were offline get all unexpired alerts on reconnect.
5. **Cloud to offline edge device** — Send with `high` priority. Edge reconnects, gets it first.
6. **Human-in-the-loop approval** — Send to human's mailbox. Human replies with same SDK. No webhooks.
7. **Async request-reply** — Send with `reply_to`. Recipient replies when ready. No blocking, no retries.
8. **Capability discovery** — Create a public mailbox on startup. Orchestrators subscribe to `mb.list()`. TTL expiry removes you automatically.

---

## How it works

**Store-first delivery.** When a message arrives, mq9 writes it to storage first, then checks if the recipient is online:

- Online → delivered immediately
- Offline → stored, delivered on next `mb.receive()`

`mb.receive()` = full push. All unexpired messages are pushed immediately when you subscribe, then new arrivals stream in real-time. No separate pull needed.

---

## Relationship to other tools

**vs. raw NATS** — NATS Core is fire-and-forget. mq9 adds persistent mailboxes and store-first delivery.

**vs. NATS JetStream** — JetStream is streams and consumers (Kafka-like). mq9 is mailboxes (email-like). Lighter — no stream config, no offset management.

**vs. Kafka** — Kafka is a high-throughput ordered log for data pipelines. mq9 is for ephemeral Agents exchanging small messages.

**vs. A2A (Google's Agent2Agent)** — A2A defines application-layer task negotiation. mq9 handles transport-layer delivery. They're complementary — A2A can run over mq9.

---

## Status

mq9 is under active development as part of [RobustMQ](https://github.com/robustmq/robustmq).

- Protocol design: complete
- Core operations implemented and validated
- Production hardening: in progress

mq9 is the fifth native protocol in RobustMQ, alongside MQTT, Kafka, NATS, and AMQP.

RobustMQ repository: [github.com/robustmq/robustmq](https://github.com/robustmq/robustmq)
