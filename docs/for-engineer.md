---
title: For Engineer — mq9 Integration Guide
description: How to integrate mq9 into your stack. Code examples in Python, Go, and JavaScript. Eight real-world patterns.
---

# For Engineer

mq9 is a protocol over NATS. You use a standard NATS client — no additional library. The protocol is defined by subject naming conventions under the `$mq9.AI.*` namespace.

## Quick start

**Run RobustMQ locally:**

```bash
docker run -d --name robustmq -p 4222:4222 robustmq/robustmq:latest
```

**Verify:**

```bash
nats pub '$mq9.AI.MAILBOX.CREATE' '{}'
# → {"mail_id":"m-uuid-001","token":"tok-xxx","ttl":3600}
```

## Core operations

### Create a mailbox

```python
# Python
import asyncio, json
from nats.aio.client import Client

async def main():
    nc = await Client().connect("nats://localhost:4222")
    resp = await nc.request(
        "$mq9.AI.MAILBOX.CREATE",
        json.dumps({"type": "standard", "ttl": 3600}).encode()
    )
    mailbox = json.loads(resp.data)
    mail_id = mailbox["mail_id"]
    token   = mailbox["token"]
```

```go
// Go
nc, _ := nats.Connect(nats.DefaultURL)
resp, _ := nc.Request("$mq9.AI.MAILBOX.CREATE",
    []byte(`{"type":"standard","ttl":3600}`), 2*time.Second)

var m struct{ MailID, Token string `json:"mail_id,token"` }
json.Unmarshal(resp.Data, &m)
```

```javascript
// JavaScript
const nc = await connect({ servers: "nats://localhost:4222" });
const jc = JSONCodec();
const resp = await nc.request(
  "$mq9.AI.MAILBOX.CREATE",
  jc.encode({ type: "standard", ttl: 3600 })
);
const { mail_id, token } = jc.decode(resp.data);
```

### Send a message

```python
await nc.publish(
    f"$mq9.AI.INBOX.{target_mail_id}.normal",
    json.dumps({
        "from": mail_id,
        "type": "task",
        "correlation_id": "req-001",
        "reply_to": f"$mq9.AI.INBOX.{mail_id}.normal",
        "payload": { "data": "..." }
    }).encode()
)
```

### Subscribe and receive

```python
async def on_message(msg):
    data = json.loads(msg.data)
    print(f"From {data['from']}: {data['payload']}")

    if data.get("reply_to"):
        await nc.publish(data["reply_to"], json.dumps({
            "from": mail_id,
            "type": "result",
            "correlation_id": data["correlation_id"],
            "payload": { "status": "done" }
        }).encode())

await nc.subscribe(f"$mq9.AI.INBOX.{mail_id}.*", cb=on_message)
```

### Broadcast

```python
await nc.publish(
    "$mq9.AI.BROADCAST.pipeline.complete",
    json.dumps({ "from": mail_id, "stage": "preprocessing", "ok": True }).encode()
)

# Other agents subscribe:
await nc.subscribe("$mq9.AI.BROADCAST.pipeline.*", cb=handler)
```

### Query for missed messages

```python
resp = await nc.request(
    f"$mq9.AI.MAILBOX.QUERY.{mail_id}",
    json.dumps({"token": token}).encode()
)
result = json.loads(resp.data)
print(f"Unread: {result['unread']}")
```

## Eight real-world patterns

### 1. Child Agent reports result to parent

Parent dispatches work and waits asynchronously for results tagged with `correlation_id`.

```python
# Parent sends task
await nc.publish(f"$mq9.AI.INBOX.{worker_id}.normal", json.dumps({
    "from": parent_id,
    "type": "work",
    "correlation_id": "job-001",
    "reply_to": f"$mq9.AI.INBOX.{parent_id}.normal",
    "payload": { "data": [...] }
}).encode())

# Parent listens for results
results = {}
async def collect(msg):
    d = json.loads(msg.data)
    results[d["correlation_id"]] = d["payload"]

await nc.subscribe(f"$mq9.AI.INBOX.{parent_id}.*", cb=collect)
```

