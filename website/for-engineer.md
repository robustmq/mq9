---
title: For Engineer — mq9 Integration Guide
description: How to integrate mq9 into your stack. Code examples in Python, Go, and JavaScript.
---

# For Engineer

You're building a multi-Agent system. This is your integration guide.

> This page assumes you've read [What is mq9](/what). It focuses on integration code and production considerations — not concept explanations.

## The problem you're facing

Agents are not services. Services are always online — you can HTTP them, pub/sub them, stream to them. Agents spin up for a task and disappear. They restart. They go offline mid-conversation.

You've probably already hit one of these:

- Agent B is offline when Agent A sends a result. Message lost. You add a retry loop.
- You use Redis pub/sub, but offline Agents miss publishes. You add Redis Streams. Now you're managing consumer groups for ephemeral processes.
- You poll a shared database for coordination. It works, but it's slow and everyone's doing it differently.
- You scale from 10 to 100 Agents and everything breaks — too many connections, too much state, no standard pattern.

There's no standard solution for Agent-to-Agent async communication. Every team builds their own. None of it is simple. All of it breaks at scale.

## What mq9 solves

mq9 is async messaging infrastructure built specifically for Agents. You run one binary. Your Agents use the mq9 SDK — Python, Go, or JavaScript.

What it handles so you don't have to:

- **Offline delivery** — message arrives when the target is offline? Stored. Delivered on reconnect. No retry logic needed.
- **Point-to-point** — each Agent gets a mailbox. Send to a `mail_id`. Done.
- **Public channels** — create a named public mailbox. Any Agent can discover it via `mb.list()` and subscribe.
- **Priority** — high-priority messages processed first.
- **Automatic cleanup** — mailboxes expire via TTL. No manual deletion, no orphaned state.
- **Competing workers** — resume groups give you one-message-per-worker without coordination overhead.

## 30-second demo

Two Agents, one message, end to end. Copy and run.

```python
# demo.py — requires: pip install mq9
import asyncio
from mq9 import Mailbox

async def main():
    mb = Mailbox("nats://localhost:4222")

    # Agent A creates a mailbox
    agent_a = await mb.create(ttl=3600)
    print(f"Agent A mailbox: {agent_a['mail_id']}")

    # Agent B creates a mailbox
    agent_b = await mb.create(ttl=3600)
    print(f"Agent B mailbox: {agent_b['mail_id']}")

    received = asyncio.Event()

    # Agent B subscribes to its mailbox
    async def on_message(msg):
        print(f"Agent B received: {msg['payload']}")
        if msg.get("reply_to"):
            await mb.send(msg["reply_to"], {
                "from": agent_b["mail_id"],
                "type": "result",
                "correlation_id": msg["correlation_id"],
                "payload": "task complete"
            })
        received.set()

    await mb.receive(agent_b["mail_id"], callback=on_message)

    # Agent A sends a task to Agent B
    await mb.send(agent_b["mail_id"], {
        "from": agent_a["mail_id"],
        "type": "task",
        "correlation_id": "demo-001",
        "reply_to": agent_a["mail_id"],
        "payload": "analyze this"
    })
    print("Agent A sent task")

    await received.wait()

asyncio.run(main())
```

Run mq9 first:

```bash
docker run -d --name mq9 -p 4222:4222 mq9/mq9:latest
python demo.py
```

## Core operations

### Create a mailbox

```python
# Python
from mq9 import Mailbox

mb = Mailbox("nats://localhost:4222")
mail_id = await mb.create(ttl=3600)
```

```go
// Go
mb := mq9.NewMailbox("nats://localhost:4222")
mailID, _ := mb.Create(mq9.WithTTL(3600))
```

```javascript
// JavaScript
const mb = new Mailbox("nats://localhost:4222")
const mailID = await mb.create({ ttl: 3600 })
```

### Send a message

```python
await mb.send(target_mail_id, {
    "from": mail_id,
    "type": "task",
    "correlation_id": "req-001",
    "reply_to": mail_id,
    "payload": { "data": "..." }
}, priority="normal")
```

### Subscribe and receive

Subscribe delivers all unexpired messages immediately, then streams new arrivals. No separate pull needed.

```python
def on_message(msg):
    print(f"From {msg['from']}: {msg['payload']}")
    if msg.get("reply_to"):
        mb.send(msg["reply_to"], {
            "from": mail_id,
            "type": "result",
            "correlation_id": msg["correlation_id"],
            "payload": { "status": "done" }
        })

mb.receive(mail_id, callback=on_message)
```

### Broadcast via public mailbox

```python
# Create public mailbox
await mb.create(ttl=3600, public=True, name="pipeline.complete")

# Send to it
await mb.send("pipeline.complete", { "from": mail_id, "stage": "preprocessing", "ok": True })

# Subscribe
await mb.receive("pipeline.complete", callback=handler)
```

## Common patterns

### Child Agent reports result to parent {#pattern-child-result}

```python
# Parent sends task with reply_to
await mb.send(worker_id, {
    "from": parent_id,
    "type": "work",
    "correlation_id": "job-001",
    "reply_to": parent_id,
    "payload": { "data": [] }
})

# Parent collects results — non-blocking
results = {}
async def collect(msg):
    results[msg["correlation_id"]] = msg["payload"]

await mb.receive(parent_id, callback=collect)
```

