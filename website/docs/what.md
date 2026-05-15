---
title: What is mq9
description: mq9 — Agent registration, discovery, and reliable async messaging for multi-agent systems.
outline: deep
---

# What is mq9

![mq9 architecture flow](/flow.svg)

mq9 is a broker that provides Agent registration, discovery, and reliable asynchronous messaging — designed to scale to millions of agents.

## Why mq9 exists

The vision behind mq9 is to make agent-to-agent communication **just work**. Every multi-agent system today encounters the same two foundational problems: how do agents find each other, and how do agents reliably communicate. Without standardized infrastructure, every team rebuilds the same plumbing. mq9 exists to solve these two problems well, so that developers can focus on agent logic rather than infrastructure.

## Two foundational problems

**Problem 1: Agents can't find each other.**

Agents are not static services with fixed endpoints. They spin up dynamically, specialize in different tasks, and their addresses are unknown at system design time. Building a directory by hand doesn't scale. Without a registry, every agent needs to be told about every other agent — a coordination problem that grows quadratically.

**Problem 2: Agents can't reliably exchange messages.**

Agents are ephemeral. They go offline unexpectedly, restart mid-task, and may not exist yet when another agent tries to reach them. Fire-and-forget transports drop messages. Push-based subscriptions require both sides online simultaneously. The result: dropped messages, retry logic scattered across every agent, and fragile coordination glue that each team rebuilds from scratch.

**mq9 solves both in one broker.**

## How mq9 solves them

### Agent Registry and Discovery

Agents announce themselves at startup with a capability description — their AgentCard. Other agents search the registry by keyword or natural language intent to find what they need.

![Agent Registry & Discovery flow](/diagram-registry.svg)

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

![FETCH + ACK offset tracking](/diagram-fetch-ack.svg)

Messages are never lost when the consumer is offline. On reconnect, FETCH resumes from the last ACK.

**Three-tier priority:**

![Three-tier priority queue](/diagram-priority.svg)

Within a mailbox, higher-priority messages are returned first — FIFO within each tier. An agent coming back online after hours processes `critical` messages (emergency stops, abort signals) before normal task dispatches.

## Positioning

mq9 is not a general-purpose message queue. It is purpose-built for Agent communication, focusing on two things: making agents discoverable, and making messages reliably deliverable.

| | **mq9** | **etcd + Kafka** | **NATS JetStream** | **Google A2A** |
| --- | --- | --- | --- | --- |
| Agent registry | Built-in, semantic + keyword search | etcd is a key-value store, no semantic search | No native registry | Agent discovery only, no messaging |
| Async messaging | FETCH+ACK, offline delivery, priority | Kafka handles messaging; no native Agent registry | Streams + durable consumers; no Agent registry | No transport layer |
| Priority delivery | Three-tier (critical / urgent / normal) | No native message priority | No native priority | N/A |
| Offline delivery | Yes — store first, fetch on reconnect | Yes (Kafka) | Yes | No |
| Setup | Single broker, one deploy | Two separate systems to operate | Single server, but no registry | Protocol only, no broker |
| Agent lifecycle | TTL-based auto-expiry | Manual cleanup | Manual cleanup | N/A |

**vs. A2A (Agent-to-Agent protocol)** — A2A defines how agents negotiate tasks at the application layer. mq9 handles reliable delivery and discovery at the transport layer. They are complementary — A2A workflows can run over mq9.

**mq9 is not:**
- A replacement for HTTP/gRPC between always-online services
- A data pipeline or event log
- An orchestration framework — it moves messages and enables discovery, not decisions

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

## Key Capabilities

| Capability | Details |
| --- | --- |
| Agent registration | Register with a capability description; full-text and semantic vector indexed |
| Agent discovery | Full-text (`text`) or semantic (`semantic`) search |
| Agent heartbeat | `AGENT.REPORT` keeps registry current |
| Persistent mailboxes | Messages stored server-side until consumed; TTL-based auto-destruction |
| Pull + ACK consumption | Stateful consumer groups with server-side offset tracking; resume-from-offset |
| Three-tier priority | `critical` > `urgent` > `normal`; enforced by storage layer |
| Key deduplication | `mq9-key`: only the latest message per key is retained |
| Delayed delivery | `mq9-delay`: message becomes visible after N seconds |
| Per-message TTL | `mq9-ttl`: message expires independently of mailbox TTL |
| Tag filtering | `mq9-tags`: filter messages by comma-separated tags via QUERY |
| N-to-N topologies | Shared mailboxes support fan-in, fan-out, and competing consumer patterns |

## Design principles

**Registry and messaging are one system, not two.** The registry tells you where agents are. The mailbox ensures messages reach them. Splitting these into separate systems creates two integration surfaces, two failure modes, and two operational planes. mq9 unifies them.

**Pull over Push.** Agents control their own consumption rate. FETCH when ready, resume from the last ACK. No long-lived connections required.

**Address is the permission boundary.** `mail_address` is the only credential needed — no tokens, no ACLs, no auth layer. Unguessability is the security model.

**Protocol-neutral transport.** Any NATS client is an mq9 client — Go, Python, Rust, JavaScript, Java. No proprietary SDK required.

**Single node is enough, scale when needed.** A single instance handles millions of concurrent agent connections. Cluster mode is available when needed — the API is unchanged.

## Protocol at a Glance

All commands use NATS request/reply under `$mq9.AI.*`.

| Category | Subject | Description |
| --- | --- | --- |
| Agent registry | `$mq9.AI.AGENT.REGISTER` | Register an Agent |
| Agent registry | `$mq9.AI.AGENT.UNREGISTER` | Unregister an Agent |
| Agent registry | `$mq9.AI.AGENT.REPORT` | Agent heartbeat / status |
| Agent registry | `$mq9.AI.AGENT.DISCOVER` | Search Agents by keyword or semantic intent |
| Mailbox | `$mq9.AI.MAILBOX.CREATE` | Create a mailbox with optional name and TTL |
| Messaging | `$mq9.AI.MSG.SEND.{mail_address}` | Send a message |
| Messaging | `$mq9.AI.MSG.FETCH.{mail_address}` | Pull messages |
| Messaging | `$mq9.AI.MSG.ACK.{mail_address}` | Advance consumer group offset |
| Messaging | `$mq9.AI.MSG.QUERY.{mail_address}` | Inspect mailbox without affecting offset |
| Messaging | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}` | Delete a specific message |

*See [For Agent](/for-agent) for the protocol reference. See [For Engineer](/for-engineer) for integration code.*
