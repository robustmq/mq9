---
title: For Engineer — mq9 Integration Guide
description: What problems mq9 solves for engineers building multi-agent systems, with integration code and deployment guidance.
---

# For Engineer

You're building a multi-agent system. Here's what mq9 solves for you and how to integrate it.

## The problems mq9 solves for you

**You need agents to find each other without hardcoding addresses.**

Agents spin up dynamically. A new translation agent, a new risk-scoring agent, a new summarizer — how does your orchestrator know where to send work? Without a registry, you hardcode addresses, maintain config files, or write your own directory service. Every team rebuilds this.

mq9 gives every agent a place to publish its capabilities at startup. Other agents search by keyword or natural language intent. No manual address management.

**You need reliable delivery when agents aren't always online.**

Agents are task-driven — they start, run, and stop. When agent A sends to agent B and B is offline, the message is lost. HTTP requires both sides online. Redis pub/sub has no persistence. Kafka requires pre-created topics.

mq9 gives every agent a persistent mailbox. Send a message — it's stored until the recipient fetches it. The recipient comes online hours later, FETCHes in priority order, ACKs, and continues. No message lost.

**You need both in one system.**

Running etcd for discovery and Kafka for messaging means two codebases to maintain, two failure modes to handle, and two operational planes to monitor. mq9 unifies agent registry and persistent messaging in one broker.

---

## Quick start — public demo server

No local setup needed. Connect to the RobustMQ demo server:

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

This is a shared environment — do not send sensitive data.

### Register an agent

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; EN/ZH/JA/KO"
}'
```

### Discover agents by intent

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "translate Chinese to English",
  "limit": 5
}'
# → [{"name":"agent.translator","mailbox":"agent.translator","payload":"..."}]
```

### Create a mailbox and send

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"quickstart.demo","ttl":300}'

nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'
```

### Fetch and ACK

```bash
nats request '$mq9.AI.MSG.FETCH.quickstart.demo' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'

nats request '$mq9.AI.MSG.ACK.quickstart.demo' '{
  "group_name": "my-worker",
  "mail_address": "quickstart.demo",
  "msg_id": 3
}'
```

---

## Install an SDK

mq9 provides official SDKs that wrap the NATS protocol calls with typed APIs:

```bash
pip install mq9           # Python
npm install mq9           # JavaScript / TypeScript
go get github.com/robustmq/mq9/go   # Go
cargo add mq9             # Rust
```

```xml
<!-- Java (Maven) -->
<dependency>
  <groupId>io.mq9</groupId>
  <artifactId>mq9</artifactId>
  <version>0.1.0</version>
</dependency>
```

---

## SDK examples

### Register and discover agents

```python
# Python — register at startup
await client.agent_register({
    "name": "agent.translator",
    "mailbox": "agent.translator",
    "payload": "Multilingual translation; EN/ZH/JA/KO",
})

# Discover by semantic intent
agents = await client.agent_discover(semantic="translate Chinese to English", limit=5)

# Report heartbeat
await client.agent_report({"name": "agent.translator", "report_info": "running"})

# Unregister at shutdown
await client.agent_unregister("agent.translator")
```

```go
// Go — register and discover
client.AgentRegister(ctx, mq9.AgentInfo{
    Name:    "agent.translator",
    Mailbox: "agent.translator",
    Payload: "Multilingual translation; EN/ZH/JA/KO",
})
agents, _ := client.AgentDiscover(ctx, mq9.DiscoverOptions{
    Semantic: "translate Chinese to English",
    Limit:    5,
})
```

### Create a mailbox and send messages

```python
# Python
from mq9 import Mq9Client
client = await Mq9Client.connect("nats://localhost:4222")
address = await client.mailbox_create(name="agent.inbox", ttl=3600)

msg_id = await client.send(
    "agent.inbox",
    b'{"task":"analyze","data":"..."}',
    priority=Priority.URGENT,
    key="state",    # dedup — only latest with this key is kept
    delay=60,       # deliver after 60 seconds
    ttl=300,        # message expires in 300 s
    tags=["billing"],
)
```

```go
// Go
address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
    Key:      "state",
    Delay:    60,
})
```

```typescript
// TypeScript
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
await client.send(address, { task: "analyze" }, { priority: Priority.URGENT });
```

- `name = ""` — broker auto-generates the address.
- `ttl = 0` — mailbox never expires.

### Fetch messages (pull + ACK)

```python
# Python — stateful consumption
messages = await client.fetch("agent.inbox", group_name="workers", deliver="earliest")
for msg in messages:
    process(msg)
    await client.ack("agent.inbox", "workers", msg.msg_id)
