# Features

mq9 provides two foundational capabilities for Agent networks: a built-in registry that lets Agents find each other, and a reliable async messaging layer that lets them communicate without requiring both sides to be online simultaneously.

---

## Part 1: Agent Registry

### AgentCard Model

Registration content is a free-form byte payload — plain text describing capabilities, or a structured A2A AgentCard JSON string. The only required protocol field is `mailbox`, which mq9 uses as the routing identifier when returning DISCOVER results.

Example registration body using an AgentCard structure:

```json
{
  "name": "agent.billing",
  "mailbox": "mq9://broker/agent.billing.inbox",
  "description": "Handles invoice generation, payment processing, and refund workflows",
  "skills": ["invoice", "payment", "refund"],
  "version": "1.2.0"
}
```

The entire body is indexed for full-text and semantic vector search. mq9 does not validate or transform it — content semantics are owned by the upper-layer protocol (A2A, MCP, or custom).

---

### REGISTER / UNREGISTER / REPORT

**REGISTER** — called at Agent startup. Adds the Agent to the registry and makes it discoverable.

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.code-review",
  "mailbox": "mq9://broker/agent.code-review.inbox",
  "payload": "Code review agent for Rust, Go, and Python; returns findings as structured JSON"
}'
# Response
{"error":""}
```

**UNREGISTER** — called at Agent shutdown. Removes the Agent from the registry immediately.

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{
  "mailbox": "mq9://broker/agent.code-review.inbox"
}'
# Response
{"error":""}
```

**REPORT** — periodic heartbeat. Sends a status update to the registry. The body is passed through unchanged; mq9 records the last-seen time for health tracking.

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "mailbox": "mq9://broker/agent.code-review.inbox",
  "status": "running",
  "reviewed_today": 42
}'
# Response
{"error":""}
```

---

### DISCOVER: Full-Text and Semantic Search

DISCOVER queries the registry and returns matching Agent entries.

**Full-text search** — keyword matching against the registered payload:

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{"text": "payment invoice"}'
```

**Semantic vector search** — natural language intent matching. Takes priority when both `text` and `semantic` are provided:

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "process a payment and generate invoice",
  "limit": 5
}'
```

**List all registered Agents** — omit both fields:

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{}'
```

**Pagination** — use `limit` and `page` (page starts at 1):

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "payment",
  "limit": 10,
  "page": 2
}'
```

DISCOVER returns the raw registered content for each match — the same body that was passed to REGISTER. The caller extracts the `mailbox` field to route messages.

---

### Health Tracking via Heartbeat

The typical lifecycle for a registered Agent:

```text
Agent starts  → AGENT.REGISTER (capability description)
               ↓
Running       → AGENT.REPORT every N seconds (heartbeat)
               ↓
Agent stops   → AGENT.UNREGISTER (removed from DISCOVER results immediately)
```

If an Agent crashes without calling UNREGISTER, it remains in the registry until the operator removes it or a TTL-based expiry mechanism is applied at the application layer. Orchestrators can compare DISCOVER results with the last-seen timestamps in REPORT data to identify stale entries.

---

## Part 2: Reliable Async Messaging

### Persistent Mailboxes with TTL

A mailbox is the persistent communication address. It is created on demand, holds messages until they are consumed, and is automatically destroyed when its TTL expires.

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name": "task.queue", "ttl": 86400}'
# Response
{"error":"","mail_address":"task.queue"}
```

TTL rules:

- TTL is declared at creation time in seconds; it cannot be renewed
- `ttl: 0` or omitting `ttl` creates a mailbox that never expires
- On expiry, the mailbox and all its pending messages are destroyed automatically
- Duplicate name → error: `mailbox xxx already exists` (CREATE is not idempotent)
- Use QUERY to check whether a mailbox exists before creating it

The `mail_address` is the only access boundary. Anyone who knows it can send to or read from the mailbox — no tokens, no ACLs. Unguessability is the security model.

---

### Pull + ACK Consumption Model

mq9 uses pull mode exclusively. Consumers call FETCH to retrieve messages and ACK to advance the consumer group offset. The broker tracks offset state server-side.

**Two consumption modes:**

| Mode | How to enable | Behavior |
| --- | --- | --- |
| Stateful | Pass `group_name` | Broker records offset per group; resumes from last ACK on reconnect |
| Stateless | Omit `group_name` | Each call applies the `deliver` policy independently; no offset recorded |

**Stateful offset behavior:**

| Condition | Behavior |
| --- | --- |
| Offset record exists | Resume from last ACK; `deliver` policy is ignored |
| Offset exists + `force_deliver: true` | Ignore offset; restart from `deliver` policy |
| No offset record (first FETCH) | Apply `deliver` policy to determine start position |

**deliver start policies:**

| Value | Description |
| --- | --- |
| `latest` (default) | Only messages from this point forward |
| `earliest` | Start from the oldest message in the mailbox |
| `from_time` | Start after the specified Unix timestamp |
| `from_id` | Start from the specified `msg_id` (inclusive) |

