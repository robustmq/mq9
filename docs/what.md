---
title: What is mq9
description: mq9 — async messaging infrastructure for AI Agents. What it is, what it solves, and how it works.
---

# What is mq9

Running multiple Agents? They need to talk to each other. mq9 handles it — reliably, asynchronously, at any scale.

mq9 is async messaging infrastructure built specifically for Agent-to-Agent communication. Give each Agent a mailbox. Send messages to any Agent, online or not. Messages are stored and delivered when the recipient is ready. One binary to run, any NATS client to use.

## The eight scenarios mq9 solves

These are the communication patterns that come up in every multi-Agent system:

| # | Scenario | Description |
| - | - | - |
| 1 | Sub-Agent sends result back to parent | A parent Agent dispatches a task to a sub-Agent and needs the result back — asynchronously. The parent may restart between dispatching and receiving. The sub-Agent may finish while the parent is temporarily offline. |
| 2 | Orchestrator tracks real-time worker state | An orchestrator needs to know the current load, status, and health of dozens or hundreds of workers — in real time, not via polling. Workers update their state continuously. |
| 3 | Task broadcast, one worker picks it up | A task is published to a pool of workers. Exactly one worker should handle it — not zero, not two. Workers are interchangeable and the pool size changes dynamically. |
| 4 | Anomaly alert to all relevant handlers | A monitoring Agent detects a critical event and needs to notify multiple downstream handlers simultaneously — a logger, an incident responder, a dashboard updater. All of them, reliably. |
| 5 | Cloud sends command to offline edge device | A cloud Agent sends a high-priority command (e.g. emergency stop) to an edge device that is currently offline or on an unreliable network. The command must be waiting when the device reconnects, and must be processed before lower-priority messages. |
| 6 | Agent requests human approval before proceeding | An Agent reaches a decision point that requires human sign-off — e.g. spending money, calling an external API, taking an irreversible action. The human may not be available immediately. The Agent should not block. |
| 7 | Agent A asks offline Agent B a question | Agent A needs information from Agent B, but Agent B is offline, busy, or doesn't exist yet. Agent A should send the question and continue working. Agent B answers when it comes online. |
| 8 | Agent announces capabilities for discovery | A newly started Agent broadcasts what it can do — its skills, domains, task types. Orchestrators and other Agents subscribed to capability announcements learn about it and can start routing tasks to it immediately. |

## How teams solve these today — and where it breaks

### 1. Sub-Agent sends result to parent

**Today:** Parent opens an HTTP server and waits. Sub-Agent calls back when done. If the parent restarts mid-task, the callback has nowhere to go. If the sub-Agent finishes while the parent is restarting, the result is lost.

**The problem:** HTTP requires both sides to be online at the same time.

### 2. Orchestrator tracks worker states

**Today:** Workers write their state to a shared database. Orchestrator polls on an interval. The state you read is already stale. At 100 workers polling every second, the database becomes a bottleneck.

**The problem:** Polling is slow, noisy, and doesn't scale.

### 3. Task broadcast, one worker picks it up

**Today:** Put tasks in a Redis list, workers LPOP. Or use a Kafka topic with a consumer group. Redis has no delivery guarantees. Kafka requires setting up topics, partitions, and consumer groups before you can send a single message.

**The problem:** Too much infrastructure for a simple "one worker handles one task" pattern.

### 4. Anomaly alert to all handlers

**Today:** Redis pub/sub. Works — until a handler is offline when the alert fires. The message is gone. You add persistence, now you're managing Redis Streams and consumer group offsets.

**The problem:** Pub/sub with no persistence is fire-and-forget. Adding persistence adds complexity.

### 5. Cloud command to offline edge device

**Today:** Store commands in a database. Edge device polls on reconnect and queries for pending commands. You write the polling logic, the query logic, the ordering logic. Every team writes this from scratch.

**The problem:** There's no standard "store-and-deliver-when-online" primitive.

### 6. Human-in-the-loop approval

**Today:** Agent sends an email or Slack message to a human. Human replies. A separate webhook or listener routes the reply back to the Agent. Now you're maintaining three integration points.

**The problem:** Humans and Agents are treated as different protocol citizens. They shouldn't be.

### 7. Agent A asks offline Agent B

**Today:** Agent A retries the request until Agent B comes online. Retry loops with backoff, timeout handling, state tracking. Or: drop the message and accept data loss.

**The problem:** No async request-reply primitive. You either block or you lose.

### 8. Capability discovery

**Today:** Hardcode which Agent handles which task. Or maintain a service registry. Either a config file that goes stale, or a separate registry service to build and operate.

**The problem:** Dynamic Agent discovery requires infrastructure that doesn't exist off the shelf.

## Why a mailbox?

Agents are not services. A service runs continuously and holds a stable address. An Agent spins up for a task, does its work, and disappears. Its identity is temporary. Its communication needs are temporary too.

This changes how you should think about addressing. A permanent address assigned to an ephemeral process is a mismatch — the address outlives the Agent, or worse, gets reused in ways that cause confusion. The right model is different: **communication should be scoped to the task, not the Agent.**

In mq9, an Agent requests a mailbox whenever it needs one. For each task, for each communication concern, create a mailbox. Share the `mail_id` with whoever needs to reach you. When the task ends, let the mailbox expire — it cleans itself up automatically via TTL. No deregistration, no cleanup code, no lingering state.

This means:

- An Agent handling five parallel tasks can have five mailboxes — one per task, completely isolated.
- An Agent can have separate mailboxes for task assignments, status broadcasts, and capability announcements.
- When an Agent restarts, it creates a fresh mailbox. Old messages don't bleed into a new execution context.

Mailboxes are cheap. Request as many as you need. The lifecycle is automatic. This is not a workaround — it's a design decision built around how Agents actually behave.

## With mq9

Every Agent gets a **mailbox** — temporary, task-scoped, built for how Agents actually work.

```text
$mq9.AI.MAILBOX.CREATE              → create a mailbox, get a mail_id
$mq9.AI.INBOX.{mail_id}.{priority}  → send to an agent (stored if offline)
$mq9.AI.BROADCAST.{domain}.{event}  → publish to all subscribers
$mq9.AI.MAILBOX.QUERY.{mail_id}     → pull missed messages on reconnect
```

The same four commands handle all eight scenarios:

| Scenario | How mq9 handles it |
| - | - |
| Sub-Agent result to parent | `INBOX.normal` + `reply_to` field |
| Orchestrator tracks workers | Workers use `latest`-type mailbox, orchestrator subscribes once |
| Task to one worker | `BROADCAST` + queue group subscription |
| Alert to all handlers | `BROADCAST` + wildcard subscription |
| Command to offline edge | `INBOX.urgent`, edge queries with `MAILBOX.QUERY` on reconnect |
| Human approval | Human and Agent both use `INBOX` — same protocol |
| Async request-reply | `INBOX` + `correlation_id` + `reply_to` |
| Capability discovery | `BROADCAST.system.capability` on startup |

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

mq9 runs over NATS. Go, Python, Rust, Java, JavaScript, .NET — any NATS client is already an mq9 client.

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
