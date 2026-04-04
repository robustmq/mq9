# mq9

The Communication Layer for AI Agents

Agent A finishes a task and sends the result to Agent B — but Agent B is offline. The message is lost.

This is the problem mq9 solves. Every Agent gets a mailbox. Messages wait. When the Agent comes back online, it gets what it missed.

mq9 is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq), purpose-built for Agent-to-Agent async communication. No new SDK needed — any NATS client is already an mq9 client.

---

## Why mq9

Today's AI Agents communicate with HTTP calls, Redis queues, or Kafka topics. Each works for a specific case. None of them were designed for Agents.

The gap:

| Need | HTTP | Redis | Kafka | mq9 |
| ---- | ---- | ----- | ----- | --- |
| Agent is offline when message arrives | Lost | Lost | Survives (but complex setup) | Survives, auto-delivered |
| Many Agents, small messages | OK | OK | Wasteful | Native fit |
| One-to-one async delivery | OK | Workaround | Workaround | Native |
| Broadcast to unknown subscribers | No | Pub/sub | Topic | Native |
| Auto-cleanup, no manual management | No | TTL hack | No | Built-in TTL |
| Lightweight, self-hosted | Yes | Yes | Heavy | Yes |

Agents are temporary. They spin up, complete a task, and go offline. They are not persistent services. The infrastructure they communicate through needs to reflect that.

---

## Four Commands

mq9 exposes four commands over NATS subjects. That's the entire protocol.

```text
MAILBOX.CREATE              → create a mailbox, get a mail_id
MAILBOX.QUERY.{mail_id}     → pull unread messages (fallback)
INBOX.{mail_id}.{priority}  → send a message to a specific Agent
BROADCAST.{domain}.{event}  → publish to all interested Agents
```

### Quick Start

```bash
# Agent A creates a mailbox
nats req '$mq9.AI.MAILBOX.CREATE' '{}'
# → {"mail_id": "agt-uuid-001", "token": "tok-xxx", "ttl": 86400}

# Agent B sends to Agent A (works even if A is offline)
nats pub '$mq9.AI.INBOX.agt-uuid-001.normal' '{"from":"agent-b","payload":"task done"}'

# Agent A subscribes and receives
nats sub '$mq9.AI.INBOX.agt-uuid-001.*'

# Agent A broadcasts a status event
nats pub '$mq9.AI.BROADCAST.pipeline.stage-complete' '{"stage":"preprocessing","result":"ok"}'

# Other Agents subscribe to the broadcast channel
nats sub '$mq9.AI.BROADCAST.pipeline.*'
```

### Priority Levels

```text
INBOX.{mail_id}.urgent    → delivered first, high retention
INBOX.{mail_id}.normal    → standard delivery
INBOX.{mail_id}.notify    → low priority, shorter TTL
```

---

## Core Concepts

**Mailbox** — Each Agent creates a mailbox with `MAILBOX.CREATE` and gets a `mail_id`. Messages sent to that `mail_id` are stored until the Agent reads them. The mailbox has a TTL and auto-expires. No manual cleanup needed.

**Inbox** — Point-to-point delivery. Agent B sends to Agent A's `mail_id`. Agent A receives it whether online now or later.

**Broadcast** — Publish once to a domain/event channel. Any Agent subscribed receives it. The sender doesn't need to know who's listening.

**Pull fallback** — If an Agent missed a push, it can call `MAILBOX.QUERY.{mail_id}` to pull unread messages. Push-first, pull as fallback.

---

## Eight Scenarios, Four Commands

These are the real cases mq9 is designed for:

1. **Sub-Agent task completion** — Sub-Agent finishes, sends result to Master Agent's inbox. Master may be sleeping. Message waits.

2. **Master Agent status awareness** — All Sub-Agents broadcast their status to `BROADCAST.pipeline.status`. Master subscribes once, knows everything.

3. **Task broadcast with worker competition** — Master broadcasts a task to `BROADCAST.tasks.new`. First available Worker picks it up.

4. **Anomaly alert broadcasting** — Monitoring Agent detects error, publishes to `BROADCAST.alerts.critical`. All subscribed Agents respond.

5. **Cloud to offline edge device** — Cloud sends instruction to edge Agent's inbox. Edge device reconnects, gets it.

6. **Human-in-the-loop workflows** — Agent sends approval request to human operator's inbox. Human approves hours later. Agent receives confirmation and continues.

7. **Async request-reply between Agents** — Agent A sends request to Agent B with a reply `mail_id`. Agent B sends response to that `mail_id`. Fully async.

8. **Agent capability registration and discovery** — Agents publish their capabilities to `BROADCAST.registry.announce`. Others query what's available.

All eight scenarios. Four commands.

---

## Storage Tiers

mq9 uses RobustMQ's unified storage layer with three tiers:

| Tier | Backend | Use case |
| ---- | ------- | -------- |
| Memory | In-memory | Temporary, real-time Agents |
| Persistent | RocksDB | Short-lived but must survive restart |
| Archive | File Segment | Long-term, audit, replay |

Default is Memory with configurable TTL. Agents that need durability opt into RocksDB or File Segment.

---

## Relationship to Other Protocols

### mq9 vs A2A (Google's Agent2Agent protocol)

A2A defines how Agents negotiate tasks and exchange structured messages — application layer semantics. mq9 handles how those messages are delivered — transport layer. They are complementary, not competing. A2A can run over mq9 as its transport.

### mq9 vs NATS JetStream

JetStream gives you durable streams and consumers. It's powerful but requires setup: stream creation, consumer configuration, retention policies. mq9 sits on top of NATS and adds Agent-native semantics: `MAILBOX.CREATE` gives you a mailbox in one call. No stream configuration. Auto-TTL. Designed for ephemeral Agents, not persistent data pipelines.

### mq9 vs Kafka

Kafka is optimized for high-throughput ordered logs — batch data, event sourcing, audit trails. mq9 is optimized for many lightweight Agents exchanging small, targeted messages. Different problem.

---

## No New SDK

mq9 runs over NATS. Any NATS client works.

```python
# Python
import nats
nc = await nats.connect("nats://localhost:4222")
await nc.publish("$mq9.AI.INBOX.agt-uuid-001.normal", b'{"task":"done"}')
```

```go
// Go
nc, _ := nats.Connect("nats://localhost:4222")
nc.Publish("$mq9.AI.INBOX.agt-uuid-001.normal", []byte(`{"task":"done"}`))
```

```javascript
// JavaScript / Node.js
const nc = await connect({ servers: "nats://localhost:4222" });
nc.publish("$mq9.AI.INBOX.agt-uuid-001.normal", encode('{"task":"done"}'));
```

Go, Python, Rust, Java, JavaScript, .NET — if there's a NATS client, it's an mq9 client.

---

## Status

mq9 is under active development as part of [RobustMQ](https://github.com/robustmq/robustmq).

- Protocol design: complete
- Core commands implemented and validated
- Multi-protocol unified storage: working
- Production hardening: in progress

---

## Built On

mq9 is the fifth native protocol in RobustMQ, alongside MQTT, Kafka, NATS, and AMQP. It shares the same unified storage engine and multi-tenant architecture.

RobustMQ repository: [github.com/robustmq/robustmq](https://github.com/robustmq/robustmq)
