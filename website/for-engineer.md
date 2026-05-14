---
title: For Engineer — mq9 Integration Guide
description: How to integrate mq9 into your stack. Quick start, SDK examples, deployment, and common patterns.
---

# For Engineer

You're building a multi-Agent system. This is your integration guide.

> This page assumes you've read [What is mq9](/what). It focuses on integration code and production considerations.

## Quick start — public demo server

No local setup needed. Connect to the RobustMQ demo server:

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

This is a shared environment — do not send sensitive data.

### Create a mailbox

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"quickstart.demo","ttl":300}'
# {"error":"","mail_address":"quickstart.demo"}
```

### Send messages with priority

```bash
# Critical — processed first
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# Normal (default, no header)
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  '{"type":"task","payload":"process dataset A"}'
```

### Fetch and ACK

```bash
# Fetch — returns messages in priority order (critical → urgent → normal)
nats request '$mq9.AI.MSG.FETCH.quickstart.demo' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'

# ACK — advance offset to last processed msg_id
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

## Core operations (SDK examples)

### Create a mailbox with the SDK

```python
# Python
from mq9 import Mq9Client
client = await Mq9Client.connect("nats://localhost:4222")
address = await client.mailbox_create(name="agent.inbox", ttl=3600)
```

```go
// Go
client, _ := mq9.Connect("nats://localhost:4222")
address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
```

```typescript
// TypeScript
const client = new Mq9Client("nats://localhost:4222");
await client.connect();
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
```

- `name = ""` (Python: `None`, Go: `""`) — broker auto-generates the address.
- `ttl = 0` — mailbox never expires.

### Send a message

```python
# Python — with priority and options
msg_id = await client.send(
    "agent.inbox",
    b'{"task":"analyze","data":"..."}',
    priority=Priority.URGENT,
    key="state",       # dedup — only latest with this key is kept
    delay=60,          # deliver after 60 seconds
    ttl=300,           # message expires in 300 s
    tags=["billing"],
)
```

```go
// Go
msgId, _ := client.Send(ctx, "agent.inbox", []byte(`{"task":"analyze"}`), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
    Key:      "state",
    Delay:    60,
})
```

### Fetch messages (pull + ACK)

```python
# Python — stateful consumption
from mq9 import FetchOptions
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

**Stateless fetch** — omit `group_name`. Each call is independent; no offset is recorded. Use for one-off reads and inspection.

### Continuous consumption loop

Use `consume()` for an automatic poll-and-process loop:

```python
# Python
consumer = await client.consume(
    "agent.inbox",
    handler=async_handler,
    group_name="workers",
    auto_ack=True,
    error_handler=lambda msg, err: print(f"msg {msg.msg_id} failed: {err}"),
)
# ... do other work ...
await consumer.stop()
print(f"processed: {consumer.processed_count}")
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

- Handler throws / returns error → message **not ACKed**, `errorHandler` called, loop continues.
- `consumer.stop()` drains the current batch and exits cleanly.

### Agent registry

```python
# Register at startup
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

---

## Common patterns

### Sub-Agent result delivery

Parent creates a private reply mailbox and shares it with the sub-agent at spawn time. Sub-agent deposits result. Parent FETCHes asynchronously — no polling, no shared state.

```python
# Parent: create private reply mailbox
reply_address = await client.mailbox_create(ttl=3600)

# Parent: send task to sub-agent with reply_to
await client.send("task.dispatch", json.dumps({
    "task": "summarize /data/corpus",
    "reply_to": reply_address,
}).encode())

# Parent: FETCH result whenever ready (non-blocking)
messages = await client.fetch(reply_address, group_name="orchestrator", deliver="earliest")
```

### Multi-worker task queue

Multiple workers share the same `group_name`. Each task is processed by exactly one worker — no coordination, no duplicate processing. Workers join or leave at any time without reconfiguration.

```python
# Producer: publish tasks with priority
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

Cloud publishes to the edge agent's private mailbox. Edge agent may be offline for hours. On reconnect, it FETCHes all pending commands in priority order — critical reconfiguration before routine tasks.

```go
// Cloud: publish commands (edge may be offline)
client.Send(ctx, "edge.agent", []byte(`{"cmd":"reconfigure","params":{"rate":100}}`),
    mq9.SendOptions{Priority: mq9.PriorityCritical})

client.Send(ctx, "edge.agent", []byte(`{"cmd":"run_diagnostic"}`), mq9.SendOptions{})

// Edge: on reconnect, fetch all pending in priority order
messages, _ := client.Fetch(ctx, "edge.agent", mq9.FetchOptions{
    GroupName: "edge-agent",
    Deliver:   "earliest",
    NumMsgs:   10,
})
```

### Human-in-the-loop approval

The human's client uses the exact same protocol as any Agent — no webhooks, no routing middleware.

