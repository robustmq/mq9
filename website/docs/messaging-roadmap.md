---
title: Reliable Async Messaging — Vision and Capability Roadmap
description: How mq9 evolves from a messaging foundation into a dedicated Agent communication infrastructure — redesigned abstractions, capability tiers, and long-horizon goals.
outline: deep
---

# Reliable Async Messaging — Vision and Roadmap

## Why "Agent Messaging" Is Not Just Messaging

Message brokers have existed for decades. The engineering foundations — persistence, reliable delivery, high throughput, low latency, high availability, clustering — are well understood. mq9 does not ignore this foundation; it builds on it. But mq9's differentiator is not the foundation itself. It is what sits on top of it.

Every abstraction in a traditional broker was designed for a world where the unit of communication is a stream of bytes between services that are almost always online. Agent workloads break each of those assumptions simultaneously.

| Traditional broker | mq9 |
|---|---|
| topic / queue | mailbox (per-agent, 1:1 binding) |
| topic-name routing | agent address / capability routing |
| short, fire-and-forget messages | long-running tasks (minutes to hours) |
| consumer occasionally offline | agent frequently offline — by design |
| pub/sub topology | N-to-N agent collaboration with sessions |
| opaque bytes | structured task (A2A Message with Parts) |
| client_id (a meaningless string) | AgentCard (identity + declared capabilities) |

This table is not a marketing comparison. It is a design constraint. Each row represents a place where repurposing a traditional broker forces developers to work around the abstraction rather than with it.

mq9's thesis: build the abstractions right for Agent scenarios from the start, and let the engineering foundation be exactly that — a foundation.

### Registry and Messaging Are One Concept

In every traditional broker, client identity is incidental. A `client_id` is a handle for connection management, not a first-class entity. mq9 treats the Agent as a first-class entity: an Agent has an AgentCard that declares its name, capabilities, and metadata. The registry manages the Agent's existence; the mailbox manages its communication. They are two facets of the same concept, not two separate systems bolted together.

This unification is what makes intent-based routing possible: a sender can describe what it needs done, and the broker can match that intent against the declared capabilities of registered agents — without the sender knowing or caring which specific agent handles the task.

## What Is Already Built

The current release covers the core messaging primitives needed for reliable offline delivery and structured consumption.

### Persistent Mailboxes

Every agent gets a mailbox with configurable TTL. Messages are stored durably on the broker. The agent does not need to be connected when a message arrives — it fetches on reconnect. This is the foundational guarantee that makes offline-by-design workloads viable.

### Three-Tier Priority

Messages carry one of three priority levels: `CRITICAL`, `URGENT`, or `NORMAL`. Within each tier, delivery is FIFO. Higher tiers are served first. This lets a calling agent signal urgency without the receiving agent needing to inspect content.

### Pull Consumption with Server-Side Offset Tracking

mq9 uses a pull model (FETCH + ACK) with server-tracked consumer group offsets. An agent fetches a batch, processes it, and ACKs to advance the offset. If the agent crashes mid-processing, the unACKed messages are re-delivered on the next FETCH. This is resume-from-offset — the broker holds the state, not the client.

### Per-Message Attributes

Each message carries structured metadata headers:

- `mq9-key` — deduplication key; the broker discards a duplicate before it ever reaches the mailbox
- `mq9-tags` — filtering labels; receivers can fetch only messages matching a tag set
- `mq9-delay` — deferred delivery; message is held until a specified offset from send time
- `mq9-ttl` — per-message TTL independent of mailbox TTL; expired messages are dropped silently

### N-to-N Topologies

Shared mailboxes support fan-in (multiple senders, one receiver), fan-out (one sender, multiple competing consumers pulling from the same mailbox), and broadcast patterns. These are not special modes — they fall out naturally from the mailbox + consumer group model.

## Capability Roadmap

The roadmap is organized into three tiers. Tier 1 is the current engineering focus. Tiers 2 and 3 represent directional commitments, not release timelines.

### Tier 1 — Strengthen the Foundation

#### Full SDK Parity Across Six Languages

The Python SDK is complete. Go, JavaScript, Java, Rust, and C# are scaffolded. Tier 1 work brings all six to feature parity: all 10 protocol commands covered, idiomatic async APIs, consume-loop-with-retry, and published packages for each ecosystem.

SDK parity is a prerequisite for everything else — no advanced capability matters if the developer cannot access it from their language of choice.

#### Long-Task Lifecycle Tracking

Current messaging covers send and receive. What is missing is the task state machine between them. A long-running agent task should expose discrete states: `submitted → working → input-required → completed` (and `failed`). These states need to be tracked on the broker so that:

- the calling agent can query task status without polling for messages
- a crashed agent can resume a task mid-execution after reconnect without losing the state snapshot
- orchestrating agents can surface task status to humans without inspecting message content

This is the feature that makes mq9 suitable for tasks that run for minutes to hours, not milliseconds.

#### Stateful Session Support