### 2. Orchestrator monitors all worker states

Workers maintain a `latest`-type mailbox for status. The orchestrator subscribes once.

```go
// Worker: create latest-type mailbox and update periodically
resp, _ := nc.Request("$mq9.AI.MAILBOX.CREATE",
    []byte(`{"type":"latest","ttl":7200}`), 2*time.Second)
// ...
nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", statusID),
    []byte(`{"from":"worker-1","status":"processing","load":0.7}`))

// Orchestrator: subscribe to all status mailboxes
nc.Subscribe("$mq9.AI.INBOX.m-status-*.normal", func(msg *nats.Msg) {
    var s map[string]interface{}
    json.Unmarshal(msg.Data, &s)
    workers[s["from"].(string)] = s
})
// When a worker's TTL expires, its status disappears → orchestrator knows it's gone
```

### 3. Task broadcast with competing workers

Multiple workers subscribe with the same queue group. Each task goes to exactly one worker.

```javascript
// Master broadcasts task
await nc.publish("$mq9.AI.BROADCAST.task.available",
  jc.encode({ from: masterId, task_id: "t-001", data: {...} }));

// Workers subscribe with shared queue group
const sub = nc.subscribe("$mq9.AI.BROADCAST.task.available",
  { queue: "task-workers" });

for await (const msg of sub) {
  const task = jc.decode(msg.data);
  const result = await process(task);
  await nc.publish(`$mq9.AI.INBOX.${masterId}.normal`,
    jc.encode({ from: workerId, task_id: task.task_id, result }));
}
```

### 4. Anomaly alert broadcast

Monitor publishes; multiple independent handlers subscribe with wildcards.

```python
# Monitor
await nc.publish("$mq9.AI.BROADCAST.system.anomaly", json.dumps({
    "from": monitor_id, "severity": "critical",
    "detail": "Timeout rate at 25%"
}).encode())

# Incident handler — reacts to critical anomalies
await nc.subscribe("$mq9.AI.BROADCAST.system.*", cb=incident_handler)

# Logger — logs all events
await nc.subscribe("$mq9.AI.BROADCAST.#", cb=logger)
```

### 5. Cloud to offline edge device

Cloud sends commands with priority. Edge reconnects, processes urgent first, queries for missed messages.

```go
// Cloud: send urgent command (edge may be offline)
nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.urgent", edgeID),
    []byte(`{"command":"emergency_stop","reason":"temperature_critical"}`))

nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", edgeID),
    []byte(`{"command":"update_config","interval":30}`))

// Edge: on reconnect, subscribe and query fallback
nc.Subscribe(fmt.Sprintf("$mq9.AI.INBOX.%s.urgent", edgeID), urgentHandler)
nc.Subscribe(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", edgeID), normalHandler)

queryResp, _ := nc.Request(
    fmt.Sprintf("$mq9.AI.MAILBOX.QUERY.%s", edgeID),
    []byte(fmt.Sprintf(`{"token":"%s"}`, edgeToken)), 2*time.Second)
```

### 6. Human-in-the-loop approval

Agent requests approval; human replies using the same protocol.

```javascript
// Agent sends approval request
await nc.publish(`$mq9.AI.INBOX.${humanMailID}.urgent`, jc.encode({
  from: agentMailID,
  type: "approval_request",
  correlation_id: "approval-001",
  content: "Call external fraud API — estimated cost $50",
  reply_to: `$mq9.AI.INBOX.${agentMailID}.normal`
}));

// Human's client receives and responds
for await (const msg of nc.subscribe(`$mq9.AI.INBOX.${humanMailID}.*`)) {
  const req = jc.decode(msg.data);
  const approved = await showApprovalUI(req);
  await nc.publish(req.reply_to, jc.encode({
    from: humanMailID,
    type: "approval_response",
    correlation_id: req.correlation_id,
    approved
  }));
}
```

