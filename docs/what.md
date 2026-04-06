---
title: What is mq9
description: mq9 — async messaging infrastructure for AI Agents. What it is, what it solves, and how it works.
---

# What is mq9

mq9 is the mailbox for AI Agents. A self-hosted broker built specifically for Agent-to-Agent communication — persistent, async, priority delivery. Deploy once, every Agent gets a mailbox.

## Why a mailbox?

Agents are not services. A service runs continuously and holds a stable address. An Agent spins up for a task, does its work, and disappears. Its identity is temporary. Its communication needs are temporary too.

In mq9, an Agent requests a mailbox whenever it needs one. The `mail_id` is its address for that task. When the task ends, let the mailbox expire — it cleans itself up automatically via TTL. No deregistration, no cleanup code, no lingering state.

**mail_id unguessability is the security boundary.** The `mail_id` is a system-generated unguessable string. Know the `mail_id` and you can send to it, subscribe to it. Don't know it — you can't touch it. No tokens, no ACL, no auth layer.

An Agent handling five parallel tasks can have five mailboxes — one per task, completely isolated.

## The eight scenarios mq9 solves

### 1. Sub-Agent sends result to parent

**Today:** Parent opens an HTTP server and waits. If the parent restarts mid-task, the callback has nowhere to go. Result lost.

**The problem:** HTTP requires both sides to be online at the same time.

**With mq9:** Sub-Agent publishes to the parent's mailbox with a `correlation_id`. Parent subscribes to its mailbox — all messages that arrived while it was offline are pushed immediately on subscribe. No HTTP server, no retry logic.

### 2. Orchestrator tracks real-time worker state

**Today:** Workers write their state to a shared database. Orchestrator polls on an interval. At 100 workers polling every second, the database becomes a bottleneck.

**The problem:** Polling is slow, noisy, and doesn't scale.

**With mq9:** Each worker creates a public mailbox and publishes its state continuously. Orchestrator subscribes — always sees the current state. When a worker's mailbox TTL expires, it disappears from PUBLIC.LIST. Orchestrator knows it's gone.

### 3. Task broadcast, one worker picks it up

**Today:** Put tasks in a Redis list, workers LPOP. Or use a Kafka topic with a consumer group. Too much infrastructure for a simple "one worker handles one task" pattern.

**The problem:** No lightweight competing-consumer primitive.

**With mq9:** Create a public mailbox for the task queue. All workers subscribe with the same queue group name. Each task goes to exactly one worker. No coordination, no duplicate processing.

### 4. Anomaly alert to all handlers

**Today:** Redis pub/sub — until a handler is offline when the alert fires. Message gone.

**The problem:** Pub/sub with no persistence is fire-and-forget.

**With mq9:** Create a public mailbox for alerts. Any Agent subscribed gets it in real-time. Handlers that were offline receive all unexpired alerts the moment they subscribe. No messages lost within TTL window.

### 5. Cloud sends command to offline edge device

**Today:** Store commands in a database. Edge device polls on reconnect and queries for pending commands. Every team writes this from scratch.

**The problem:** There's no standard "store-and-deliver-when-online" primitive.

**With mq9:** Cloud publishes to the edge device's mailbox with `high` priority. mq9 stores it. Edge device reconnects, subscribes to its mailbox — all pending messages pushed immediately, high priority first.

### 6. Agent requests human approval before proceeding

**Today:** Agent sends an email or Slack message. A webhook routes the reply back. Three integration points to maintain.

**The problem:** Humans and Agents are treated as different protocol citizens.

**With mq9:** Agent sends an approval request to the human's mailbox with `reply_to` set. The human's client subscribes to their mailbox — same protocol, same NATS client. Human replies directly. No webhooks, no routing middleware.

### 7. Agent A asks offline Agent B a question

**Today:** Agent A retries until Agent B comes online. Retry loops, timeout handling, state tracking. Or: drop the message and accept data loss.

**The problem:** No async request-reply primitive.

**With mq9:** Agent A publishes a question to Agent B's mailbox with `correlation_id` and `reply_to` set to its own mailbox. Agent A continues working. Agent B comes online, gets the question from its mailbox, replies. Agent A collects the answer when it arrives. No blocking, no retries.

### 8. Agent announces capabilities for discovery

**Today:** Hardcode which Agent handles which task. Or maintain a service registry — a config file that goes stale, or a separate registry service to build.