```

```go
// Go
messages, _ := client.Fetch(ctx, "agent.inbox", mq9.FetchOptions{
    GroupName: "workers",
    Deliver:   "earliest",
})
for _, msg := range messages {
    process(msg)
    client.Ack(ctx, "agent.inbox", "workers", msg.MsgID)
}
```

ACK the **last `msg_id` in the batch** — one call confirms the whole batch. The next FETCH resumes from there.

**Stateless fetch** — omit `group_name`. Each call is independent; no offset is recorded.

### Continuous consumption loop

```python
# Python
consumer = await client.consume(
    "agent.inbox",
    handler=async_handler,
    group_name="workers",
    auto_ack=True,
    error_handler=lambda msg, err: print(f"msg {msg.msg_id} failed: {err}"),
)
await consumer.stop()
```

```typescript
// TypeScript
const consumer = await client.consume("task.inbox", async (msg) => {
  const data = JSON.parse(new TextDecoder().decode(msg.payload));
  console.log(data);
}, {
  groupName: "workers",
  autoAck: true,
  errorHandler: async (msg, err) => console.error(`msg ${msg.msgId} failed:`, err),
});
await consumer.stop();
```

- Handler throws → message not ACKed, `errorHandler` called, loop continues.
- `consumer.stop()` drains the current batch and exits cleanly.

---

## Common patterns

### Capability-based routing

Orchestrator discovers agents dynamically at runtime, routes work by intent rather than hardcoded address.

```python
agents = await client.agent_discover(semantic="summarize PDF documents", limit=3)
if agents:
    await client.send(agents[0]["mailbox"], task_payload)
```

### Sub-agent result delivery

Parent creates a private reply mailbox and passes it to the sub-agent. No polling, no shared state, no webhook setup.

```python
# Parent: create private reply mailbox
reply_address = await client.mailbox_create(ttl=3600)

# Parent: send task with reply_to
await client.send("task.dispatch", json.dumps({
    "task": "summarize /data/corpus",
    "reply_to": reply_address,
}).encode())

# Parent: FETCH result whenever ready
messages = await client.fetch(reply_address, group_name="orchestrator", deliver="earliest")
```

### Multi-worker task queue

Multiple workers share the same `group_name`. Each task goes to exactly one worker — no coordination, no duplicates. Workers join or leave at any time without reconfiguration.

```python
# Producer
await client.send("task.queue",
    b'{"task":"reindex","id":"t-101"}',
    priority=Priority.CRITICAL,
)

# Worker A and Worker B — same group_name
messages = await client.fetch("task.queue", group_name="workers", num_msgs=1)
for msg in messages:
    await process(msg)
    await client.ack("task.queue", "workers", msg.msg_id)
```

### Cloud-to-edge command delivery

Cloud publishes to the edge agent's mailbox. Edge agent may be offline for hours. On reconnect it FETCHes all pending commands in priority order — critical reconfiguration before routine tasks.

```go
client.Send(ctx, "edge.agent", []byte(`{"cmd":"reconfigure"}`),
    mq9.SendOptions{Priority: mq9.PriorityCritical})

client.Send(ctx, "edge.agent", []byte(`{"cmd":"run_diagnostic"}`), mq9.SendOptions{})

// Edge: on reconnect, fetch in priority order
messages, _ := client.Fetch(ctx, "edge.agent", mq9.FetchOptions{
    GroupName: "edge-agent",
    Deliver:   "earliest",
    NumMsgs:   10,
})
```

### Human-in-the-loop approval

The human's client uses the exact same protocol — no webhooks, no routing middleware, no separate notification system.

```typescript
// Agent: send approval request to human's mailbox
await client.send(humanMailAddress, JSON.stringify({
  type: "approval_request",
  action: "delete_dataset",
  reply_to: agentMailAddress,
}), { priority: Priority.URGENT });

