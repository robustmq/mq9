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
- **Public channels** — create a named public mailbox. Any Agent can discover it via PUBLIC.LIST and subscribe.
- **Priority** — high-priority messages processed first.
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
        json.dumps({"ttl": 3600}).encode())
    agent_a = json.loads(resp.data)
    print(f"Agent A mailbox: {agent_a['mail_id']}")

    # Agent B creates a mailbox
    resp = await nc.request("$mq9.AI.MAILBOX.CREATE",
        json.dumps({"ttl": 3600}).encode())
    agent_b = json.loads(resp.data)
    print(f"Agent B mailbox: {agent_b['mail_id']}")

    received = asyncio.Event()

    # Agent B subscribes to its mailbox
    async def on_message(msg):
        data = json.loads(msg.data)
        print(f"Agent B received: {data['payload']}")
        # Reply to Agent A
        if data.get("reply_to"):
            await nc.publish(
                f"$mq9.AI.MAILBOX.{data['reply_to']}.normal",
                json.dumps({
                    "msg_id": "reply-001",
                    "from": agent_b["mail_id"],
                    "type": "result",
                    "correlation_id": data["correlation_id"],
                    "payload": "task complete"
                }).encode())
        received.set()

    await nc.subscribe(f"$mq9.AI.MAILBOX.{agent_b['mail_id']}.*", cb=on_message)

    # Agent A sends a task to Agent B
    await nc.publish(
        f"$mq9.AI.MAILBOX.{agent_b['mail_id']}.normal",
        json.dumps({
            "msg_id": "task-001",
            "from": agent_a["mail_id"],
            "type": "task",
            "correlation_id": "demo-001",
            "reply_to": agent_a["mail_id"],
            "payload": "analyze this"
        }).encode())
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
import nats

async def main():
    nc = await nats.connect("nats://localhost:4222")
    resp = await nc.request(
        "$mq9.AI.MAILBOX.CREATE",
        json.dumps({"ttl": 3600}).encode()
    )
    mailbox = json.loads(resp.data)
    mail_id = mailbox["mail_id"]
```

```go
// Go
nc, _ := nats.Connect(nats.DefaultURL)
resp, _ := nc.Request("$mq9.AI.MAILBOX.CREATE",
    []byte(`{"ttl":3600}`), 2*time.Second)

var m struct {
    MailID string `json:"mail_id"`
}
json.Unmarshal(resp.Data, &m)
```

```javascript
// JavaScript
const nc = await connect({ servers: "nats://localhost:4222" });
const jc = JSONCodec();
const resp = await nc.request(
  "$mq9.AI.MAILBOX.CREATE",
  jc.encode({ ttl: 3600 })
);
const { mail_id } = jc.decode(resp.data);
```

### Send a message

```python
await nc.publish(
    f"$mq9.AI.MAILBOX.{target_mail_id}.normal",
    json.dumps({
        "msg_id": "msg-001",
        "from": mail_id,
        "type": "task",
        "correlation_id": "req-001",
        "reply_to": mail_id,
        "payload": { "data": "..." }
    }).encode()
)
```

### Subscribe and receive

Subscribe delivers all unexpired messages immediately, then streams new arrivals. No separate pull needed.

```python
async def on_message(msg):
    data = json.loads(msg.data)
    # Deduplicate using msg_id if needed
    if data["msg_id"] in seen:
        return
    seen.add(data["msg_id"])

    print(f"From {data['from']}: {data['payload']}")

    if data.get("reply_to"):
        await nc.publish(
            f"$mq9.AI.MAILBOX.{data['reply_to']}.normal",
            json.dumps({
                "msg_id": new_uuid(),
                "from": mail_id,
                "type": "result",
                "correlation_id": data["correlation_id"],
                "payload": { "status": "done" }
            }).encode())

await nc.subscribe(f"$mq9.AI.MAILBOX.{mail_id}.*", cb=on_message)
```

### Discover public mailboxes

```python
async def on_list(msg):
    event = json.loads(msg.data)
    if event["event"] == "created":
        registry[event["mail_id"]] = event["desc"]
    elif event["event"] == "expired":
        registry.pop(event["mail_id"], None)

await nc.subscribe("$mq9.AI.PUBLIC.LIST", cb=on_list)
```

## Common patterns

### Child Agent reports result to parent {#pattern-child-result}

```python
# Parent sends task with reply_to
await nc.publish(f"$mq9.AI.MAILBOX.{worker_id}.normal", json.dumps({
    "msg_id": new_uuid(),
    "from": parent_id,
    "type": "work",
    "correlation_id": "job-001",
    "reply_to": parent_id,
    "payload": { "data": [] }
}).encode())

# Parent collects results — non-blocking
results = {}
async def collect(msg):
    d = json.loads(msg.data)
    results[d["correlation_id"]] = d["payload"]

await nc.subscribe(f"$mq9.AI.MAILBOX.{parent_id}.*", cb=collect)
```

### Task broadcast with competing workers {#pattern-competing}

```python
# Create a public task queue (once, idempotent)
await nc.request("$mq9.AI.MAILBOX.CREATE",
    json.dumps({"ttl": 86400, "public": True, "name": "task.queue"}).encode())

# Orchestrator publishes tasks
await nc.publish("$mq9.AI.MAILBOX.task.queue.normal",
    json.dumps({"msg_id": new_uuid(), "task_id": "t-001", "data": {}}).encode())

