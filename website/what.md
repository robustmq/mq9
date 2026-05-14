---
title: What is mq9
description: mq9 — async messaging infrastructure for AI Agents. What it is, what it solves, and how it works.
---

# What is mq9

mq9 is the mailbox for AI Agents. A message broker built specifically for Agent-to-Agent async communication — persistent, pull-based, priority delivery. Deploy once, every Agent gets a mailbox.

It is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq), sitting alongside MQTT, Kafka, NATS, and AMQP on a shared storage layer.

## Why a mailbox?

Agents are not services. A service runs continuously and holds a stable address. An Agent spins up for a task, does its work, and disappears. Its identity is temporary.

In mq9, an Agent requests a mailbox whenever it needs one. The `mail_address` is its address for that task. When the task ends, let the mailbox expire — it cleans itself up automatically via TTL. No deregistration, no cleanup code, no lingering state.

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

**Unguessability is the security boundary.** The `mail_address` is the only access credential. Know it and you can send or fetch. Don't know it — you can't touch it. No tokens, no ACL, no auth layer.

## The problem it solves

In multi-Agent systems, Agents are not servers — they start, execute, and die, coming online and offline at any time. When Agent A sends a message to Agent B and B is offline, the message is gone. Every team works around this with their own temporary solution:

- **Redis pub/sub** — no persistence. Messages are lost if the recipient is offline.
- **Kafka** — topics require advance creation. Not designed for throwaway Agents.
- **Homegrown queues** — every team rebuilds the same thing. Agent implementations are incompatible across teams.

These approaches work, but they're all workarounds. Offline delivery is treated as a boundary condition handled manually, not a guarantee provided by the infrastructure.

**mq9 solves it directly: send a message, the recipient gets it when they come online.**

## How it works

### Pull consumption + ACK

mq9 uses **pull mode**: clients actively FETCH messages, then ACK to advance the consumption offset. Messages are not lost when consumers are temporarily offline — on reconnect, FETCH resumes from the last ACK.

```text
FETCH → broker returns messages → process → ACK → broker advances offset
                                                          ↓
                                              next FETCH resumes here
```

Two consumption modes:

| Mode      | How               | Use case                                                  |
| --------- | ----------------- | --------------------------------------------------------- |
| Stateful  | Pass `group_name` | Broker records offset; resumes from last ACK on reconnect |
| Stateless | Omit `group_name` | Each FETCH is independent; no offset recorded             |

### Three-tier priority

```text
critical → urgent → normal
```

Each message carries a priority. Within a mailbox, higher-priority messages are returned first by FETCH — FIFO within each level. An edge device coming back online after 8 hours processes `critical` first — the emergency stop sent hours ago is not buried under routine updates.

### Message attributes

Messages carry optional attributes via NATS headers:

| Attribute   | Purpose                                                   |
| ----------- | --------------------------------------------------------- |
| `mq9-key`   | Dedup key — only the latest message with this key is kept |
| `mq9-tags`  | Comma-separated tags for query filtering                  |
| `mq9-delay` | Delay delivery by N seconds                               |
| `mq9-ttl`   | Per-message TTL, independent of mailbox TTL               |

### Agent registry

mq9 has a built-in Agent registry. Agents register their capabilities at startup; other agents discover them by full-text search or **semantic vector search** (natural language intent matching).

```text
Agent starts → REGISTER (capability description)
Other Agent → DISCOVER ("find a translation agent") → returns matching list
                                                      → sends to matched agent's mailbox
Agent shuts down → UNREGISTER
```

### Mailbox lifetime

Mailboxes declare a TTL at creation. On expiry, the mailbox and all its messages are automatically destroyed with no manual cleanup required.

```json
{"name": "task.queue", "ttl": 3600}
```

`ttl: 0` means the mailbox never expires. TTL cannot be changed after creation.

## How mq9 fits in your stack

**vs. raw NATS Core** — NATS Core is fire-and-forget pub/sub. mq9 adds persistent mailboxes, pull+ACK consumption, priority ordering, and TTL lifecycle on top of NATS transport. Same NATS client, completely different guarantees.

**vs. NATS JetStream** — JetStream is a full Kafka-like system with named streams, durable consumers, and sequence-based replay. mq9 is optimized for Agent workloads: FETCH+ACK consumption, three-tier priority, message attributes, built-in Agent discovery. Different abstractions for different problems.

**vs. Kafka** — Kafka is a high-throughput ordered log optimized for data pipelines. mq9 is optimized for ephemeral Agents exchanging small messages with TTL lifecycle. Don't use mq9 as a data pipeline.

**vs. A2A (Google's Agent2Agent)** — A2A defines how Agents negotiate tasks at the application layer. mq9 handles reliable delivery at the transport layer. They're complementary — A2A can run over mq9.

**mq9 is not:**
- A replacement for HTTP/gRPC between always-online services
- A data pipeline or event log
- An orchestration framework — it moves messages, not decisions

## Position in RobustMQ

mq9 is RobustMQ's fifth native protocol, sharing the same unified storage architecture as MQTT, Kafka, NATS, and AMQP. Deploy one RobustMQ instance — all capabilities are ready. IoT devices send data over MQTT, analytics systems consume over Kafka, Agents collaborate over mq9 — one broker, one storage layer, no bridging.

NATS is only the **transport layer** — the wire protocol between client and broker. Storage, priority scheduling, TTL management, pull consumption offsets, and the Agent registry are all implemented by RobustMQ in Rust.

## Design principles

**No new concepts invented.** Request/reply reuses NATS native semantics. Offset tracking is analogous to Kafka consumer groups. Message attributes are transmitted via NATS headers.

**mail_address is not tied to Agent identity.** One Agent can create different mailboxes for different tasks, leave them alone when done, and TTL handles cleanup automatically.

**Single node is enough, scale when needed.** A single instance covers most workloads. When high availability is needed, switch to cluster mode — the API is unchanged.

*See [For Agent](/for-agent) to understand how Agents use mq9. See [For Engineer](/for-engineer) for integration code.*
