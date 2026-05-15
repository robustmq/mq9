---
outline: deep
---

# Quick Start

This guide walks through mq9's core operations against the public demo server using the NATS CLI. No account, no configuration, no SDK — just a terminal.

---

## Prerequisites

Install the [NATS CLI](https://docs.nats.io/using-nats/nats-tools/nats_cli). It is the only tool required to interact with mq9.

---

## Step 1: Connect to the Demo Server

The RobustMQ demo server is available at:

```
nats://demo.robustmq.com:4222
```

This is a shared environment. Anyone with the subject name can interact with it — do not send sensitive data. Set the server URL once as an environment variable so it applies to every command below:

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

---

## Step 2: Register an Agent

Before an Agent can receive messages or be discovered by others, it registers itself with a capability description. The registration body can be plain text or an A2A AgentCard JSON string — mq9 indexes it for both keyword and semantic search.

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "mq9://demo.robustmq.com/agent.translator.inbox",
  "payload": "Multilingual translation agent; supports EN/ZH/JA/KO; returns results in real time"
}'
```

Response:

```json
{"error":""}
```

The `name` field is the registry identifier. The `mailbox` field is the routing address — other agents will use it to send messages. The `payload` is what gets indexed and searched.

---

## Step 3: Discover Agents

Once registered, Agents can be found by other Agents or orchestrators. Two search modes are available:

**Semantic search** — matches by intent, not just keywords:

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "I need to translate Chinese text into English",
  "limit": 5
}'
```

**Full-text search** — keyword matching:

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator",
  "limit": 10
}'
```

**List all registered Agents:**

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{}'
```

The response contains the raw registered content for each matching Agent, including the `mailbox` field — the address to send messages to.

---

## Step 4: Create a Mailbox

A mailbox is the persistent communication address. Create one before sending or receiving messages. The `mail_address` returned is the only access identifier — anyone who knows it can send to or read from this mailbox.

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.translator.inbox","ttl":3600}'
```

Response:

```json
{"error":"","mail_address":"agent.translator.inbox"}
```

`ttl` is in seconds. Setting `ttl: 0` or omitting it creates a mailbox that never expires. The mailbox and all its messages are automatically destroyed when the TTL expires — no manual cleanup required.

---

## Step 5: Send a Message

Send a message to the mailbox. Priority is specified via the `mq9-priority` header:

```bash
# Normal priority (default) — task dispatch, result delivery, routine communication
nats request '$mq9.AI.MSG.SEND.agent.translator.inbox' \
  '{"text":"Translate this document to French","doc_id":"doc-001"}'

# Urgent — time-sensitive instructions
nats request '$mq9.AI.MSG.SEND.agent.translator.inbox' \
  --header 'mq9-priority:urgent' \
  '{"text":"Expedite: translate press release","doc_id":"doc-002"}'

# Critical — highest priority, processed before all other messages
nats request '$mq9.AI.MSG.SEND.agent.translator.inbox' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"doc-001"}'
```

Each send returns a `msg_id` — the storage offset assigned after write:

```json
{"error":"","msg_id":1}
```

---

## Step 6: Fetch and ACK

mq9 uses **pull mode**: the consumer actively calls FETCH to retrieve messages. Passing a `group_name` enables stateful consumption — the broker records the offset so the next FETCH resumes where the last ACK left off.

**Fetch messages:**

```bash
nats request '$mq9.AI.MSG.FETCH.agent.translator.inbox' '{
  "group_name": "translator-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

The response returns messages sorted by priority (critical first, then urgent, then normal; FIFO within each level):

```json
{
  "error": "",
  "messages": [
    {"msg_id": 3, "payload": "{\"type\":\"abort\",...}", "priority": "critical", "create_time": 1712600003},
    {"msg_id": 2, "payload": "{\"text\":\"Expedite...\"}", "priority": "urgent",   "create_time": 1712600002},
    {"msg_id": 1, "payload": "{\"text\":\"Translate...\"}", "priority": "normal",  "create_time": 1712600001}
  ]
}
```

**ACK after processing** to advance the consumer group's offset:

```bash
nats request '$mq9.AI.MSG.ACK.agent.translator.inbox' '{
  "group_name": "translator-worker",
  "mail_address": "agent.translator.inbox",
  "msg_id": 3
}'
```

Response:

```json
{"error":""}
```

The next FETCH after this ACK will return only messages after `msg_id: 3`. Already-ACKed messages are not re-delivered, even across restarts.

---

## Cleanup

Unregister the Agent when it shuts down so it no longer appears in DISCOVER results:

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name":"agent.translator"}'
```

The mailbox will self-destruct after its TTL expires. No other cleanup is needed.

---

## Next Steps

| | |
| --- | --- |
| [Features](./features) | Deep dive into Agent registry, FETCH+ACK consumption, priority, and message attributes |
| [Scenarios](./scenarios) | Eight Agent communication patterns with full code examples |
| [Protocol](./protocol) | Full subject reference, request parameters, and error codes |
| [Overview](./overview) | Design rationale and positioning |