### Task broadcast with competing workers {#pattern-competing}

```python
# Create a public task queue (once, idempotent)
await mb.create(ttl=86400, public=True, name="task.queue")

# Orchestrator publishes tasks
await mb.send("task.queue", { "task_id": "t-001", "data": {} })

# Workers subscribe with resume group — each task goes to exactly one worker
async def handle_task(msg):
    result = await process(msg)
    await mb.send(master_id, { "from": worker_id, "task_id": msg["task_id"], "result": result })

await mb.receive("task.queue", resume="task-workers", callback=handle_task)
```

### Cloud to offline edge device {#pattern-edge}

```go
// Cloud: send commands — edge may be offline for hours
mb.Send(edgeID, map[string]any{
    "command": "emergency_stop",
    "reason":  "temperature_critical",
}, mq9.WithPriority("high"))

mb.Send(edgeID, map[string]any{
    "command":  "update_config",
    "interval": 30,
})

// Edge: on reconnect, subscribe — high priority messages arrive first
mb.Receive(edgeID, func(msg mq9.Message) {
    dispatch(msg)
})
```

### Human-in-the-loop approval {#pattern-human}

```javascript
// Agent sends approval request to human's mailbox
await mb.send(humanMailID, {
  from: agentMailID,
  type: "approval_request",
  correlation_id: "approval-001",
  content: "Call external fraud API — estimated cost $50",
  reply_to: agentMailID
}, { priority: "high" })

// Human's client — same SDK
mb.receive(humanMailID, async (req) => {
  const approved = await showApprovalUI(req)
  await mb.send(req.reply_to, {
    from: humanMailID,
    type: "approval_response",
    correlation_id: req.correlation_id,
    approved
  })
})
```

### Capability registration and discovery {#pattern-capability}

```go
// Agent creates a public mailbox on startup to announce capabilities
mb.Create(
    mq9.WithTTL(3600),
    mq9.WithPublic(true),
    mq9.WithName("agent."+agentID),
    mq9.WithDesc("data analysis, anomaly detection"),
)

// Orchestrator subscribes to PUBLIC.LIST — receives all registrations
index := map[string]string{}
mb.List(func(event mq9.ListEvent) {
    if event.Type == "created" {
        index[event.MailID] = event.Desc
    } else if event.Type == "expired" {
        delete(index, event.MailID)
    }
})

// Dispatch to a capable Agent
mb.Send("agent."+targetID, task)
```

### Async request-reply {#pattern-request-reply}

```python
# Agent A asks Agent B a question — B may be offline
await mb.send(agent_b_id, {
    "from": agent_a_id,
    "type": "question",
    "correlation_id": "q-001",
    "reply_to": agent_a_id,
    "payload": { "question": "..." }
})

# Agent A continues other work — no blocking
# When Agent B comes online, it processes the question and replies to agent_a_id
# Agent A's receive callback picks up the reply by correlation_id
```

## Error handling

| Situation | What happens | What to do |
| - | - | - |
| `mb.create()` fails | Returns error | Retry with backoff; check server connectivity |
| Send to expired `mail_id` | Message dropped silently | Set TTL longer than your worst-case offline window |
| `mb.create()` called twice with same public name | Silently succeeds — TTL stays from first creation | This is intentional — CREATE is idempotent |
| TTL expires before Agent reconnects | Mailbox and all messages deleted | Set TTL to cover worst-case offline duration |
| Message exceeds size limit | Rejected with error | Keep payloads small; use references to external storage for large data |

## Deployment

### Development

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data mq9/mq9:latest
```

Mount `-v mq9-data:/data` to persist mailboxes and messages across container restarts. Without it, all data is lost on restart.

### Production — single node

Single binary, no external dependencies. A single node handles millions of concurrent Agent connections. Suitable for most production workloads.

```bash
docker run -d \
  --name mq9 \
  -p 4222:4222 \
  -p 9090:9090 \
  -v /data/mq9:/data \
  --restart unless-stopped \
  mq9/mq9:latest
```

- Port `4222` — mq9 protocol (Agent connections)
- Port `9090` — Prometheus metrics endpoint

### Cluster mode

Scale horizontally when a single node is not enough. Agents use the same SDK — no client code changes required.

### Observability

```bash
# Prometheus metrics
curl http://localhost:9090/metrics
```

```python
# Fetch all messages in a mailbox
await mb.fetch(mail_id)
```

## Pattern reference

| Scenario | API | Pattern |
| - | - | - |
| Point-to-point | `mb.send(mail_id, payload)` | Send to known mail_id |
| Public broadcast | `mb.send(name, payload)` | Public mailbox + `mb.receive` |
| Competing workers | `mb.receive(name, resume="workers")` | Resume group — one message per worker |
| Request-reply | `mb.send` + `reply_to` field | `correlation_id` links the pair |
| Capability discovery | `mb.create(public=True, name="...")` | PUBLIC.LIST auto-registration |
| Offline delivery | `mb.send` + `mb.receive` | Store-first, push on reconnect |

*See [What](/what) for design rationale. See [For Agent](/for-agent) for the Agent perspective.*
