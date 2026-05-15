---
title: For Agent — mq9 Agent Manual
description: How AI Agents use mq9 — mailbox, send, fetch, ACK, priority, offline delivery.
---

# For Agent

You are an AI Agent. This is your communication manual.

> This page describes the protocol concepts. For typed SDK usage — see [For Engineer](/for-engineer).

## The problem you face

You are ephemeral. You spin up to handle a task, then go dark. You might restart unexpectedly. You might be busy when a message arrives. You might not even exist yet when another Agent tries to reach you.

Standard communication tools weren't built for this:

- **HTTP** requires both sides to be online at the same time. You go offline — the message is gone.
- **Redis pub/sub** has no persistence. Miss the publish window — miss the message.
- **Direct NATS Core** is fire-and-forget. No delivery guarantee when you're offline.

The result: other Agents can't reliably reach you. You can't reliably reach them.

## What mq9 gives you

mq9 gives every Agent a **mailbox** — a persistent address that holds messages until you're ready to fetch them.

- Send a message to any Agent, whether they're online or not. mq9 stores it.
- FETCH your mailbox when you start up. mq9 returns everything that arrived while you were gone — in priority order.
- Messages have three priority levels. Critical commands get fetched first.
- Mailboxes expire automatically via TTL. No manual cleanup.
- A built-in Agent registry lets Agents find each other by capability, including semantic search.

The mental model is **email, not RPC**. You send to an address. The recipient reads when ready. Neither side needs to be online at the same time.

## How to use mq9

### Get a mailbox

Before other Agents can reach you, you need an address.

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.inbox","ttl":3600}'
```

Response:

```json
{"error": "", "mail_address": "agent.inbox"}
```

- `mail_address` — your address. Share this with Agents who need to reach you.
- `ttl` — your mailbox lives for 3600 seconds, then auto-expires with all its messages.
- `ttl: 0` — mailbox never expires.
- **The name must be unique.** Creating a mailbox with a name that already exists returns an error.

**mail_address format:** lowercase letters, digits, and dots only. 1–128 characters. Examples: `agent.inbox`, `task.queue.v2`, `session.20260502`.

**Unguessability is your security boundary.** Anyone who knows your `mail_address` can send to it or fetch from it. Keep private mailboxes private.

**You can have multiple mailboxes** — one per communication concern:

```bash
# Private inbox for task assignments
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl":7200}'

# Shared public queue for competing workers
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"task.queue","ttl":86400}'
```

### Send a message

You know another Agent's `mail_address`. Send to it. They may be offline — mq9 stores it.

```bash
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  '{"from":"sender.mailbox","type":"task","reply_to":"sender.mailbox","payload":{"task":"analyze","data":"..."}}'
```

**Set priority via header:**

```bash
# Critical — abort signals, emergency commands, security events
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# Urgent — approval requests, time-sensitive notifications
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-priority:urgent' \
  '{"type":"interrupt","task_id":"t-002"}'

# Normal (default, no header) — task dispatch, result delivery
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  '{"type":"task","payload":"process dataset A"}'
```

**Optional message attributes (via headers):**

| Header           | Purpose                                                          |
| ---------------- | ---------------------------------------------------------------- |
| `mq9-key: state` | Key dedup — only the latest message with this key is kept        |
| `mq9-tags: a,b`  | Comma-separated tags; can be filtered in QUERY                   |
| `mq9-delay: 60`  | Delay delivery by 60 seconds; returns `msg_id: -1`               |
| `mq9-ttl: 300`   | Message expires in 300 s regardless of mailbox TTL               |

**Message body fields (recommended convention, not enforced):**

| Field            | Purpose                                                  |
| ---------------- | -------------------------------------------------------- |
| `from`           | Sender's `mail_address`                                  |
| `type`           | Message kind: `task`, `result`, `question`, `approval_request` |
| `correlation_id` | Links a message to its reply                             |
| `reply_to`       | The `mail_address` where you want the response sent      |
| `payload`        | The actual content — mq9 does not inspect or validate it |

mq9 treats the message body as opaque bytes. These fields are a convention, not a protocol requirement.

### Fetch messages (FETCH + ACK)

mq9 uses **pull mode**. You actively FETCH messages when you're ready — not a push subscription.

```bash
nats request '$mq9.AI.MSG.FETCH.agent.inbox' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

