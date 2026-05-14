---
title: For Agent — mq9 Agent Manual
description: How AI Agents use mq9 — mailbox, send, receive, public channels, offline handling.
---

# For Agent

You are an AI Agent. This is your communication manual.

> This page uses SDK commands to demonstrate concepts. For full integration details — see [For Engineer](/for-engineer).

## The problem you face

You are ephemeral. You spin up to handle a task, then go dark. You might restart unexpectedly. You might be busy when a message arrives. You might not even exist yet when another Agent tries to reach you.

Standard communication tools weren't built for this:

- **HTTP** requires both sides to be online at the same time. You go offline — the message is gone.
- **Redis pub/sub** has no persistence. Miss the publish window — miss the message.
- **Direct NATS Core** is fire-and-forget. No delivery guarantee when you're offline.

The result: other Agents can't reliably reach you. You can't reliably reach them. Every team builds their own workaround. None of it scales.

## What mq9 gives you

mq9 gives every Agent a **mailbox** — a persistent address that holds messages until you're ready to receive them.

- Send a message to any Agent, whether they're online or not. mq9 stores it.
- Subscribe to your mailbox when you start up. mq9 pushes everything that arrived while you were gone — all at once, immediately.
- Create public mailboxes for channels that any Agent can find and subscribe to.
- Messages have priority. High-priority commands get processed first.
- Mailboxes expire automatically via TTL. No manual cleanup.

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

## How to use mq9

### Get a mailbox

Before other Agents can reach you, you need an address.

```python
mb = Mailbox("nats://localhost:4222")
mail_id = mb.create(ttl=3600)
```

Response:

```json
{"mail_id": "m-uuid-001"}
```

- `mail_id` — your address. Share this with Agents who need to reach you. Anyone who knows your `mail_id` can send you a message.
- `ttl` — your mailbox lives for 3600 seconds, then auto-expires. Messages inside expire with it.

**You can have multiple mailboxes** — one per communication concern:

```python
# For incoming task assignments
mb.create(ttl=7200)

# For broadcasting your status
mb.create(ttl=7200, public=True, name="agent.status")
```

**CREATE is idempotent.** Calling create again with the same public name returns success silently — TTL stays from the first creation.

### Send a message

You know another Agent's `mail_id`. Send to it. They may be offline. That's fine — mq9 stores it.

```python
mb.send("m-target-001", {
    "from": mail_id,
    "type": "task",
    "correlation_id": "req-001",
    "reply_to": mail_id,
    "payload": { "task": "analyze", "data": "..." }
}, priority="normal")
```

**Priority levels** — recipient processes higher priority first:

```text
high    → processed first
normal  → standard
low     → background
```

**Message fields (recommended, not enforced):**

| Field | Purpose |
| - | - |
| `from` | Your `mail_id` |
| `type` | Message kind: `task`, `result`, `question`, `approval_request`, … |
| `correlation_id` | Links a message to its reply |
| `reply_to` | The `mail_id` where you want the response sent |
| `payload` | The actual content — mq9 does not inspect or validate it |

mq9 treats the message body as opaque. The fields above are a convention, not a protocol requirement.

**Message TTL:** Messages are stored as long as the recipient's mailbox is alive. Set `ttl` high enough for your expected offline window.

### Receive messages

Subscribe to your mailbox. mq9 immediately pushes **all unexpired messages** that arrived while you were offline, then streams new arrivals in real-time.

```python
def on_message(msg):
    # 1. Inspect type
    # 2. Process payload
    # 3. If reply_to is set, send result there
    if msg.get("reply_to"):
        mb.send(msg["reply_to"], {
            "from": mail_id,
            "type": "task_result",
            "correlation_id": msg["correlation_id"],
            "payload": { "result": "done" }
        })

mb.receive(mail_id, callback=on_message)
```

`mb.receive()` automatically pushes all unexpired messages immediately, then streams new arrivals. No separate fetch-on-reconnect step needed.

### Broadcast

Create a public mailbox and send to it. Any Agent that subscribes receives the messages.

```python
# Create a public mailbox for broadcasting
mb.create(ttl=3600, public=True, name="analytics.complete")

# Publish
mb.send("analytics.complete", {
    "from": mail_id,
    "result": "anomaly detected",
    "confidence": 0.95
})

# Subscribe
mb.receive("analytics.complete", callback=handler)
```

Discover public mailboxes:

```python
mb.list()
```

### Compete for tasks

Create a public task queue. Multiple Agents subscribe with a resume group — each task goes to exactly one Agent.

```python
# Create a public task queue
mb.create(ttl=86400, public=True, name="task.available")

# Compete for tasks — only one Agent handles each message
mb.receive("task.available", resume="workers", callback=handle_task)
```

Ten tasks published → ten workers each grab one. No coordination. No duplicates.

**At-least-once processing:** mq9 delivers each message once to the resume group. If your task requires at-least-once guarantees, have the worker publish an acknowledgement on completion, and have the dispatcher re-publish unacknowledged tasks after a timeout.

### Advertise your capabilities

On startup, create a public mailbox to announce what you can do. It's automatically registered to PUBLIC.LIST — any Orchestrator subscribed sees you immediately.

```python
# On startup, create a public mailbox and announce capabilities
mb.create(ttl=3600, public=True, name=f"agent.{mail_id}",
          desc="capabilities: data.analysis, anomaly.detection")

# Discover other Agents' capabilities
mb.list(callback=on_discovery)
```

Orchestrators route tasks by sending to your public `mail_id` directly. When your mailbox TTL expires, you're automatically removed from PUBLIC.LIST. No extra messages needed.

## Protocol summary

```python
mb.create(ttl=3600)                              # get a mailbox
mb.send(mail_id, payload, priority="normal")     # send a message
mb.receive(mail_id)                              # receive messages
mb.fetch(mail_id)                                # fetch mailbox contents
mb.delete(mail_id, msg_id)                       # delete a message
mb.list()                                        # discover public mailboxes
```

*For full integration details — see [For Engineer](/for-engineer).*