// Human's client — same SDK
const consumer = await client.consume(humanMailAddress, async (req) => {
  const data = JSON.parse(new TextDecoder().decode(req.payload));
  const approved = await showApprovalUI(data);
  await client.send(data.reply_to, JSON.stringify({ approved, reviewer: "alice" }));
});
```

### Async request-reply

Agent A asks Agent B a question, continues other work, fetches the reply when ready.

```bash
# Agent A: create private reply mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl":600}'
# → {"mail_address":"reply.a1b2c3"}

# Agent A: send request with reply_to
nats request '$mq9.AI.MSG.SEND.agent.b' '{
  "request":"translate","text":"Hello world","lang":"fr","reply_to":"reply.a1b2c3"
}'

# Agent B: process and reply
nats request '$mq9.AI.MSG.FETCH.agent.b' '{"group_name":"b-worker","deliver":"earliest"}'
nats request '$mq9.AI.MSG.SEND.reply.a1b2c3' '{"result":"Bonjour le monde"}'
nats request '$mq9.AI.MSG.ACK.agent.b' '{"group_name":"b-worker","mail_address":"agent.b","msg_id":1}'

# Agent A: FETCH reply whenever ready
nats request '$mq9.AI.MSG.FETCH.reply.a1b2c3' '{"deliver":"earliest"}'
```

---

## LangChain / LangGraph integration

`langchain-mq9` wraps all mq9 operations as LangChain tools so your LLM-powered agents can register, discover, send, and receive without custom code.

```bash
pip install langchain-mq9
```

**8 tools included:**

| Tool | Operation |
| ---- | --------- |
| `agent_register` | Register this agent with capabilities |
| `agent_discover` | Find agents by text or semantic search |
| `create_mailbox` | Create a private mailbox |
| `send_message` | Send a message with priority |
| `fetch_messages` | Pull messages (FETCH + ACK model) |
| `ack_messages` | Advance consumer group offset |
| `query_messages` | Inspect mailbox read-only |
| `delete_message` | Delete a specific message |

```python
from langchain_mq9 import Mq9Toolkit
from langgraph.prebuilt import create_react_agent

toolkit = Mq9Toolkit(server="nats://localhost:4222")
app = create_react_agent(llm, toolkit.get_tools())
result = await app.ainvoke({"messages": [("human", "Discover all registered agents")]})
```

---

## MCP server

mq9 exposes a Model Context Protocol (MCP) server on the RobustMQ Admin Server. Connect any MCP-compatible client (Claude Desktop, Cursor, etc.):

```text
http://<admin-server>:<port>/mcp
```

---

## Error handling

All protocol responses include an `error` field. An empty string means success.

| Error message | Cause |
| ------------- | ----- |
| `mailbox xxx already exists` | CREATE called with a name that already exists |
| `mailbox not found` | Mailbox does not exist or has expired |
| `message not found` | The specified `msg_id` does not exist or has expired |
| `invalid mail_address` | Format is invalid (uppercase, hyphens, etc.) |
| `agent not found` | UNREGISTER or REPORT called with unknown agent name |

SDK exceptions: all SDKs throw/return `Mq9Error` for non-empty `error` responses.

---

## Deployment

### Development (Docker)

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

### Production — single node

```bash
docker run -d \
  --name mq9 \
  -p 4222:4222 \
  -p 9090:9090 \
  -v /data/mq9:/data \
  --restart unless-stopped \
  robustmq/robustmq:latest
```

- Port `4222` — mq9/NATS protocol (agent connections)
- Port `9090` — Prometheus metrics endpoint

A single node handles millions of concurrent agent connections.

### Cluster mode

Scale horizontally when a single node is not enough. Agents use the same SDK — no client code changes required.

---

## Pattern reference

| Scenario | Key feature |
| -------- | ----------- |
| Capability routing | AGENT.REGISTER + AGENT.DISCOVER → send to found agent |
| Point-to-point | Private mailbox + FETCH + ACK |
| Competing workers | Shared `group_name` across workers |
| Request-reply | Private reply mailbox + `reply_to` |
| Offline delivery | Store-first, FETCH on reconnect |
| Cloud-to-edge | Priority ordering on reconnect |
| Human-in-the-loop | Same protocol for humans and agents |

*See [What is mq9](/docs/what) for design rationale. See [For Agent](/docs/for-agent) for the agent protocol perspective.*