Response — sorted by priority (`critical` → `urgent` → `normal`, FIFO within each level):

```json
{
  "error": "",
  "messages": [
    {"msg_id": 1, "payload": "...", "priority": "critical", "create_time": 1712600001},
    {"msg_id": 3, "payload": "...", "priority": "normal",   "create_time": 1712600003}
  ]
}
```

**`group_name`** enables stateful consumption: the broker records your offset. After ACK, the next FETCH resumes from where you left off — no duplicate delivery. Omit `group_name` for stateless one-off reads.

**`deliver` start policies:**

| Value       | Description                                  |
| ----------- | -------------------------------------------- |
| `latest`    | Only messages arriving from this point on    |
| `earliest`  | Start from the oldest message in the mailbox |
| `from_time` | Start from after a Unix timestamp            |
| `from_id`   | Start from a specific `msg_id`               |

After processing, call ACK to advance your offset:

```bash
nats request '$mq9.AI.MSG.ACK.agent.inbox' '{
  "group_name": "my-worker",
  "mail_address": "agent.inbox",
  "msg_id": 3
}'
```

Pass the `msg_id` of the **last message in the batch** — one ACK confirms the whole batch.

### Reply to a message

If the sender set `reply_to`, send your result to that `mail_address`:

```bash
nats request '$mq9.AI.MSG.SEND.sender.mailbox' '{
  "from": "agent.inbox",
  "type": "task_result",
  "correlation_id": "req-001",
  "payload": {"result": "done"}
}'
```

### Inspect without consuming (QUERY)

QUERY returns stored messages **without affecting your consumption offset**. Use it for debugging or state inspection:

```bash
# All messages
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{}'

# Latest message with key "status"
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"key":"status"}'

# By time range
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"since":1712600000,"limit":20}'
```

QUERY never moves your offset. Two consecutive QUERYs return the same result (assuming no new messages).

### Delete a message

```bash
nats request '$mq9.AI.MSG.DELETE.agent.inbox.5' '{}'
```

Subject pattern: `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}`

## Advertise your capabilities

Register at startup so other Agents can discover you:

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "payload": "Multilingual translation; supports EN/ZH/JA/KO; returns results in real time"
}'
```

Send periodic heartbeats:

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "agent.translator",
  "report_info": "running, processed: 512 tasks"
}'
```

Unregister at shutdown:

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name":"agent.translator"}'
```

## Discover other Agents

Find agents by capability without knowing their address in advance:

```bash
# Semantic vector search (natural language intent)
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "find an agent that can translate Chinese text into English",
  "limit": 5
}'

# Full-text keyword search
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator",
  "limit": 10
}'
```

Once you have a matching agent's `mail_address`, send to it directly.

## Protocol summary

| Operation         | Subject pattern                                 |
| ----------------- | ----------------------------------------------- |
| Create mailbox    | `$mq9.AI.MAILBOX.CREATE`                        |
| Send message      | `$mq9.AI.MSG.SEND.{mail_address}`               |
| Fetch messages    | `$mq9.AI.MSG.FETCH.{mail_address}`              |
| ACK               | `$mq9.AI.MSG.ACK.{mail_address}`                |
| Query (inspect)   | `$mq9.AI.MSG.QUERY.{mail_address}`              |
| Delete message    | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}`    |
| Register Agent    | `$mq9.AI.AGENT.REGISTER`                        |
| Unregister Agent  | `$mq9.AI.AGENT.UNREGISTER`                      |
| Report status     | `$mq9.AI.AGENT.REPORT`                          |
| Discover Agents   | `$mq9.AI.AGENT.DISCOVER`                        |

*For SDK usage in Python, Go, JavaScript, Rust, and Java — see [For Engineer](/for-engineer).*
