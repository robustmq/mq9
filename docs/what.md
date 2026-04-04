---
title: What is mq9
description: mq9 — async messaging infrastructure for AI Agents. What it is, what it solves, and how it works.
---

# What is mq9

Running multiple Agents? They need to talk to each other. mq9 handles it — reliably, asynchronously, at any scale.

mq9 is async messaging infrastructure built specifically for Agent-to-Agent communication. Give each Agent a mailbox. Send messages to any Agent, online or not. Messages are stored and delivered when the recipient is ready. One binary to run, any NATS client to use.

## The eight scenarios mq9 solves

### 1. Sub-Agent sends result to parent {#scenario-1}

**Today:** Parent opens an HTTP server and waits. Sub-Agent calls back when done. If the parent restarts mid-task, the callback has nowhere to go. If the sub-Agent finishes while the parent is restarting, the result is lost.

**The problem:** HTTP requires both sides to be online at the same time.

**With mq9:** Sub-Agent publishes to `INBOX.{parent_id}.normal` with a `correlation_id`. Parent subscribes to its inbox — messages arrive whether the parent was online or not. No HTTP server, no retry logic.

### 2. Orchestrator tracks real-time worker state {#scenario-2}

**Today:** Workers write their state to a shared database. Orchestrator polls on an interval. The state you read is already stale. At 100 workers polling every second, the database becomes a bottleneck.

**The problem:** Polling is slow, noisy, and doesn't scale.

**With mq9:** Each worker creates a `latest`-type mailbox and publishes its state continuously. The orchestrator subscribes once to `INBOX.m-status-*.normal` — always sees the current state, never a history. When a worker's TTL expires, its state disappears. The orchestrator knows it's gone.

### 3. Task broadcast, one worker picks it up {#scenario-3}

**Today:** Put tasks in a Redis list, workers LPOP. Or use a Kafka topic with a consumer group. Redis has no delivery guarantees. Kafka requires setting up topics, partitions, and consumer groups before you can send a single message.

**The problem:** Too much infrastructure for a simple "one worker handles one task" pattern.

**With mq9:** Publish to `BROADCAST.task.available`. All workers subscribe with the same queue group name. Each task goes to exactly one worker. No coordination, no duplicate processing, no infrastructure to configure.

### 4. Anomaly alert to all handlers {#scenario-4}

**Today:** Redis pub/sub. Works — until a handler is offline when the alert fires. The message is gone. You add persistence, now you're managing Redis Streams and consumer group offsets.

**The problem:** Pub/sub with no persistence is fire-and-forget. Adding persistence adds complexity.

**With mq9:** Publish to `BROADCAST.system.anomaly`. Any Agent subscribed with a wildcard (`BROADCAST.system.*`) receives it. Handlers that were offline get the message when they reconnect via `MAILBOX.QUERY`. Persistence is built in — no extra configuration.

### 5. Cloud sends command to offline edge device {#scenario-5}

**Today:** Store commands in a database. Edge device polls on reconnect and queries for pending commands. You write the polling logic, the query logic, the ordering logic. Every team writes this from scratch.

**The problem:** There's no standard "store-and-deliver-when-online" primitive.

**With mq9:** Cloud publishes to `INBOX.{edge_id}.urgent`. mq9 stores it. Edge device reconnects, subscribes to its inbox, and gets all pending messages — urgent first. One `MAILBOX.QUERY` call as a fallback safety net. No custom polling code.

### 6. Agent requests human approval before proceeding {#scenario-6}

**Today:** Agent sends an email or Slack message to a human. Human replies. A separate webhook or listener routes the reply back to the Agent. Now you're maintaining three integration points.

**The problem:** Humans and Agents are treated as different protocol citizens. They shouldn't be.

**With mq9:** The Agent sends an approval request to the human's `mail_id` via `INBOX.urgent`, with a `reply_to` address. The human's client subscribes to their inbox — same protocol, same client. Human replies directly. No webhooks, no routing middleware.

### 7. Agent A asks offline Agent B a question {#scenario-7}

**Today:** Agent A retries the request until Agent B comes online. Retry loops with backoff, timeout handling, state tracking. Or: drop the message and accept data loss.

**The problem:** No async request-reply primitive. You either block or you lose.

**With mq9:** Agent A publishes a question to `INBOX.{agent_b}.normal` with a `correlation_id` and `reply_to` set to its own inbox. Agent A continues working. Agent B comes online, processes the question, replies to `reply_to`. Agent A collects the answer when it arrives. No blocking, no retries.

### 8. Agent announces capabilities for discovery {#scenario-8}

**Today:** Hardcode which Agent handles which task. Or maintain a service registry. Either a config file that goes stale, or a separate registry service to build and operate.

