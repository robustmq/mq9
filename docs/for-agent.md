---
title: For Agent — mq9 Agent Manual
description: How AI Agents use mq9 — mailbox, inbox, broadcast, offline handling.
---

# For Agent

You are an AI Agent. This is your communication manual.

## The problem you face

You are ephemeral. You spin up to handle a task, then go dark. You might restart unexpectedly. You might be busy when a message arrives. You might not even exist yet when another Agent tries to reach you.

Standard communication tools weren't built for this:

- **HTTP** requires both sides to be online at the same time. You go offline — the message is gone.
- **Redis pub/sub** has no persistence. Miss the publish window — miss the message.
- **Direct NATS** is fire-and-forget. No delivery guarantee when you're offline.

The result: other Agents can't reliably reach you. You can't reliably reach them. Every team builds their own workaround. None of it scales.

## What mq9 gives you

mq9 gives every Agent a **mailbox** — a persistent inbox that holds messages until you're ready to receive them.

- Send a message to any Agent, whether they're online or not. mq9 stores it.
- Subscribe to your mailbox when you start up. mq9 pushes everything that arrived while you were gone.
- Broadcast your capabilities or events to the network. You don't manage the subscriber list.
- Messages have priority. Urgent commands get processed first.
- Mailboxes expire automatically. No manual cleanup.

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

## How to use mq9

### Get a mailbox

Before other Agents can reach you, you need an address.

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"standard","ttl":3600}'
```

Response:

```json
{
  "mail_id": "m-uuid-001",
  "token": "tok-xxx",
  "inbox": "$mq9.AI.INBOX.m-uuid-001"
}
```

- `mail_id` — your address. Share this with Agents who need to reach you.
- `token` — authenticates mailbox operations. Keep this private.
- `ttl` — your mailbox lives for 3600 seconds, then auto-expires.

**Two mailbox types:**

| Type | Behavior | When to use |
| - | - | - |
| `standard` | Keeps all messages | Task requests, results, approvals |
| `latest` | Keeps only the newest | Status updates, current state |

If you're reporting your current load to an orchestrator, use `latest`. The orchestrator wants your current state, not a history of every state you've been in.

**You can have multiple mailboxes** — one per communication concern:

```bash
# For incoming task assignments
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"standard","ttl":7200}'

# For broadcasting your status
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"latest","ttl":7200}'
```

### Send a message

You know another Agent's `mail_id`. Send to it. They may be offline. That's fine.

```bash
nats publish '$mq9.AI.INBOX.m-target-001.normal' '{
  "from": "m-uuid-001",
  "type": "task",
  "correlation_id": "req-001",
  "reply_to": "$mq9.AI.INBOX.m-uuid-001.normal",
  "payload": { "task": "analyze", "data": "..." }
}'
```

**Priority levels** — recipient processes higher priority first:

```text
$mq9.AI.INBOX.{mail_id}.urgent    → processed first
$mq9.AI.INBOX.{mail_id}.normal    → standard
$mq9.AI.INBOX.{mail_id}.notify    → background, shorter TTL
```

**Message fields:**

| Field | Purpose |
| - | - |
| `from` | Your `mail_id` |
| `type` | Message kind: `task`, `result`, `question`, `approval_request`, … |
| `correlation_id` | Links a message to its reply |
| `reply_to` | Subject where you want the response sent |
| `payload` | The actual content |

### Receive messages

Subscribe to your inbox. mq9 pushes messages in real-time — including anything that arrived while you were offline.

```bash
# All priority levels
nats subscribe '$mq9.AI.INBOX.m-uuid-001.*'

# Urgent only
nats subscribe '$mq9.AI.INBOX.m-uuid-001.urgent'
```

When a message arrives:

1. Inspect `type` to understand what's expected.
2. Process the payload.
3. If `reply_to` is set, send your result there.

```bash
nats publish '$mq9.AI.INBOX.m-sender-001.normal' '{
  "from": "m-uuid-001",
  "type": "task_result",
  "correlation_id": "req-001",
  "payload": { "result": "done", "output": "..." }
}'
```

### Recover missed messages

If you reconnect after being offline and want to confirm nothing slipped through:

```bash
nats request '$mq9.AI.MAILBOX.QUERY.m-uuid-001' '{"token":"tok-xxx"}'
```

Response:

```json
{
  "mail_id": "m-uuid-001",
  "unread": 3,
  "messages": [...]
}
```

Normal flow: subscribe and get pushed. `QUERY` is your safety net after a gap.

### Broadcast

When you don't need to know who's listening — publish once, any subscriber receives it.

```bash
nats publish '$mq9.AI.BROADCAST.analytics.complete' '{
  "from": "m-uuid-001",
  "analysis_id": "a-789",
  "result": "anomaly detected",
  "confidence": 0.95
}'
```

**Wildcard subscriptions:**

```bash
# All events in a domain
nats subscribe '$mq9.AI.BROADCAST.analytics.*'

# All alerts, any domain
nats subscribe '$mq9.AI.BROADCAST.*.alert'

# Everything
nats subscribe '$mq9.AI.BROADCAST.#'
```

### Compete for tasks

Multiple Agents can handle the same task type. Use a queue group — only one Agent grabs each message.

```bash
nats subscribe '$mq9.AI.BROADCAST.task.available' --queue 'workers'
```

Ten tasks published → ten workers each grab one. No coordination. No duplicates.

### Advertise your capabilities

On startup, tell the network what you can do:

```bash
nats publish '$mq9.AI.BROADCAST.system.capability' '{
  "from": "m-uuid-001",
  "capabilities": ["data.analysis", "anomaly.detection"],
  "reply_to": "$mq9.AI.INBOX.m-uuid-001.normal"
}'
```

Orchestrators subscribed to `$mq9.AI.BROADCAST.system.capability` learn about you and can send tasks directly to your `mail_id`.

## Protocol summary

```text
$mq9.AI.MAILBOX.CREATE                  → get a mailbox
$mq9.AI.MAILBOX.QUERY.{mail_id}         → pull unread messages
$mq9.AI.INBOX.{mail_id}.urgent          → send, high priority
$mq9.AI.INBOX.{mail_id}.normal          → send, normal
$mq9.AI.INBOX.{mail_id}.notify          → send, background
$mq9.AI.BROADCAST.{domain}.{event}      → broadcast to subscribers
```

Any NATS client speaks this. No additional library needed.

---

*For integration code in Python, Go, and JavaScript — see [For Engineer](/for-engineer).*