**Consumption flow:**

```text
FETCH → broker returns message list (sorted by priority)
           ↓
   client processes messages
           ↓
        ACK msg_id
           ↓
  broker advances offset for group
           ↓
  next FETCH resumes from here
```

**FETCH config options:**

| Field | Default | Description |
| --- | --- | --- |
| `num_msgs` | 100 | Maximum messages per FETCH call |
| `max_wait_ms` | 500 | How long the server waits when the mailbox is empty before returning an empty list |

---

### Three-Tier Priority

Each message declares its priority via the `mq9-priority` header. The storage layer enforces ordering — consumers receive messages in priority order without any client-side sorting.

| Priority | Header | Typical use |
| --- | --- | --- |
| `critical` (highest) | `mq9-priority: critical` | Abort signals, emergency commands, security events |
| `urgent` | `mq9-priority: urgent` | Approval requests, time-sensitive notifications |
| `normal` (default) | omit header | Task dispatch, result delivery, routine communication |

Ordering guarantees:

- Within the same priority: FIFO (send order is preserved)
- Across priorities: `critical` before `urgent` before `normal`

Example — sending messages at each priority level:

```bash
nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:critical' \
  '{"cmd":"abort","task_id":"t-001"}'

nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:urgent' \
  '{"cmd":"interrupt","task_id":"t-002"}'

nats request '$mq9.AI.MSG.SEND.task.queue' \
  '{"cmd":"process","task_id":"t-003"}'
```

A FETCH after this will return `t-001`, then `t-002`, then `t-003` — regardless of the order in which they were received at the storage layer.

---

### Message Attributes

Optional attributes are attached to a message via NATS headers at send time.

| Attribute | Header | Description |
| --- | --- | --- |
| Key deduplication | `mq9-key: {key}` | Only the latest message with the same key is retained; older ones are overwritten |
| Delayed delivery | `mq9-delay: {seconds}` | Message becomes visible to FETCH after N seconds; returns `msg_id: -1` |
| Per-message TTL | `mq9-ttl: {seconds}` | Message expires at `send_time + ttl`, independent of mailbox TTL |
| Tags | `mq9-tags: {tag1},{tag2}` | Comma-separated; filterable via the `tags` field in QUERY |

**Key deduplication** — keeps only the latest state for a given key:

```bash
# Each SEND with the same key overwrites the previous
nats request '$mq9.AI.MSG.SEND.task.001.status' \
  --header 'mq9-key:progress' '{"pct":20}'
nats request '$mq9.AI.MSG.SEND.task.001.status' \
  --header 'mq9-key:progress' '{"pct":60}'
nats request '$mq9.AI.MSG.SEND.task.001.status' \
  --header 'mq9-key:progress' '{"pct":100}'

# QUERY returns only the latest — {"pct":100}
nats request '$mq9.AI.MSG.QUERY.task.001.status' '{"key":"progress"}'
```

**Delayed delivery** — message is invisible to FETCH until the delay expires:

```bash
nats request '$mq9.AI.MSG.SEND.agent.scheduler.inbox' \
  --header 'mq9-delay:300' \
  '{"task":"run_report","scheduled_for":"T+5min"}'
# Response: {"error":"","msg_id":-1}  ← -1 indicates delayed
```

---

### Offline Delivery Guarantee

Messages written to a mailbox are persisted server-side. The recipient does not need to be online when the message is sent. When the recipient Agent comes online, it calls FETCH and retrieves all pending messages in priority order. Messages are held until consumed and ACKed, or until the mailbox or message TTL expires.

This is the core contract: **send once, the recipient gets it when they come online** — no retry logic, no reconnect handling, no bridging required.

---

### N-to-N Agent Topologies

mq9 mailboxes are not bound to a single sender or a single receiver. The same mailbox can support multiple concurrent senders and multiple concurrent consumer groups.

**Fan-in** — multiple Agents send to one shared mailbox (e.g., a task queue):

```bash
# Agent A, B, C each send to the same mailbox
nats request '$mq9.AI.MSG.SEND.task.queue' '{"from":"agent-a","task":"..."}'
nats request '$mq9.AI.MSG.SEND.task.queue' '{"from":"agent-b","task":"..."}'
```

**Fan-out** — multiple consumer groups read from the same mailbox independently. Each group has its own offset and receives all messages:

```bash
# Group 1 and Group 2 each maintain independent offsets
nats request '$mq9.AI.MSG.FETCH.task.queue' '{"group_name":"group-1","deliver":"earliest"}'
nats request '$mq9.AI.MSG.FETCH.task.queue' '{"group_name":"group-2","deliver":"earliest"}'
```

**Competing consumers** — multiple workers share one group name. Only one worker receives each message (the offset advances on ACK, preventing re-delivery to other group members):

```bash
# Worker 1 and Worker 2 share the same group — each message is delivered once
nats request '$mq9.AI.MSG.FETCH.task.queue' '{"group_name":"workers","config":{"num_msgs":1}}'
```