**The problem:** Dynamic Agent discovery requires infrastructure that doesn't exist off the shelf.

**With mq9:** Agent publishes to `BROADCAST.system.capability` on startup with its skill list and `reply_to` address. Orchestrators subscribed to this channel build a live index. When an Agent goes offline (TTL expires), it disappears from the index naturally. No registry to maintain.

## Why a mailbox?

Agents are not services. A service runs continuously and holds a stable address. An Agent spins up for a task, does its work, and disappears. Its identity is temporary. Its communication needs are temporary too.

This changes how you should think about addressing. A permanent address assigned to an ephemeral process is a mismatch — the address outlives the Agent, or worse, gets reused in ways that cause confusion. The right model is different: **communication should be scoped to the task, not the Agent.**

In mq9, an Agent requests a mailbox whenever it needs one. For each task, for each communication concern, create a mailbox. Share the `mail_id` with whoever needs to reach you. When the task ends, let the mailbox expire — it cleans itself up automatically via TTL. No deregistration, no cleanup code, no lingering state.

This means:

- An Agent handling five parallel tasks can have five mailboxes — one per task, completely isolated.
- An Agent can have separate mailboxes for task assignments, status broadcasts, and capability announcements.
- When an Agent restarts, it creates a fresh mailbox. Old messages don't bleed into a new execution context.

Mailboxes are cheap. Request as many as you need. The lifecycle is automatic. This is not a workaround — it's a design decision built around how Agents actually behave.

## How it works

Every Agent gets a **mailbox** — temporary, task-scoped, built for how Agents actually work.

```text
$mq9.AI.MAILBOX.CREATE              → create a mailbox, get a mail_id
$mq9.AI.INBOX.{mail_id}.{priority}  → send to an agent (stored if offline)
$mq9.AI.BROADCAST.{domain}.{event}  → publish to all subscribers
$mq9.AI.MAILBOX.QUERY.{mail_id}     → pull missed messages on reconnect
```

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

### Store-first delivery

When a message arrives, mq9 writes it to storage first, then checks if the recipient is online:

- **Online** → delivered immediately
- **Offline** → stored, delivered on reconnect. `MAILBOX.QUERY` as a fallback safety net.

### Priority

```text
$mq9.AI.INBOX.{mail_id}.urgent    → processed first
$mq9.AI.INBOX.{mail_id}.normal    → standard
$mq9.AI.INBOX.{mail_id}.notify    → background, shorter TTL
```

An edge device coming back online processes `urgent` first — the emergency stop sent hours ago is not buried under routine updates.

### Mailbox types

| Type | Behavior | Use case |
| - | - | - |
| `standard` | Keeps all messages | Task requests, results, approvals |
| `latest` | Keeps only the newest | Status updates, current state |

### No new SDK

mq9 runs over NATS. Any NATS client — Go, Python, Rust, JavaScript — is already an mq9 client. No new library to install.

```python
# Python — three lines to send a message
import nats, json, asyncio
nc = await nats.connect("nats://localhost:4222")
await nc.publish("$mq9.AI.INBOX.m-target-001.normal",
    json.dumps({"from": "m-uuid-001", "type": "task", "payload": {"data": "..."}}).encode())
```

## Quick start

```bash
# Run mq9
docker run -d -p 4222:4222 robustmq/robustmq:latest

# Create a mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"standard","ttl":3600}'
# → {"mail_id":"m-uuid-001","token":"tok-xxx"}

# Send a message
nats publish '$mq9.AI.INBOX.m-uuid-001.normal' '{"from":"me","payload":"hello"}'

# Subscribe
nats subscribe '$mq9.AI.INBOX.m-uuid-001.*'
```

See [For Engineer](/for-engineer) for full integration code in Python, Go, and JavaScript.

## How mq9 fits in your stack

**vs. raw NATS** — NATS is fire-and-forget pub/sub. mq9 adds persistent mailboxes and store-first delivery on top of NATS. Same client, different guarantees.

**vs. NATS JetStream** — JetStream gives you streams and consumers (Kafka-like). mq9 gives you mailboxes and broadcasts (email-like). Different abstractions for different problems.

**vs. Kafka** — Kafka is a high-throughput ordered log optimized for data pipelines. mq9 is optimized for ephemeral Agents exchanging small messages. Don't use mq9 as a data pipeline.

**vs. A2A (Google's Agent2Agent)** — A2A defines how Agents negotiate tasks at the application layer. mq9 handles reliable delivery at the transport layer. They're complementary — A2A can run over mq9.

**What mq9 is not:**
- Not a replacement for HTTP/gRPC between always-online services
- Not a data pipeline
- Not an orchestration framework — it moves messages, not decisions

*See [For Agent](/for-agent) to understand how Agents use mq9. See [For Engineer](/for-engineer) for integration code.*
