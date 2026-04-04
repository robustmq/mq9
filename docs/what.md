---
title: What is mq9
description: The design philosophy behind mq9 — why Agents need a different communication layer.
---

# What is mq9

mq9 is a communication layer designed specifically for AI Agents. Not a new message queue. Not a wrapper around Kafka. A protocol that treats Agents as the primary actor — temporary, offline-capable, ephemeral.

## The problem nobody solved yet

Agent A finishes a task and sends the result to Agent B. Agent B is offline. The message is lost.

This is the default behavior of HTTP. Redis pub/sub. Even raw NATS. None of them were built for Agents — they were built for services. Services are always online. Agents are not.

Today, every team building multi-Agent systems solves this differently. Some poll a shared database. Some use Redis Streams with manual consumer groups. Some build their own queue. None of it is standard. None of it is simple. And all of it breaks when Agents scale from 10 to 10,000.

## Why existing solutions don't fit

| | HTTP | Redis | Kafka | mq9 |
| - | - | - | - | - |
| Agent offline when message arrives | Lost | Lost | Survives (complex) | Survives, auto-delivered |
| Many Agents, small messages | OK | OK | Wasteful | Native fit |
| One-to-one async delivery | OK | Workaround | Workaround | Native |
| Broadcast to unknown subscribers | No | Pub/sub | Topic | Native |
| Auto-cleanup, no manual management | No | TTL hack | No | Built-in TTL |
| No new SDK required | — | — | — | Yes |

**HTTP** assumes both parties are online. One goes down, the request fails.

**Redis** has pub/sub but no persistence. Offline = message lost. Adding Redis Streams brings consumer group complexity that wasn't designed for ephemeral Agents.

**Kafka** is optimized for high-throughput ordered logs. Agents are temporary — they spin up for a task and disappear. Topics are permanent. The mismatch is fundamental.

## The mailbox model

The right mental model is email, not RPC.

When you send someone an email, you don't need them to be online. The message goes to their mailbox. They read it when they're available. You don't know when that will be. You don't need to know.

Agents work the same way. mq9 gives each Agent a mailbox.

- **Send a letter** → `INBOX.{mail_id}.{priority}` — recipient offline? Stored. Online? Delivered.
- **Open your mailbox** → Subscribe to `$mq9.AI.INBOX.{mail_id}.*` — get pushed messages as they arrive, pull missed ones with `MAILBOX.QUERY` as fallback.
- **Post to a bulletin board** → `BROADCAST.{domain}.{event}` — publish once, any subscriber receives it. You don't manage the audience.
- **Mailbox expires automatically** — TTL-based cleanup. No manual deletion.

## Four commands

mq9 exposes four commands over NATS subjects. That's the entire protocol.

```text
$mq9.AI.MAILBOX.CREATE              → create a mailbox, get a mail_id
$mq9.AI.MAILBOX.QUERY.{mail_id}     → pull unread messages (fallback)
$mq9.AI.INBOX.{mail_id}.{priority}  → point-to-point delivery
$mq9.AI.BROADCAST.{domain}.{event}  → one-to-many broadcast
```

These four commands cover every async Agent communication pattern. The [For Agent](/for-agent) page maps eight real scenarios to these four commands.

## Key design decisions

### mail_id is not identity

A `mail_id` is a communication channel, not an Agent's identity. One Agent can create multiple mailboxes — one for task assignments, one for status broadcasts, one for capability declarations.

This decouples communication from identity. Agents don't persist their address. Create for a task, let it expire with the task.

### Two mailbox types

| Type | Behavior | Use case |
| - | - | - |
| `standard` | Accumulates all messages | Task requests, results, notifications |
| `latest` | Keeps only the newest message | Status updates, state snapshots |

A worker reporting its current load should use `latest` — you always want the current state, not a history of state changes.

### Store first, push second

When a message arrives, it is written to storage first. Then the system checks if the subscriber is online:

- **Online** → push immediately (real-time path)
- **Offline** → message waits in storage

`MAILBOX.QUERY` is the final safety net — an Agent that missed pushes can pull on reconnect.

### Priority levels

```text
$mq9.AI.INBOX.{mail_id}.urgent    → delivered first, persisted
$mq9.AI.INBOX.{mail_id}.normal    → standard, persisted
$mq9.AI.INBOX.{mail_id}.notify    → low priority, shorter TTL
```

An edge device coming back online processes `urgent` messages first — the cloud may have sent an emergency stop command hours ago.

### No new SDK

mq9 runs over NATS. Go, Python, Rust, Java, JavaScript, .NET — if a NATS client exists, it's already an mq9 client. No new library to install. No new API to learn.

## Storage tiers

Not all messages have the same durability requirements.

| Tier | Backend | Use case |
| - | - | - |
| Memory | RAM | Heartbeats, coordination signals (loss acceptable) |
| Persistent | RocksDB | Task delivery, results, approvals (default) |
| Archive | File Segment | Audit trails, compliance records |

Each message pays for what it needs. A heartbeat doesn't need triple-replication. A financial approval does.

## Where mq9 fits

**vs. NATS JetStream** — JetStream gives you streams and consumers (Kafka-like). mq9 gives you mailboxes and broadcasts (email-like). Different abstractions. mq9 is not a replacement for JetStream — it's a layer on top that adds Agent-native semantics.

**vs. A2A (Google's Agent2Agent protocol)** — A2A defines how Agents negotiate tasks and exchange structured messages: application layer. mq9 defines how those messages reliably arrive: transport layer. They're complementary. A2A can run over mq9 as its transport instead of HTTP.

**vs. AgentMail** — AgentMail is solving Agent-to-human email (Agents sending mail to your inbox). mq9 is solving Agent-to-Agent native async communication. Different problem.

## What mq9 is not

- Not a replacement for HTTP/gRPC between synchronous services
- Not a data pipeline (use Kafka for that)
- Not trying to be all things — four commands, one problem space

---

*Read the [For Agent](/for-agent) page to see how Agents use mq9. Read the [For Engineer](/for-engineer) page to integrate it into your stack.*
