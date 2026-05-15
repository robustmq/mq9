---
title: For Agent — mq9 Protocol Manual
description: Protocol reference for AI Agents — registration, discovery, mailbox, send, fetch, ACK, priority.
---

# For Agent

You are an AI Agent. This is your protocol manual.

> This page describes the wire protocol. For typed SDK usage — see [For Engineer](/for-engineer).

## The problem you face

You are ephemeral. You spin up to handle a task, then go dark. You might restart unexpectedly. You might be busy when a message arrives. You might not even exist yet when another agent tries to reach you.

Beyond delivery reliability, there is a second problem: you don't know who else is out there. Other agents with complementary capabilities are running somewhere, but their addresses are not in your context. You can't collaborate with agents you can't find.

mq9 solves both.

## What mq9 gives you

**A registry** — announce yourself, get found. Other agents search for you by capability. You search for them the same way. No hard-coded addresses, no central configuration file.

**A mailbox** — a persistent address that holds messages until you fetch them. Send a message to any agent, whether they're online or not. Fetch your mail when you start up. Messages survive your downtime in priority order — critical commands first.

## Operations

### REGISTER — announce yourself

Register at startup so other agents can find you. Your registration payload is your **AgentCard** — name plus a free-text capability description. mq9 indexes it for both keyword and semantic vector search.

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; supports EN/ZH/JA/KO; returns results in real time"
}'
```

Send periodic heartbeats while running:

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "agent.translator",
  "report_info": "running, processed: 512 tasks"
}'
```

### DISCOVER — find other agents

Search the registry without knowing addresses in advance. Two search modes:

```bash
# Semantic vector search — natural language intent
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

Response includes matching agents with their names and mailbox addresses. Send directly to the returned `mailbox` field — no further lookup needed.

### MAILBOX.CREATE — get a persistent address

Before other agents can reach you, create a mailbox. The returned `mail_address` is your delivery address.

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.inbox","ttl":3600}'
```

Response:

```json
{"error": "", "mail_address": "agent.inbox"}
```

- `ttl` — mailbox lives for N seconds, then auto-expires with all its messages.
- `ttl: 0` — mailbox never expires. TTL cannot be changed after creation.
- **Name must be unique.** Duplicate name returns an error.

**mail_address format:** lowercase letters, digits, and dots only. 1–128 characters. Examples: `agent.inbox`, `task.queue.v2`, `session.20260502`.

**Unguessability is your security boundary.** Anyone who knows your `mail_address` can send to it or fetch from it. Keep private mailboxes private.

You can have multiple mailboxes for different concerns:

```bash
# Private inbox for task assignments
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl":7200}'

# Shared public queue for competing workers
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"task.queue","ttl":86400}'
```

### MSG.SEND — send a message

You know another agent's `mail_address` (from DISCOVER or shared out-of-band). Send to it. They may be offline — mq9 stores it.

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
| `mq9-delay: 60` | Delay delivery by 60 seconds; returns `msg_id: -1` |
| `mq9-ttl: 300` | Message expires in 300 s regardless of mailbox TTL |

**Message body fields (recommended convention, not enforced):**

| Field | Purpose |
| ----- | ------- |
| `from` | Sender's `mail_address` |
| `type` | Message kind: `task`, `result`, `question`, `approval_request` |
| `correlation_id` | Links a message to its reply |
| `reply_to` | The `mail_address` where you want the response sent |
| `payload` | The actual content — mq9 does not inspect or validate it |

mq9 treats the message body as opaque bytes. These fields are a convention, not a protocol requirement.

### MSG.FETCH — pull messages

mq9 uses **pull mode**. You actively FETCH when you're ready — no push subscription.

```bash
nats request '$mq9.AI.MSG.FETCH.agent.inbox' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

Response — sorted by priority (`critical` → `urgent` → `normal`, FIFO within each tier):

```json
{
  "error": "",
  "messages": [
    {"msg_id": 1, "payload": "...", "priority": "critical", "create_time": 1712600001},
    {"msg_id": 3, "payload": "...", "priority": "normal",   "create_time": 1712600003}
  ]
}
```

**`deliver` start policies:**

| Value | Description |
| ----- | ----------- |
| `latest` | Only messages arriving from this point on |
| `earliest` | Start from the oldest message in the mailbox |
| `from_time` | Start from after a Unix timestamp |
| `from_id` | Start from a specific `msg_id` |

**`group_name`** enables stateful consumption: the broker records your offset. After ACK, the next FETCH resumes from where you left off — no duplicate delivery. Omit `group_name` for stateless one-off reads.

### MSG.ACK — advance your offset

After processing a batch, ACK to advance your consumption offset:

```bash
nats request '$mq9.AI.MSG.ACK.agent.inbox' '{
  "group_name": "my-worker",
  "mail_address": "agent.inbox",
  "msg_id": 3
}'
```

Pass the `msg_id` of the **last message in the batch** — one ACK confirms the whole batch.

**FETCH + ACK flow:**

```text
FETCH (group_name=my-worker, deliver=earliest)
  │
  └─→ [msg_id:1 critical] [msg_id:2 urgent] [msg_id:3 normal]
         │                      │                   │
       process               process             process
                                                     │
                                              ACK (msg_id:3)
                                                     │
                                         broker advances offset to 3
                                                     │
                                next FETCH resumes from msg_id:4
```

### MSG.QUERY — inspect without consuming

QUERY returns stored messages **without affecting your consumption offset**. Use for debugging or state inspection.

```bash
# All messages
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{}'

# Latest message with key "status"
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"key":"status"}'

# By time range
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"since":1712600000,"limit":20}'
```

QUERY never moves your offset. Two consecutive QUERYs return the same result (assuming no new messages arrive).

### MSG.DELETE — delete a specific message

```bash
nats request '$mq9.AI.MSG.DELETE.agent.inbox.5' '{}'
```

Subject pattern: `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}`

### AGENT.REPORT — send a heartbeat

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "agent.translator",
  "report_info": "running, processed: 512 tasks"
}'
```

Send periodically while the agent is active. Heartbeats allow the registry to surface freshness metadata to agents that discover you.

### AGENT.UNREGISTER — deregister at shutdown

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name":"agent.translator"}'
```

## Protocol overview

| Operation | Subject pattern |
| --------- | --------------- |
| Register Agent | `$mq9.AI.AGENT.REGISTER` |
| Discover Agents | `$mq9.AI.AGENT.DISCOVER` |
| Report status | `$mq9.AI.AGENT.REPORT` |
| Unregister Agent | `$mq9.AI.AGENT.UNREGISTER` |
| Create mailbox | `$mq9.AI.MAILBOX.CREATE` |
| Send message | `$mq9.AI.MSG.SEND.{mail_address}` |
| Fetch messages | `$mq9.AI.MSG.FETCH.{mail_address}` |
| ACK | `$mq9.AI.MSG.ACK.{mail_address}` |
| Query (inspect) | `$mq9.AI.MSG.QUERY.{mail_address}` |
| Delete message | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}` |

*For SDK usage in Python, Go, JavaScript, Rust, and Java — see [For Engineer](/for-engineer).*
