---
title: For Engineer — mq9 Integration Guide
description: How to integrate mq9 into your stack. Code examples in Python, Go, and JavaScript.
---

# For Engineer

You're building a multi-Agent system. This is your integration guide.

> This page assumes you've read [What is mq9](/what). It focuses on integration code and production considerations — not concept explanations.

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
- **Priority** — urgent messages processed first.
- **Automatic cleanup** — mailboxes expire via TTL. No manual deletion, no orphaned state.
- **Competing workers** — queue groups give you one-message-per-worker without coordination overhead.

## 30-second demo

Two Agents, one message, end to end. Copy and run.

```python
# demo.py — requires: pip install nats-py
import asyncio, json
import nats

async def main():
    nc = await nats.connect("nats://localhost:4222")

    # Agent A creates a mailbox
    resp = await nc.request("$mq9.AI.MAILBOX.CREATE",
        json.dumps({"type": "standard", "ttl": 3600}).encode())
    agent_a = json.loads(resp.data)
    print(f"Agent A mailbox: {agent_a['mail_id']}")

    # Agent B creates a mailbox
    resp = await nc.request("$mq9.AI.MAILBOX.CREATE",
        json.dumps({"type": "standard", "ttl": 3600}).encode())
    agent_b = json.loads(resp.data)
    print(f"Agent B mailbox: {agent_b['mail_id']}")

    received = asyncio.Event()

    # Agent B subscribes to its inbox
    async def on_message(msg):
        data = json.loads(msg.data)
        print(f"Agent B received: {data['payload']}")
        # Reply to Agent A
        if data.get("reply_to"):
            await nc.publish(data["reply_to"],
                json.dumps({"from": agent_b["mail_id"],
                            "type": "result",
                            "correlation_id": data["correlation_id"],
                            "payload": "task complete"}).encode())
        received.set()

    await nc.subscribe(f"$mq9.AI.INBOX.{agent_b['mail_id']}.*", cb=on_message)

    # Agent A sends a task to Agent B
    await nc.publish(f"$mq9.AI.INBOX.{agent_b['mail_id']}.normal",
        json.dumps({"from": agent_a["mail_id"],
                    "type": "task",
                    "correlation_id": "demo-001",
                    "reply_to": f"$mq9.AI.INBOX.{agent_a['mail_id']}.normal",
                    "payload": "analyze this"}).encode())
    print("Agent A sent task")

    await received.wait()
    await nc.close()

asyncio.run(main())
```

Run mq9 first:

```bash
docker run -d -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
python demo.py
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

var m struct {
    MailID string `json:"mail_id"`
    Token  string `json:"token"`
}
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

### Child Agent reports result to parent {#pattern-child-result}

```python
# Parent sends task
await nc.publish(f"$mq9.AI.INBOX.{worker_id}.normal", json.dumps({
    "from": parent_id,
    "type": "work",
    "correlation_id": "job-001",
    "reply_to": f"$mq9.AI.INBOX.{parent_id}.normal",
    "payload": { "data": [] }
}).encode())

# Parent collects results — non-blocking
results = {}
async def collect(msg):
    d = json.loads(msg.data)
    results[d["correlation_id"]] = d["payload"]

await nc.subscribe(f"$mq9.AI.INBOX.{parent_id}.*", cb=collect)
```

### Orchestrator monitors all worker states {#pattern-orchestrator}

```go
// Worker: latest-type mailbox, state updates overwrite previous
resp, _ := nc.Request("$mq9.AI.MAILBOX.CREATE",
    []byte(`{"type":"latest","ttl":7200}`), 2*time.Second)

nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", statusID),
    []byte(`{"from":"worker-1","status":"processing","load":0.7}`))

// Orchestrator: one subscription covers all workers
nc.Subscribe("$mq9.AI.INBOX.m-status-*.normal", func(msg *nats.Msg) {
    var s map[string]interface{}
    json.Unmarshal(msg.Data, &s)
    workers[s["from"].(string)] = s
    // When a worker's TTL expires, its state stops arriving → treat as offline
})
```

### Task broadcast with competing workers {#pattern-competing}

```javascript
// Master broadcasts task
await nc.publish("$mq9.AI.BROADCAST.task.available",
  jc.encode({ from: masterId, task_id: "t-001", data: {} }));

// Workers subscribe with shared queue group — each task goes to exactly one worker
const sub = nc.subscribe("$mq9.AI.BROADCAST.task.available",
  { queue: "task-workers" });

