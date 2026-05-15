---
title: What is mq9
description: mq9 — Agent registration, discovery, and reliable async messaging for multi-agent systems.
outline: deep
---

mq9 is a broker that provides Agent registration, discovery, and reliable asynchronous messaging — designed to scale to millions of agents.

It is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq), sitting alongside MQTT, Kafka, NATS, and AMQP on a shared storage layer.

## Two foundational problems

Every multi-agent system hits the same two problems, regardless of framework or language:

**Problem 1: Agents can't find each other.**

Agents are not static services with fixed endpoints. They spin up dynamically, specialize in different tasks, and their addresses are unknown at system design time. Building a directory by hand doesn't scale. Without a registry, every agent needs to be told about every other agent — a coordination problem that grows quadratically.

**Problem 2: Agents can't reliably exchange messages.**

Agents are ephemeral. They go offline unexpectedly, restart mid-task, and may not exist yet when another agent tries to reach them. Fire-and-forget transports drop messages. Push-based subscriptions require both sides online simultaneously. The result: dropped messages, retry logic scattered across every agent, and fragile coordination glue that each team rebuilds from scratch.

**mq9 solves both in one broker.**

## How mq9 solves them

### Agent Registry and Discovery

Agents announce themselves at startup with a capability description — their AgentCard. Other agents search the registry by keyword or natural language intent to find what they need.

```text
Agent starts → REGISTER (name + capability description)
Other Agent  → DISCOVER ("find an agent that can translate Chinese") → returns matched agents
                                                                      → send to matched agent's mailbox
Agent stops  → UNREGISTER
```

The registry supports two search modes:

| Mode | How | Use case |
| ---- | --- | -------- |
| Semantic | Natural language intent | "find an agent that summarizes PDFs" |
| Full-text | Keyword match | `translator`, `billing`, `risk-check` |

An **AgentCard** is the registration payload — name plus a free-text capability description. mq9 indexes it for both keyword and vector search. No schema to define, no service mesh to configure.

### Reliable Async Messaging

Once an agent is discovered, messaging is the second piece. mq9 gives every agent a **mailbox** — a persistent address that holds messages until the recipient is ready to fetch them.

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

**FETCH + ACK consumption model:**

```text
FETCH → broker returns messages (priority order) → process → ACK → broker advances offset
                                                                           ↓
                                                               next FETCH resumes here
```

Messages are never lost when the consumer is offline. On reconnect, FETCH resumes from the last ACK.

**Three-tier priority:**

```text
critical → urgent → normal
```

Within a mailbox, higher-priority messages are returned first — FIFO within each tier. An agent coming back online after hours processes `critical` messages (emergency stops, abort signals) before normal task dispatches.

## Core concepts

### AgentCard

The registration record for an agent. Contains the agent's name and a free-text capability description. mq9 indexes it for keyword and semantic vector search. Agents discover each other through AgentCards without needing prior knowledge of addresses.

### REGISTER / DISCOVER

`AGENT.REGISTER` — publish an AgentCard to the registry. Call at startup; send periodic `AGENT.REPORT` heartbeats to signal the agent is still alive.

`AGENT.DISCOVER` — search the registry by keyword or semantic query. Returns a list of matching agents with their names and mailbox addresses.

### Mailbox

A named, persistent message store. Created on demand with a TTL. The `mail_address` is the delivery address. Anyone who knows it can send to it or fetch from it — unguessability is the security boundary.

`ttl: 0` — mailbox never expires. TTL cannot be changed after creation.

### FETCH + ACK

Pull consumption with offset tracking. `group_name` enables stateful consumption — the broker records which messages have been confirmed. Omit `group_name` for stateless one-off reads.

### Three-tier priority

Messages are labeled `critical`, `urgent`, or `normal` via the `mq9-priority` header. FETCH returns them in priority order. Within a tier, delivery is FIFO.

## Comparison

| | **mq9** | **etcd + Kafka** | **NATS JetStream** | **Google A2A** |
| --- | --- | --- | --- | --- |
| Agent registry | Built-in, semantic + keyword search | etcd is a key-value store, no semantic search | No native registry | Agent discovery only, no messaging |
| Async messaging | FETCH+ACK, offline delivery, priority | Kafka handles messaging; no native Agent registry | Streams + durable consumers; no Agent registry | No transport layer |
| Priority delivery | Three-tier (critical / urgent / normal) | No native message priority | No native priority | N/A |
| Offline delivery | Yes — store first, fetch on reconnect | Yes (Kafka) | Yes | No |
| Setup | Single broker, one deploy | Two separate systems to operate | Single server, but no registry | Protocol only, no broker |
| Agent lifecycle | TTL-based auto-expiry | Manual cleanup | Manual cleanup | N/A |

**vs. raw NATS Core** — NATS Core is fire-and-forget pub/sub. mq9 adds persistent mailboxes, FETCH+ACK consumption, priority ordering, TTL lifecycle, and the Agent registry on top of NATS transport. Same wire protocol, completely different guarantees.

**vs. A2A (Google's Agent2Agent)** — A2A defines how agents negotiate tasks at the application layer. mq9 handles reliable delivery and discovery at the transport layer. They are complementary — A2A workflows can run over mq9.

**mq9 is not:**

- A replacement for HTTP/gRPC between always-online services
- A data pipeline or event log
- An orchestration framework — it moves messages and enables discovery, not decisions

## Design principles

**Registry and messaging are one system, not two.** The registry tells you where agents are. The mailbox ensures messages reach them. Splitting these into separate systems creates two integration surfaces, two failure modes, and two operational planes. mq9 unifies them.

**No new concepts invented.** Request/reply reuses NATS native semantics. Offset tracking mirrors Kafka consumer groups. Message attributes are transmitted via NATS headers.

**mail_address is not tied to Agent identity.** One Agent can have different mailboxes for different tasks. TTL handles cleanup — no deregistration code, no lingering state.

**Single node is enough, scale when needed.** A single instance handles millions of concurrent agent connections. When higher availability is needed, switch to cluster mode — the API is unchanged.

## Position in RobustMQ

mq9 is RobustMQ's fifth native protocol, sharing the same unified storage architecture as MQTT, Kafka, NATS, and AMQP. Deploy one RobustMQ instance — all capabilities are available. IoT devices send data over MQTT, analytics systems consume over Kafka, agents collaborate over mq9 — one broker, one storage layer, no bridging.

NATS is only the **transport layer** — the wire protocol between client and broker. Storage, priority scheduling, TTL management, pull consumption offsets, and the Agent registry are all implemented by RobustMQ in Rust.

*See [For Agent](/for-agent) for the protocol reference. See [For Engineer](/for-engineer) for integration code.*