**The problem:** Dynamic Agent discovery requires infrastructure that doesn't exist off the shelf.

**With mq9:** Agent creates a public mailbox on startup with a meaningful name like `agent.analysis.v1`. It's automatically registered to `$mq9.AI.PUBLIC.LIST`. Orchestrators subscribe to PUBLIC.LIST — they see all public mailboxes in real-time. When an Agent's mailbox TTL expires, it disappears from PUBLIC.LIST automatically. No registry to maintain.

## How it works

Every Agent gets a **mailbox** — temporary, task-scoped, built for how Agents actually work.

```python
mailbox.create(ttl=3600)                           # create a mailbox
mailbox.send(mail_id, payload, priority="normal")  # send a message
mailbox.receive(mail_id)                           # receive messages
mailbox.fetch(mail_id)                             # fetch mailbox contents
mailbox.delete(mail_id, msg_id)                    # delete a message
mailbox.list()                                     # discover public mailboxes
```

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

### Store-first delivery

When a message arrives, mq9 writes it to storage first, then checks if the recipient is online:

- **Online** → delivered immediately
- **Offline** → stored, delivered on next subscribe

Subscribe = full push. Every subscription delivers all unexpired messages immediately, then streams new arrivals in real-time. No separate QUERY command needed.

### Priority

```text
high    → processed first
normal  → standard
low     → background
```

An edge device coming back online after 8 hours processes `high` first — the emergency stop sent hours ago is not buried under routine updates.

### Private and public mailboxes

**Private mailbox** — `mail_id` is system-generated, unguessable. Share it with whoever needs to reach you. Used for point-to-point communication and task result delivery.

**Public mailbox** — `mail_id` is user-defined, meaningful name. Created with `public=True`. Automatically registered to PUBLIC.LIST. Used for task queues, capability announcements, shared channels.

```python
# Private mailbox
mailbox.create(ttl=3600)
# → {"mail_id": "m-uuid-001"}

# Public mailbox — auto-registered to PUBLIC.LIST
mailbox.create(ttl=3600, public=True, name="task.queue", desc="main task queue")
# → {"mail_id": "task.queue"}
```

### Discover public mailboxes

PUBLIC.LIST is broker-maintained. Subscribe once — all current public mailboxes pushed immediately, new ones pushed as they're created, expired ones pushed as they're removed.

```python
mailbox.list()
```

No registry service. PUBLIC.LIST is the directory.

### Official SDKs

mq9 provides official SDKs for Python, Go, and JavaScript.

```bash
pip install mq9
npm install mq9
go get github.com/robustmq/mq9
```

## Quick start

```bash
# Run mq9
docker run -d -p 4222:4222 robustmq/robustmq:latest

# Install SDK
pip install mq9
```

```python
from mq9 import Mailbox

m = Mailbox(server="localhost:4222")

# Create a mailbox
box = m.create(ttl=3600)          # → {"mail_id": "m-uuid-001"}

# Send a message
m.send(box["mail_id"], {"type": "task", "payload": "hello"})

# Receive — all unexpired messages pushed immediately, then realtime
for msg in m.receive(box["mail_id"]):
    print(msg)
```

See [For Engineer](/for-engineer) for full integration code in Python, Go, and JavaScript.

## How mq9 fits in your stack

**vs. raw NATS** — NATS Core is fire-and-forget pub/sub. mq9 adds persistent mailboxes and store-first delivery on top of NATS. Same client, different guarantees.

**vs. NATS JetStream** — JetStream gives you streams and consumers (Kafka-like). mq9 gives you mailboxes (email-like). Different abstractions for different problems. mq9 is lighter — no stream, no consumer group, no offset management.

**vs. Kafka** — Kafka is a high-throughput ordered log optimized for data pipelines. mq9 is optimized for ephemeral Agents exchanging small messages. Don't use mq9 as a data pipeline.

**vs. A2A (Google's Agent2Agent)** — A2A defines how Agents negotiate tasks at the application layer. mq9 handles reliable delivery at the transport layer. They're complementary — A2A can run over mq9.

**What mq9 is not:**

- Not a replacement for HTTP/gRPC between always-online services
- Not a data pipeline
- Not an orchestration framework — it moves messages, not decisions

*See [For Agent](/for-agent) to understand how Agents use mq9. See [For Engineer](/for-engineer) for integration code.*