for await (const msg of sub) {
  const task = jc.decode(msg.data);
  const result = await process(task);
  await nc.publish(`$mq9.AI.INBOX.${masterId}.normal`,
    jc.encode({ from: workerId, task_id: task.task_id, result }));
}
```

### Cloud to offline edge device {#pattern-edge}

```go
// Cloud: send commands — edge may be offline for hours
nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.urgent", edgeID),
    []byte(`{"command":"emergency_stop","reason":"temperature_critical"}`))

nc.Publish(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", edgeID),
    []byte(`{"command":"update_config","interval":30}`))

// Edge: on reconnect, subscribe (urgent first) then query fallback
nc.Subscribe(fmt.Sprintf("$mq9.AI.INBOX.%s.urgent", edgeID), urgentHandler)
nc.Subscribe(fmt.Sprintf("$mq9.AI.INBOX.%s.normal", edgeID), normalHandler)

queryResp, _ := nc.Request(
    fmt.Sprintf("$mq9.AI.MAILBOX.QUERY.%s", edgeID),
    []byte(fmt.Sprintf(`{"token":"%s"}`, edgeToken)), 2*time.Second)
```

### Human-in-the-loop approval {#pattern-human}

```javascript
// Agent sends approval request
await nc.publish(`$mq9.AI.INBOX.${humanMailID}.urgent`, jc.encode({
  from: agentMailID,
  type: "approval_request",
  correlation_id: "approval-001",
  content: "Call external fraud API — estimated cost $50",
  reply_to: `$mq9.AI.INBOX.${agentMailID}.normal`
}));

// Human's client — same protocol, no special tooling
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

### Capability registration and discovery {#pattern-capability}

```go
// Agent announces capabilities on startup
nc.Publish("$mq9.AI.BROADCAST.system.capability",
    []byte(fmt.Sprintf(`{
        "from": "%s",
        "capabilities": ["data.analysis","ml.training"],
        "reply_to": "$mq9.AI.INBOX.%s.normal"
    }`, agentID, agentID)))

// Orchestrator builds live index from announcements
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

## Error handling

| Situation | What happens | What to do |
| - | - | - |
| `MAILBOX.CREATE` fails | Returns error response | Retry with backoff; check server connectivity |
| Send to expired `mail_id` | Message dropped silently | Validate `mail_id` is still active before sending critical messages |
| `MAILBOX.QUERY` with wrong token | Returns auth error | Store token securely; recreate mailbox if token is lost |
| TTL expires before Agent reconnects | Mailbox and all messages deleted | Set TTL longer than your worst-case offline window |
| Message exceeds size limit | Rejected with error | Keep payloads small; use references to external storage for large data |

General rule: mq9 operations are best-effort at the application layer. For critical messages, use `INBOX.urgent` + `MAILBOX.QUERY` on reconnect as a two-layer safety net.

## Deployment

### Development

```bash
docker run -d -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

Mount `-v mq9-data:/data` to persist mailboxes and messages across container restarts. Without it, all data is lost on restart.

### Production — single node

Single binary, no external dependencies. A single node handles millions of concurrent Agent connections. Suitable for most production workloads.

```bash
docker run -d \
  --name mq9 \
  -p 4222:4222 \
  -p 9090:9090 \
  -v /data/mq9:/data \
  --restart unless-stopped \
  robustmq/robustmq:latest
```

- Port `4222` — NATS protocol (Agent connections)
- Port `9090` — Prometheus metrics endpoint

### Cluster mode

Scale horizontally when a single node is not enough. Agents use the same protocol — no client code changes required.

### Observability

```bash
# Prometheus metrics
curl http://localhost:9090/metrics

# Watch all mq9 traffic (development / debugging)
nats sub '$mq9.AI.#'
```

## Pattern reference

| Scenario | Subject | Pattern | Example |
| - | - | - | - |
| Point-to-point | `INBOX.{mail_id}.{priority}` | Send to known `mail_id` | [↑](#pattern-child-result) |
| Status tracking | `INBOX.{status-id}.normal` | `latest`-type mailbox | [↑](#pattern-orchestrator) |
| Competing workers | `BROADCAST.*` | Queue group subscription | [↑](#pattern-competing) |
| Offline delivery | `INBOX.*` + `MAILBOX.QUERY` | Store-first, push-on-reconnect | [↑](#pattern-edge) |
| Human-in-the-loop | `INBOX.{mail_id}.urgent` | Same protocol as Agent | [↑](#pattern-human) |
| Capability discovery | `BROADCAST.system.capability` | Publisher-subscriber index | [↑](#pattern-capability) |
| Broadcast to all | `BROADCAST.{domain}.{event}` | Wildcard subscribers | — |
| Request-reply | `INBOX` + `reply_to` | `correlation_id` links the pair | — |

*See [What](/what) for design rationale. See [For Agent](/for-agent) for the Agent perspective.*