```typescript
// Agent: send approval request to human's mailbox
await client.send(humanMailAddress, JSON.stringify({
  type: "approval_request",
  action: "delete_dataset",
  target: "ds-prod-2024",
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

Agent A asks Agent B a question, then continues other work. Agent B processes at its own pace and replies to A's private reply mailbox.

```bash
# Agent A: create private reply mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl":600}'
# → {"mail_address":"reply.a1b2c3"}

# Agent A: send request to Agent B with reply_to
nats request '$mq9.AI.MSG.SEND.agent.b' '{
  "request":"translate","text":"Hello world","lang":"fr","reply_to":"reply.a1b2c3"
}'

# Agent B: fetch its queue and reply
nats request '$mq9.AI.MSG.FETCH.agent.b' '{"group_name":"b-worker","deliver":"earliest"}'
nats request '$mq9.AI.MSG.SEND.reply.a1b2c3' '{"result":"Bonjour le monde"}'
nats request '$mq9.AI.MSG.ACK.agent.b' '{"group_name":"b-worker","mail_address":"agent.b","msg_id":1}'

# Agent A: FETCH reply whenever ready
nats request '$mq9.AI.MSG.FETCH.reply.a1b2c3' '{"deliver":"earliest"}'
```

---

## LangChain / LangGraph integration

`langchain-mq9` is an official toolkit that wraps all mq9 operations as LangChain tools. Works with both LangChain and LangGraph out of the box.

```bash
pip install langchain-mq9
```

**8 tools included:**

| Tool | Operation |
| ---- | --------- |
| `create_mailbox` | Create a private mailbox |
| `send_message` | Send a message with priority |
| `fetch_messages` | Pull messages (FETCH + ACK model) |
| `ack_messages` | Advance consumer group offset |
| `query_messages` | Inspect mailbox read-only |
| `delete_message` | Delete a specific message |
| `agent_register` | Register this agent with capabilities |
| `agent_discover` | Find agents by text or semantic search |

**LangChain:**

```python
from langchain_mq9 import Mq9Toolkit
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI

toolkit = Mq9Toolkit(server="nats://localhost:4222")
tools = toolkit.get_tools()

llm = ChatOpenAI(model="gpt-4o")
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
result = executor.invoke({"input": "Create a mailbox and send me a task summary"})
```

**LangGraph:**

```python
from langgraph.prebuilt import create_react_agent
from langchain_mq9 import Mq9Toolkit

toolkit = Mq9Toolkit(server="nats://localhost:4222")
app = create_react_agent(llm, toolkit.get_tools())
result = await app.ainvoke({"messages": [("human", "Discover all registered agents")]})
```

**Manual tool usage (no LLM):**

```python
tools_by_name = {t.name: t for t in toolkit.get_tools()}

address = await tools_by_name["create_mailbox"]._arun(ttl=300)
await tools_by_name["send_message"]._arun(mail_address=address, content="hello")
result = await tools_by_name["fetch_messages"]._arun(mail_address=address, group_name="workers")
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

| Error message                | Cause                                                 |
| ---------------------------- | ----------------------------------------------------- |
| `mailbox xxx already exists` | CREATE called with a name that already exists         |
| `mailbox not found`          | Mailbox does not exist or has expired                 |
| `message not found`          | The specified `msg_id` does not exist or has expired  |
| `invalid mail_address`       | Format is invalid (uppercase, hyphens, etc.)          |
| `agent not found`            | UNREGISTER or REPORT called with unknown Agent name   |

SDK exceptions: all SDKs throw/return `Mq9Error` for non-empty `error` responses.

---

## Deployment

### Development (Docker)

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

Mount `-v mq9-data:/data` to persist mailboxes and messages across restarts.

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

- Port `4222` — mq9/NATS protocol (Agent connections)
- Port `9090` — Prometheus metrics endpoint

A single node handles millions of concurrent Agent connections and is sufficient for most production workloads.

### Cluster mode

Scale horizontally when a single node is not enough. Agents use the same SDK — no client code changes required.

---

## Pattern reference

| Scenario               | Key feature                             |
| ---------------------- | --------------------------------------- |
| Point-to-point         | Private mailbox + FETCH + ACK           |
| Competing workers      | Shared `group_name` across workers      |
| Broadcast              | Named public mailbox, multiple fetchers |
| Request-reply          | Private reply mailbox + `reply_to`      |
| Offline delivery       | Store-first, FETCH on reconnect         |
| Capability discovery   | AGENT.REGISTER + AGENT.DISCOVER         |
| Cloud-to-edge          | Priority ordering on reconnect          |
| Human-in-the-loop      | Same protocol for humans and Agents     |

*See [What](/what) for design rationale. See [For Agent](/for-agent) for the Agent protocol perspective.*
