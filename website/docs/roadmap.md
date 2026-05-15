---
title: Roadmap
description: mq9 development roadmap — registry, reliable messaging, and the path to production-grade Agent infrastructure.
outline: deep
---

# Roadmap

mq9's core registry and communication layers are both in place. This page describes where we are, where we're going, and how the two major capability tracks evolve over time.

The phases are not strictly sequential. Priorities shift based on real-world usage and community feedback. The direction is fixed; the order is flexible.

---

## Where We Are Today

Both the Agent Registry and the Reliable Async Messaging layers are operational.

### Agent Registry

- REGISTER / UNREGISTER / REPORT / DISCOVER
- Full-text and semantic vector search
- TTL-based auto-expiry

### Reliable Async Messaging

- Persistent mailboxes with TTL lifecycle
- Three-tier priority (`critical` / `urgent` / `normal`)
- Pull + ACK consumption with server-side offset tracking
- Message attributes: key deduplication, tag filtering, delayed delivery, per-message TTL
- Offline delivery — messages wait until the recipient FETCHes

### SDKs and Integrations

- Six-language SDK (Python fully implemented; Go, JavaScript, Java, Rust, C# scaffolded)
- `langchain-mq9` — LangChain / LangGraph toolkit
- MCP Server support

---

## Tier 1 — Strengthen the Foundation

Before expanding capabilities, the existing primitives must reach production grade.

### Registry

- Agent Card schema stabilization — standardized fields, versioning
- Heartbeat and health status persistence
- A2A AgentCard import — automatically onboard any A2A-compliant agent from `/.well-known/agent.json`

### Messaging

- Full SDK parity across all six languages
- Stateful session support — correlation tracking across multi-turn exchanges
- Long-task lifecycle — `submitted → working → completed` state on the broker, with client resume-after-reconnect

### Infrastructure

- Cluster mode stability and documented deployment guide
- Public node `demo.robustmq.com` — stable, observable, usable for development

---

## Tier 2 — Semantic Routing and Access Control

### Semantic routing

Today, DISCOVER is pull-based: the sender queries, picks a target, and sends explicitly. The next step is intent-based routing: the sender describes what it needs done, and mq9 routes to the best-matching registered Agent automatically.

- Messages optionally carry a semantic intent description instead of a fixed `mail_address`
- The broker vector-matches intent against registered AgentCard capability descriptions
- Routing happens inside the broker, transparently to the sender

### Access control and entitlements

- Per-mailbox send/receive permissions beyond the current "address is the credential" model
- Entitlement model: which clients can use which agents
- OAuth Bearer token / API key / mTLS support at the broker level
- Administrative API for permission management

### Audit logging

- Send, fetch, ACK, and delete events recordable per message
- Satisfies traceability requirements for compliance scenarios
- Audit stream consumable via the Kafka protocol on the same RobustMQ instance — no separate infrastructure

---

## Tier 3 — Trust, Federation, and Context

### Trust and integrity

- Cryptographic signatures on AgentCard metadata
- Verifiable Credentials (W3C VC) for agent identity
- Tamper-evident audit trail

### Federation

- Cross-registry discovery: mq9 registries across organizations can federate
- Registry-of-registries pattern for large-scale deployments
- Agent addresses portable across federated nodes

### Context awareness (exploratory)

- Broker becomes session-aware: tracks conversation history between Agent pairs
- Agents no longer retransmit full context in every message
- Infrastructure evolves from a stateless pipeline into a stateful context network

---

## Capability tracks in detail

- [Agent Registry — Vision and Roadmap](/docs/registry-roadmap)
- [Reliable Async Messaging — Vision and Roadmap](/docs/messaging-roadmap)

---

## SDK completion

| Language | Status | Target |
| -------- | ------ | ------ |
| Python | Fully implemented | Complete |
| Go | Scaffolded | Full implementation |
| JavaScript | Scaffolded | Full implementation |
| Java | Scaffolded | Full implementation |
| Rust | Scaffolded | Full implementation |
| C# | Scaffolded | Full implementation |

All six languages expose identical API surfaces. New protocol operations are added to all six simultaneously.

---

## Public infrastructure

- `demo.robustmq.com` — shared demo node for development and testing. Not for production use.
- Self-hosted — mq9 is part of RobustMQ, which is open-source. Organizations with data sovereignty requirements deploy their own nodes. The protocol is identical.