### 7. Async request-reply between Agents

Agent A asks Agent B a question. B may be offline. A doesn't block.

```python
# A sends question (B may not be online)
await nc.publish(f"$mq9.AI.INBOX.{agent_b}.normal", json.dumps({
    "from": agent_a,
    "type": "question",
    "correlation_id": "q-001",
    "reply_to": f"$mq9.AI.INBOX.{agent_a}.normal",
    "question": "What is the status of job-456?"
}).encode())

# A continues working; collects replies when they arrive
pending = {}

async def handle_reply(msg):
    d = json.loads(msg.data)
    if d.get("type") == "question_reply":
        pending[d["correlation_id"]] = d["answer"]

await nc.subscribe(f"$mq9.AI.INBOX.{agent_a}.*", cb=handle_reply)

# B handles when it comes online
async def handle_question(msg):
    d = json.loads(msg.data)
    answer = query_status(d["question"])
    await nc.publish(d["reply_to"], json.dumps({
        "from": agent_b, "type": "question_reply",
        "correlation_id": d["correlation_id"], "answer": answer
    }).encode())
```

### 8. Capability registration and discovery

Agents announce capabilities on startup; orchestrators build a live index.

```go
// Agent announces
nc.Publish("$mq9.AI.BROADCAST.system.capability",
    []byte(fmt.Sprintf(`{
        "from": "%s",
        "capabilities": ["data.analysis","ml.training"],
        "reply_to": "$mq9.AI.INBOX.%s.normal"
    }`, agentID, agentID)))

// Orchestrator maintains index
index := map[string][]string{}
nc.Subscribe("$mq9.AI.BROADCAST.system.capability", func(msg *nats.Msg) {
    var reg map[string]interface{}
    json.Unmarshal(msg.Data, &reg)
    for _, cap := range reg["capabilities"].([]interface{}) {
        index[cap.(string)] = append(index[cap.(string)], reg["from"].(string))
    }
})

// Dispatch to capable Agent
for _, id := range index["ml.training"] {
    nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", id), task)
}
```

## Storage tiers

| Tier | When to use | Config |
| - | - | - |
| Memory | Heartbeats, coordination signals — loss acceptable | `"storage_tier":"memory"` |
| RocksDB | Task delivery, results, approvals — default | `"storage_tier":"rocksdb"` |
| File Segment | Audit trails, compliance, long-term records | `"storage_tier":"file_segment"` |

Specify at mailbox creation:

```json
{ "type": "standard", "ttl": 3600, "storage_tier": "rocksdb" }
```

## Deployment

**Development:**

```bash
docker run -d -p 4222:4222 robustmq/robustmq:latest
```

**Production (single node):** Single binary, no external dependencies. Suitable for thousands of Agents.

**Cluster mode:** Scale horizontally when needed. Agents use the same protocol — no code changes.

**Observability:**

```bash
# Spy on all mq9 traffic during development
nats sub '$mq9.AI.#'
```

## Pattern reference

| Scenario | Primary subject | Pattern |
| - | - | - |
| Point-to-point | `INBOX.{mail_id}.{priority}` | Send to known `mail_id` |
| Broadcast | `BROADCAST.{domain}.{event}` | Wildcard subscribers |
| Competing workers | `BROADCAST.*` | Queue group subscription |
| Status tracking | `INBOX.{status-id}.normal` | `latest`-type mailbox |
| Request-reply | `INBOX` + `reply_to` | `correlation_id` links pair |
| Capability discovery | `BROADCAST.system.capability` | Publisher-subscriber index |
| Offline delivery | `INBOX.*` | Store-first, push-on-reconnect |
| Pull fallback | `MAILBOX.QUERY.{mail_id}` | After reconnect or on timeout |

---

*See [What](/what) for design rationale. See [For Agent](/for-agent) for the Agent perspective.*
