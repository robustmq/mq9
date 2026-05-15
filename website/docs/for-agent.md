---
title: For Agent — mq9 Agent Manual
description: What problems mq9 solves for AI Agents — registration, discovery, mailbox, send, fetch, ACK, priority, offline delivery.
---

# For Agent

You are an AI Agent. Here's what mq9 solves for you and how to use it.

## The problems mq9 solves for you

**You can't be found by other agents.**

You have capabilities — translation, summarization, risk scoring — but other agents don't know you exist or how to reach you. Without a registry, every orchestrator hardcodes addresses, and you're invisible to agents you've never been explicitly connected to.

mq9 gives you a place to publish your capabilities at startup. Any agent can search for you by keyword or natural language intent. You become discoverable without anyone needing to know your address in advance.

**You're not always online when messages arrive.**

You are ephemeral. You spin up to handle a task, then go dark. You might restart unexpectedly. When another agent sends you a message while you're offline, standard transports drop it:

- **HTTP** requires both sides online simultaneously.
- **Redis pub/sub** has no persistence — miss the publish window, miss the message.
- **NATS Core** is fire-and-forget — no delivery guarantee when you're offline.

mq9 gives you a **mailbox** — a persistent address that stores messages until you're ready to fetch them. Come back online hours later, FETCH in priority order, process, ACK. Nothing lost.

**You need both in one place.**

Registration and messaging are the same problem — finding agents and reaching them. mq9 solves both in one broker, under one protocol.

---

## Register yourself

Call REGISTER at startup. Publish your capabilities in plain text — mq9 indexes it for both keyword and semantic vector search.

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; supports EN/ZH/JA/KO; returns results in real time"
}'
```

Send heartbeats to stay visible in the registry:

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

---

## Discover other agents

Find agents by capability without knowing their address in advance:

```bash
# Semantic search — natural language intent
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "find an agent that can translate Chinese text into English",
  "limit": 5
}'

# Keyword search
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator",
  "limit": 10
}'
```

Once you have a matching agent's `mailbox`, send to it directly — even if they're offline right now.

---

## Get a mailbox

Before other agents can reach you, you need a persistent address.

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.inbox","ttl":3600}'
# → {"error": "", "mail_address": "agent.inbox"}
```

- `mail_address` — your address. Share it with agents that need to reach you.
- `ttl` — mailbox auto-expires after 3600 seconds, along with all its messages.
- `ttl: 0` — mailbox never expires.

**mail_address format:** lowercase letters, digits, and dots only. 1–128 characters. Examples: `agent.inbox`, `task.queue.v2`.

**Unguessability is your security boundary.** Anyone who knows your `mail_address` can send to it or fetch from it. Keep private mailboxes private.

---

## Send a message

You know another agent's `mail_address`. Send to it. They may be offline — mq9 stores it until they fetch.

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

| Header | Purpose |
| ------ | ------- |
| `mq9-key: state` | Key dedup — only the latest message with this key is kept |
| `mq9-tags: a,b` | Comma-separated tags; can be filtered in QUERY |
| `mq9-delay: 60` | Delay delivery by 60 seconds |
| `mq9-ttl: 300` | Message expires in 300 s regardless of mailbox TTL |

**Message body fields (recommended convention, not enforced):**

| Field | Purpose |
| ----- | ------- |
| `from` | Sender's `mail_address` |
| `type` | Message kind: `task`, `result`, `question`, `approval_request` |
| `correlation_id` | Links a message to its reply |
| `reply_to` | The `mail_address` where you want the response sent |
| `payload` | The actual content — mq9 does not inspect or validate it |

---

## Fetch your messages

mq9 uses **pull mode**. You actively FETCH when ready — no push subscription required.

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

**`group_name`** enables stateful consumption: the broker records your offset. After ACK, the next FETCH resumes from where you left off — no duplicates. Omit for stateless one-off reads.

**`deliver` start policies:**

| Value | Description |
| ----- | ----------- |
| `latest` | Only messages arriving from this point on |
| `earliest` | Start from the oldest message in the mailbox |
| `from_time` | Start from after a Unix timestamp |
| `from_id` | Start from a specific `msg_id` |

After processing, ACK to advance your offset:

```bash
nats request '$mq9.AI.MSG.ACK.agent.inbox' '{
  "group_name": "my-worker",
  "mail_address": "agent.inbox",
  "msg_id": 3
}'
```

Pass the `msg_id` of the **last message in the batch** — one ACK confirms the whole batch.

---

## Reply to a message

If the sender set `reply_to`, send your result to that `mail_address`:

```bash
nats request '$mq9.AI.MSG.SEND.sender.mailbox' '{
  "from": "agent.inbox",
  "type": "task_result",
  "correlation_id": "req-001",
  "payload": {"result": "done"}
}'
```

---

## Inspect without consuming

QUERY returns stored messages **without affecting your consumption offset**. Use it for debugging or state inspection:

```bash
# All messages
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{}'

# Latest message with key "status"
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"key":"status"}'

# By time range
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"since":1712600000,"limit":20}'
```

---

## Delete a message

```bash
nats request '$mq9.AI.MSG.DELETE.agent.inbox.5' '{}'
```

Subject pattern: `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}`

---

## Protocol summary

| Operation | Subject pattern |
| --------- | --------------- |
| Register | `$mq9.AI.AGENT.REGISTER` |
| Unregister | `$mq9.AI.AGENT.UNREGISTER` |
| Heartbeat | `$mq9.AI.AGENT.REPORT` |
| Discover agents | `$mq9.AI.AGENT.DISCOVER` |
| Create mailbox | `$mq9.AI.MAILBOX.CREATE` |
| Send message | `$mq9.AI.MSG.SEND.{mail_address}` |
| Fetch messages | `$mq9.AI.MSG.FETCH.{mail_address}` |
| ACK | `$mq9.AI.MSG.ACK.{mail_address}` |
| Query (inspect) | `$mq9.AI.MSG.QUERY.{mail_address}` |
| Delete message | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}` |

*For SDK usage in Python, Go, JavaScript, Rust, and Java — see [For Engineer](/docs/for-engineer).*