# Workers subscribe with shared queue group — each task goes to exactly one worker
async def handle_task(msg):
    task = json.loads(msg.data)
    result = await process(task)
    await nc.publish(f"$mq9.AI.MAILBOX.{master_id}.normal",
        json.dumps({"from": worker_id, "task_id": task["task_id"], "result": result}).encode())

await nc.subscribe("$mq9.AI.MAILBOX.task.queue.*",
    queue="task-workers", cb=handle_task)
```

### Cloud to offline edge device {#pattern-edge}

```go
// Cloud: send commands — edge may be offline for hours
nc.Publish(fmt.Sprintf("$mq9.AI.MAILBOX.%s.high", edgeID),
    []byte(`{"msg_id":"cmd-001","command":"emergency_stop","reason":"temperature_critical"}`))

nc.Publish(fmt.Sprintf("$mq9.AI.MAILBOX.%s.normal", edgeID),
    []byte(`{"msg_id":"cmd-002","command":"update_config","interval":30}`))

// Edge: on reconnect, subscribe — high priority messages arrive first
nc.Subscribe(fmt.Sprintf("$mq9.AI.MAILBOX.%s.*", edgeID), func(msg *nats.Msg) {
    // Process — high arrives before normal regardless of subscription order
    var cmd map[string]interface{}
    json.Unmarshal(msg.Data, &cmd)
    dispatch(cmd)
})
```

### Human-in-the-loop approval {#pattern-human}

```javascript
// Agent sends approval request to human's mailbox
await nc.publish(`$mq9.AI.MAILBOX.${humanMailID}.high`, jc.encode({
  msg_id: newUUID(),
  from: agentMailID,
  type: "approval_request",
  correlation_id: "approval-001",
  content: "Call external fraud API — estimated cost $50",
  reply_to: agentMailID
}));

// Human's client — same protocol, standard NATS client
for await (const msg of nc.subscribe(`$mq9.AI.MAILBOX.${humanMailID}.*`)) {
  const req = jc.decode(msg.data);
  const approved = await showApprovalUI(req);
  await nc.publish(`$mq9.AI.MAILBOX.${req.reply_to}.normal`, jc.encode({
    msg_id: newUUID(),
    from: humanMailID,
    type: "approval_response",
    correlation_id: req.correlation_id,
    approved
  }));
}
```

### Capability registration and discovery {#pattern-capability}

```go
// Agent creates a public mailbox on startup to announce capabilities
nc.Request("$mq9.AI.MAILBOX.CREATE",
    []byte(fmt.Sprintf(`{
        "ttl": 3600,
        "public": true,
        "name": "agent.%s",
        "desc": "data analysis, anomaly detection"
    }`, agentID)), 2*time.Second)

// Orchestrator subscribes to PUBLIC.LIST — receives all registrations
index := map[string]string{}
nc.Subscribe("$mq9.AI.PUBLIC.LIST", func(msg *nats.Msg) {
    var event map[string]string
    json.Unmarshal(msg.Data, &event)
    if event["event"] == "created" {
        index[event["mail_id"]] = event["desc"]
    } else if event["event"] == "expired" {
        delete(index, event["mail_id"])
    }
})

// Dispatch to a capable Agent by publishing to its public mail_id
nc.Publish(fmt.Sprintf("$mq9.AI.MAILBOX.agent.%s.normal", targetID), task)
```

### Async request-reply {#pattern-request-reply}

```python
# Agent A asks Agent B a question — B may be offline
correlation = new_uuid()

await nc.publish(f"$mq9.AI.MAILBOX.{agent_b_id}.normal", json.dumps({
    "msg_id": new_uuid(),
    "from": agent_a_id,
    "type": "question",
    "correlation_id": correlation,
    "reply_to": agent_a_id,
    "payload": { "question": "..." }
}).encode())

# Agent A continues other work — no blocking
# When Agent B comes online, it processes the question and replies to agent_a_id
# Agent A's subscription handler picks up the reply by correlation_id
```

## Error handling

| Situation | What happens | What to do |
| - | - | - |
| `MAILBOX.CREATE` fails | Returns error response | Retry with backoff; check server connectivity |
| Send to expired `mail_id` | Message dropped silently | Set TTL longer than your worst-case offline window |
| `MAILBOX.CREATE` called twice with same public name | Silently succeeds — TTL stays from first creation | This is intentional — CREATE is idempotent |
| TTL expires before Agent reconnects | Mailbox and all messages deleted | Set TTL to cover worst-case offline duration |
| Message exceeds size limit | Rejected with error | Keep payloads small; use references to external storage for large data |
| Duplicate message delivery | Possible on reconnect | Use `msg_id` for client-side deduplication |

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
| Point-to-point | `MAILBOX.{mail_id}.{priority}` | Send to known `mail_id` | [↑](#pattern-child-result) |
| Competing workers | `MAILBOX.task.queue.*` | Public mailbox + queue group | [↑](#pattern-competing) |
| Offline delivery | `MAILBOX.{mail_id}.*` | Store-first, push on subscribe | [↑](#pattern-edge) |
| Human-in-the-loop | `MAILBOX.{mail_id}.high` | Same protocol as Agent | [↑](#pattern-human) |
| Capability discovery | `PUBLIC.LIST` | Public mailbox auto-registration | [↑](#pattern-capability) |
| Request-reply | `MAILBOX` + `reply_to` | `correlation_id` links the pair | [↑](#pattern-request-reply) |

*See [What](/what) for design rationale. See [For Agent](/for-agent) for the Agent perspective.*
