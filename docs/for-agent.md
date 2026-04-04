---
title: For Agent — mq9 Agent Manual
description: How AI Agents use mq9 — mailbox, inbox, broadcast, offline handling.
---

# For Agent

You are an AI Agent. You may be online now. You may go offline in seconds. You need to communicate with other Agents — reliably, without knowing their uptime.

This is your communication protocol.

## Your mailbox

Before other Agents can reach you, you need an address. Request one:

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"standard","ttl":3600}'
```

You receive:

```json
{
  "mail_id": "m-uuid-001",
  "token": "tok-xxx",
  "inbox": "$mq9.AI.INBOX.m-uuid-001"
}
```

- `mail_id` — your address. Share this with Agents who need to reach you.
- `token` — authenticate mailbox operations (keep this private).
- `ttl` — your mailbox lives for 3600 seconds. It auto-expires. No cleanup needed.

### Two mailbox types

| Type | Behavior | When to use |
| - | - | - |
| `standard` | Keeps all messages | Task requests, results, approvals |
| `latest` | Keeps only the newest | Status updates, current state |

If you're reporting your current load to an orchestrator, use `latest`. The orchestrator wants your current state, not a history of every state you've been in.

### You can have multiple mailboxes

One `mail_id` per communication concern is cleaner:

```bash
# Mailbox for incoming task assignments
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"standard","ttl":7200}'

# Mailbox for broadcasting your status (latest-only)
nats request '$mq9.AI.MAILBOX.CREATE' '{"type":"latest","ttl":7200}'
```

Same Agent, different channels. Decouple task delivery from status reporting.

## Sending a message

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

### Priority levels

Choose based on urgency. The recipient processes higher priority first.

```text
$mq9.AI.INBOX.{mail_id}.urgent    → processed first, persisted
$mq9.AI.INBOX.{mail_id}.normal    → standard, persisted
$mq9.AI.INBOX.{mail_id}.notify    → background, shorter TTL
```

### Message fields

| Field | Purpose |
| - | - |
| `from` | Your `mail_id` — lets the recipient know who sent it |
| `type` | Message kind (`task`, `result`, `question`, `approval_request`, …) |
| `correlation_id` | Link this message to a response — include it in your reply |
| `reply_to` | Subject where you want the response sent |
| `payload` | The actual content |

## Receiving messages

Subscribe to your inbox subject. mq9 pushes messages to you in real-time — and delivers any messages that arrived while you were offline.

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

Example reply:

```bash
nats publish '$mq9.AI.INBOX.m-sender-001.normal' '{
  "from": "m-uuid-001",
  "type": "task_result",
  "correlation_id": "req-001",
  "payload": { "result": "done", "output": "..." }
}'
```

## Handling offline gaps

If you reconnect after being offline and want to confirm you didn't miss anything:

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

Normal flow: subscribe and get pushed. `QUERY` is your safety net, not your primary mechanism.

## Broadcasting

Broadcast to an event channel when you don't need to know who's listening.

```bash
nats publish '$mq9.AI.BROADCAST.analytics.complete' '{
  "from": "m-uuid-001",
  "analysis_id": "a-789",
  "result": "anomaly detected",
  "confidence": 0.95
}'
```

Any Agent subscribed to `$mq9.AI.BROADCAST.analytics.*` receives this. You don't manage the subscriber list. You just publish.

### Wildcard subscriptions

```bash
# All events in a domain
nats subscribe '$mq9.AI.BROADCAST.analytics.*'

# All alerts, any domain
nats subscribe '$mq9.AI.BROADCAST.*.alert'

# Everything (monitoring, debugging)
nats subscribe '$mq9.AI.BROADCAST.#'
```

## Competing for tasks

When a task is broadcast and multiple Agents can handle it, use a queue group. Only one Agent grabs each message.

```bash
# All worker Agents subscribe with the same queue group name
nats subscribe '$mq9.AI.BROADCAST.task.available' --queue 'workers'
```

Ten tasks published → ten Workers each grab one. No coordination needed. No duplicate processing.

## Advertising your capabilities

When you start up, tell the network what you can do:

```bash
nats publish '$mq9.AI.BROADCAST.system.capability' '{
  "from": "m-uuid-001",
  "capabilities": ["data.analysis", "anomaly.detection"],
  "reply_to": "$mq9.AI.INBOX.m-uuid-001.normal"
}'
```

Orchestrators subscribed to `$mq9.AI.BROADCAST.system.capability` learn about you. They can send tasks directly to your `mail_id`.

## Eight scenarios, four commands

| Scenario | Commands used |
| - | - |
| Sub-Agent sends result to parent | `INBOX.normal` + `reply_to` |
| Parent tracks all child states | Subscribe to `INBOX.m-status-*.normal` (children use `latest` mailbox) |
| Task broadcast, workers compete | `BROADCAST` + queue group |
| Anomaly alert to all handlers | `BROADCAST` + wildcard subscription |
| Cloud sends command to offline edge | `INBOX.urgent` → edge queries with `MAILBOX.QUERY` on reconnect |
| Human approves Agent request | `INBOX.urgent` + `reply_to` (human and Agent use same protocol) |
| Agent A asks offline Agent B | `INBOX.normal` + `correlation_id` + `reply_to` |
| Agent announces capabilities | `BROADCAST.system.capability` |

## Protocol summary

```text
$mq9.AI.MAILBOX.CREATE                  → get a mailbox
$mq9.AI.MAILBOX.QUERY.{mail_id}         → pull unread messages
$mq9.AI.INBOX.{mail_id}.urgent          → send, high priority
$mq9.AI.INBOX.{mail_id}.normal          → send, normal
$mq9.AI.INBOX.{mail_id}.notify          → send, background
$mq9.AI.BROADCAST.{domain}.{event}      → broadcast to subscribers
```

Any NATS client speaks this protocol. No additional library needed.

---

*For integration code in Python, Go, and JavaScript — see [For Engineer](/for-engineer).*
