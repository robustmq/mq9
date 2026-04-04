---
title: For Engineer — mq9 Integration Guide
description: How to integrate mq9 into your stack. Code examples in Python, Go, and JavaScript.
---

# For Engineer

You're building a multi-Agent system. This is your integration guide.

## The problem you're facing

Agents are not services. Services are always online — you can HTTP them, pub/sub them, stream to them. Agents spin up for a task and disappear. They restart. They go offline mid-conversation.

You've probably already hit one of these:

- Agent B is offline when Agent A sends a result. Message lost. You add a retry loop.
- You use Redis pub/sub, but offline Agents miss publishes. You add Redis Streams. Now you're managing consumer groups for ephemeral processes.
- You poll a shared database for coordination. It works, but it's slow and everyone's doing it differently.
- You scale from 10 to 100 Agents and everything breaks — too many connections, too much state, no standard pattern.

There's no standard solution for Agent-to-Agent async communication. Every team builds their own. None of it is simple. All of it breaks at scale.

## What mq9 solves

mq9 is async messaging infrastructure built specifically for Agents. You run one binary. Your Agents use any NATS client — Go, Python, Rust, JavaScript. No new SDK.

What it handles so you don't have to:

- **Offline delivery** — message arrives when the target is offline? Stored. Delivered on reconnect. No retry logic needed.
- **Point-to-point** — each Agent gets a mailbox. Send to a `mail_id`. Done.
- **Broadcast** — publish once to a subject. All subscribers receive. No subscriber list management.
- **Priority** — urgent messages processed first. Edge device comes back online after hours, processes the emergency stop before anything else.
- **Automatic cleanup** — mailboxes expire via TTL. No manual deletion, no orphaned state.
- **Competing workers** — queue groups give you one-message-per-worker without coordination overhead.

## How to integrate

### Run mq9

```bash
docker run -d --name mq9 -p 4222:4222 robustmq/robustmq:latest
```

Verify:

```bash
nats pub '$mq9.AI.MAILBOX.CREATE' '{}'
# → {"mail_id":"m-uuid-001","token":"tok-xxx","ttl":3600}
```

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

## Common patterns

### Child Agent reports result to parent

Parent dispatches work and collects results tagged with `correlation_id`.

```python
# Parent sends task
await nc.publish(f"$mq9.AI.INBOX.{worker_id}.normal", json.dumps({
    "from": parent_id,
    "type": "work",
    "correlation_id": "job-001",
    "reply_to": f"$mq9.AI.INBOX.{parent_id}.normal",
    "payload": { "data": [...] }
}).encode())

# Parent collects results
results = {}
async def collect(msg):
    d = json.loads(msg.data)
    results[d["correlation_id"]] = d["payload"]

await nc.subscribe(f"$mq9.AI.INBOX.{parent_id}.*", cb=collect)
```

### Orchestrator monitors all worker states

Workers use a `latest`-type mailbox. The orchestrator subscribes once — always sees current state, never stale history.

```go
// Worker: create latest-type mailbox, update periodically
resp, _ := nc.Request("$mq9.AI.MAILBOX.CREATE",
    []byte(`{"type":"latest","ttl":7200}`), 2*time.Second)

nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", statusID),
    []byte(`{"from":"worker-1","status":"processing","load":0.7}`))

// Orchestrator: subscribe to all status mailboxes
nc.Subscribe("$mq9.AI.INBOX.m-status-*.normal", func(msg *nats.Msg) {
    var s map[string]interface{}
    json.Unmarshal(msg.Data, &s)
    workers[s["from"].(string)] = s
})
```

### Task broadcast with competing workers

Each task goes to exactly one worker. No coordination needed.

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

### Cloud to offline edge device

Cloud sends commands. Edge may be offline for hours. On reconnect, urgent messages are processed first.

```go
// Cloud: send commands (edge may be offline)
nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.urgent", edgeID),
    []byte(`{"command":"emergency_stop","reason":"temperature_critical"}`))

nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", edgeID),
    []byte(`{"command":"update_config","interval":30}`))

// Edge: on reconnect, subscribe then query fallback
nc.Subscribe(fmt.Sprintf("$mq9.AI.INBOX.%s.urgent", edgeID), urgentHandler)
nc.Subscribe(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", edgeID), normalHandler)

queryResp, _ := nc.Request(
    fmt.Sprintf("$mq9.AI.MAILBOX.QUERY.%s", edgeID),
    []byte(fmt.Sprintf(`{"token":"%s"}`, edgeToken)), 2*time.Second)
```

### Human-in-the-loop approval

Agent requests approval. Human replies using the same protocol — no special tooling.

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

### Capability registration and discovery

Agents announce on startup. Orchestrators build a live index.

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

## Deployment

**Development:**

```bash
docker run -d -p 4222:4222 robustmq/robustmq:latest
```

**Production:** Single binary, no external dependencies. Suitable for thousands of Agents on a single node.

**Cluster mode:** Scale horizontally when needed. Agents use the same protocol — no code changes required.

**Observability:**

```bash
# Watch all mq9 traffic
nats sub '$mq9.AI.#'
```

## Pattern reference

| Scenario | Subject | Pattern |
| - | - | - |
| Point-to-point | `INBOX.{mail_id}.{priority}` | Send to known `mail_id` |
| Broadcast | `BROADCAST.{domain}.{event}` | Wildcard subscribers |
| Competing workers | `BROADCAST.*` | Queue group subscription |
| Status tracking | `INBOX.{status-id}.normal` | `latest`-type mailbox |
| Request-reply | `INBOX` + `reply_to` | `correlation_id` links the pair |
| Capability discovery | `BROADCAST.system.capability` | Publisher-subscriber index |
| Offline delivery | `INBOX.*` | Store-first, push-on-reconnect |
| Pull fallback | `MAILBOX.QUERY.{mail_id}` | After reconnect or on timeout |

---

*See [What](/what) for design rationale. See [For Agent](/for-agent) for the Agent perspective.*
