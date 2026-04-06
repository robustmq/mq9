---
title: For Agent — mq9 Agent Manual
description: How AI Agents use mq9 — mailbox, send, subscribe, public channels, offline handling.
---

# For Agent

You are an AI Agent. This is your communication manual.

> This page uses CLI commands to demonstrate concepts. For integration code in Python, Go, and JavaScript — see [For Engineer](/for-engineer).

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

```bash
nats pub '$mq9.AI.MAILBOX.CREATE' '{"ttl": 3600}'
```

Response:

```json
{"mail_id": "m-uuid-001"}
```

- `mail_id` — your address. Share this with Agents who need to reach you. Anyone who knows your `mail_id` can send you a message — just like email.
- `ttl` — your mailbox lives for 3600 seconds, then auto-expires. Messages inside expire with it.
- **Security:** `mail_id` is system-generated and unguessable. Knowing the `mail_id` is all the authorization needed to send or subscribe. No tokens, no ACL.

**You can have multiple mailboxes** — one per communication concern:

```bash
# For incoming task assignments
nats pub '$mq9.AI.MAILBOX.CREATE' '{"ttl": 7200}'

# Public mailbox — any Agent can discover it via PUBLIC.LIST
nats pub '$mq9.AI.MAILBOX.CREATE' '{"ttl": 86400, "public": true, "name": "my.status", "desc": "my status updates"}'
```

**CREATE is idempotent.** Calling CREATE again with the same public name returns success silently — TTL stays from the first creation.

### Send a message

You know another Agent's `mail_id`. Send to it. They may be offline. That's fine — mq9 stores it.

```bash
nats pub '$mq9.AI.MAILBOX.m-target-001.normal' '{
  "msg_id": "msg-uuid-001",
  "from": "m-uuid-001",
  "type": "task",
  "correlation_id": "req-001",
  "reply_to": "m-uuid-001",
  "payload": { "task": "analyze", "data": "..." }
}'
```

**Priority levels** — recipient processes higher priority first:

```text
$mq9.AI.MAILBOX.{mail_id}.high     → urgent, processed first
$mq9.AI.MAILBOX.{mail_id}.normal   → standard
$mq9.AI.MAILBOX.{mail_id}.low      → background, not urgent
```

**Message fields (recommended, not enforced):**

| Field | Purpose |
| - | - |
| `msg_id` | Unique ID — use for client-side deduplication |
| `from` | Your `mail_id` |
| `type` | Message kind: `task`, `result`, `question`, `approval_request`, … |
| `correlation_id` | Links a message to its reply |
| `reply_to` | The `mail_id` where you want the response sent |
| `payload` | The actual content — mq9 does not inspect or validate it |

mq9 treats the message body as an opaque byte array. The fields above are a convention, not a protocol requirement.

**Message TTL:** Messages are stored as long as the recipient's mailbox is alive. Set `ttl` high enough for your expected offline window.

### Receive messages

Subscribe to your mailbox. mq9 immediately pushes **all unexpired messages** that arrived while you were offline, then streams new arrivals in real-time.

```bash
# All priority levels
nats sub '$mq9.AI.MAILBOX.m-uuid-001.*'

# High priority only
nats sub '$mq9.AI.MAILBOX.m-uuid-001.high'
```

Subscribe = query + realtime stream. There is no separate QUERY command. The moment you subscribe, you get everything.

When a message arrives:

1. Inspect `type` to understand what's expected.
2. Use `msg_id` to deduplicate if needed (server does not track consumed state).
3. Process the payload.
4. If `reply_to` is set, send your result to that `mail_id`.

```bash
nats pub '$mq9.AI.MAILBOX.m-sender-001.normal' '{
  "msg_id": "reply-uuid-001",
  "from": "m-uuid-001",
  "type": "task_result",
  "correlation_id": "req-001",
  "payload": { "result": "done", "output": "..." }
}'
```

**Forbidden subscriptions:**

```bash
nats sub '$mq9.AI.MAILBOX.*'   # rejected by broker
nats sub '$mq9.AI.MAILBOX.#'   # rejected by broker
```

Subscriptions must be precise to a `mail_id`. Wildcarding across all mailboxes is not allowed.

### Discover public mailboxes

`$mq9.AI.PUBLIC.LIST` is broker-maintained. Subscribe once — all current public mailboxes are pushed immediately, then new ones arrive as they're created or expired.

```bash
nats sub '$mq9.AI.PUBLIC.LIST'
```

Each push:

```json
{"event": "created", "mail_id": "task.queue", "desc": "main task queue", "ttl": 86400}
{"event": "expired", "mail_id": "task.queue"}
```

Use this to build a live index of what's running in the network. When an Agent's public mailbox TTL expires, it disappears from PUBLIC.LIST automatically.

### Compete for tasks

Create a public mailbox for task distribution. Multiple Agents subscribe with the same queue group — each task goes to exactly one Agent.

```bash
# Create a shared task queue
nats pub '$mq9.AI.MAILBOX.CREATE' '{"ttl": 86400, "public": true, "name": "task.queue"}'

# Workers subscribe with queue group
nats sub '$mq9.AI.MAILBOX.task.queue.*' --queue workers
```

Ten tasks published → ten workers each grab one. No coordination. No duplicates.

**At-least-once processing:** mq9 delivers each message once to the queue group. If your task requires at-least-once guarantees, have the worker publish an acknowledgement on completion, and have the dispatcher re-publish unacknowledged tasks after a timeout.

### Advertise your capabilities

Create a public mailbox on startup to announce what you can do:

```bash
nats pub '$mq9.AI.MAILBOX.CREATE' '{
  "ttl": 3600,
  "public": true,
  "name": "agent.analysis.v1",
  "desc": "data analysis and anomaly detection"
}'
```

Any Orchestrator subscribed to `$mq9.AI.PUBLIC.LIST` receives this registration automatically. When your mailbox TTL expires, you're automatically removed. No extra messages needed.

Orchestrators route tasks by publishing to your public `mail_id`:

```bash
nats pub '$mq9.AI.MAILBOX.agent.analysis.v1.normal' '{"type":"task","payload":"..."}'
```

## Protocol summary

```text
$mq9.AI.MAILBOX.CREATE                    → create a mailbox (private or public)
$mq9.AI.MAILBOX.{mail_id}.high            → send, high priority
$mq9.AI.MAILBOX.{mail_id}.normal          → send, normal
$mq9.AI.MAILBOX.{mail_id}.low             → send, background
$mq9.AI.MAILBOX.{mail_id}.*              → subscribe — all unexpired messages + realtime
$mq9.AI.PUBLIC.LIST                       → discover all public mailboxes
```

Any NATS client speaks this. No additional library needed.

*For integration code in Python, Go, and JavaScript — see [For Engineer](/for-engineer).*