A single task often involves multiple turns: an orchestrator sends a task, a worker asks a clarifying question, the orchestrator answers, and the worker completes. Today each of these is an independent message. Tier 1 introduces `correlation_id` tracking at the broker level: a session groups related messages, the broker maintains session history, and agents can fetch a session view rather than an unordered mailbox view.

This makes multi-turn Agent exchanges a first-class primitive instead of something each developer reimplements by convention.

#### Exactly-Once Delivery for Critical Tasks

At-least-once delivery (the current guarantee) is sufficient for idempotent tasks. Critical non-idempotent tasks — payments, resource provisioning, irreversible state changes — need exactly-once semantics. Tier 1 adds an opt-in exactly-once delivery mode backed by broker-side deduplication combined with cooperative ACK fencing.

#### Dead Letter Handling

Messages that exhaust their retry budget currently stall the consumer group. Tier 1 adds a configurable dead-letter mailbox per mailbox: messages that exceed max retries are moved there automatically, with the original headers and a failure reason attached. The dead-letter mailbox is itself a normal mq9 mailbox — it can be consumed, monitored, and alerted on using exactly the same primitives.

### Tier 2 — Semantic Routing and Access Control

#### Intent-Based Routing

Today a sender must know the `mail_address` of the recipient. Tier 2 introduces intent-based routing: the sender describes what it needs done (as a structured capability request), and the broker vector-matches that intent against the capability declarations in registered AgentCards. The broker selects the best-matching available agent and routes the message there.

This decouples sender logic from recipient identity — a sender does not need to know which specific agent will handle a task, only what kind of task it is.

#### Per-Mailbox Access Control

Currently, knowing a mailbox address is sufficient to send to it. Tier 2 adds a permission layer: explicit send/receive grants per mailbox, bound to authenticated identities. The credential model supports OAuth Bearer tokens, API keys, and mTLS at the broker level — no application-layer enforcement required.

#### Entitlement Model

Access control at the mailbox level needs a higher-level model: which clients are allowed to send to which mailboxes, under what conditions. The entitlement model formalizes this as a policy that the broker evaluates at send time, before the message is persisted.

#### Content Policy Engine

Some deployments need to enforce rules on message content — blocking messages that contain disallowed data types, violate compliance requirements, or attempt prompt injection. The content policy engine evaluates message content semantically (not just structurally) before delivery. Messages that violate policy are rejected at the broker boundary with a structured error, before they ever reach the receiving agent.

#### Audit Logging

Every send, fetch, ACK, and delete event can be recorded to an audit stream. The audit stream is consumable via Kafka protocol on the same RobustMQ instance — no separate pipeline required. This satisfies enterprise compliance requirements without adding infrastructure.

### Tier 3 — Long-Horizon Capabilities

#### Context Awareness

Today agents are responsible for retransmitting relevant context with every message. This is wasteful: the broker has already seen every message in a session. Tier 3 introduces broker-side context tracking: for Agent pairs with an active session, the broker maintains a compressed conversation history and enriches incoming messages with relevant historical context before delivery. Agents stop retransmitting full context; the broker manages it.

#### Privacy-Preserving Messaging

Agent-to-agent messages may carry sensitive data. Tier 3 adds end-to-end encryption between specific agent pairs: messages are encrypted by the sender's agent runtime and decryptable only by the intended recipient. The broker stores and routes ciphertext — it never sees plaintext. This supports deployments where the broker operator and the agent operators are different trust domains.

#### Cross-Cluster Message Routing

A single mq9 cluster has a single address space. Tier 3 introduces federation: messages are addressable to agents on remote mq9 nodes. The broker resolves the target cluster, routes the message across the federation boundary, and delivers it as if it were local. This enables multi-region and multi-tenant deployments without application-layer routing logic.

#### OpenTelemetry Integration

Full observability of message flows: every send and deliver operation emits spans compatible with OpenTelemetry. Distributed traces span sender agent → broker → receiver agent. This makes it possible to diagnose latency, trace task failures, and understand the full execution graph of a multi-agent workflow in any standard observability backend.

## The Kubernetes Analogy

Kafka is to Agent messaging what OpenStack is to container orchestration: a powerful general-purpose system that can be made to work, but one that was not designed for the target workload. Every Agent-specific pattern — offline delivery, long-task state, capability routing, per-agent identity — requires custom application logic layered on top.

mq9 is to Kafka what Kubernetes is to OpenStack: not a repurposed general tool, but a dedicated tool designed from scratch for the target workload. Every abstraction is optimized for Agent scenarios. The engineering foundation (persistence, throughput, HA) is the same class of problem; the abstractions on top are entirely different.

The ceiling for mq9, if the thesis is correct, is the same ceiling Kubernetes reached: becoming the de facto infrastructure layer for its target workload. Every Agent framework, every multi-agent system, every enterprise AI deployment eventually needs a message layer. mq9's bet is that the right abstractions, built early, compound over time.
