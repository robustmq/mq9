# mq9

**The mailbox for AI Agents.**

mq9 is an async messaging broker built specifically for Agent-to-Agent communication. It is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq), alongside MQTT, Kafka, NATS, and AMQP.

---

## What problem does it solve?

In multi-Agent systems, Agents are not servers — they start, execute, and die. They come online and offline at any time. When Agent A sends a message to Agent B and B is offline, the message is gone.

Every team works around this with their own temporary solution — Redis pub/sub (no persistence), Kafka (requires stream management for throwaway Agents), or a homegrown queue. None of these is designed for ephemeral Agents.

**mq9 solves it directly: send a message, the recipient gets it when they come online.** Just like email.

---

## How it works

Every Agent gets a **mailbox** — a persistent, TTL-scoped address. The sender sends to a `mail_address`. The recipient calls FETCH when ready. Neither side needs to be online at the same time.

**Pull consumption + ACK**: clients actively FETCH messages, then ACK to advance the offset. On reconnect, FETCH resumes from the last ACK — no duplicate delivery, no lost messages.

**Three-tier priority**: `critical` → `urgent` → `normal`. Higher-priority messages are returned first by FETCH. FIFO within each level.

**Message attributes**: key dedup (`mq9-key`), tag filtering (`mq9-tags`), delayed delivery (`mq9-delay`), per-message TTL (`mq9-ttl`).

**Agent registry**: built-in registry with full-text and semantic vector search. Agents register their capabilities; other Agents discover them by intent.

**TTL lifecycle**: mailboxes auto-destroy on expiry with all their messages. No manual cleanup.

---

## Try it now — public demo server

```bash
export NATS_URL=nats://demo.robustmq.com:4222

# Create a mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"quickstart.demo","ttl":300}'

# Send a message with critical priority
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# Fetch messages (returned in priority order)
nats request '$mq9.AI.MSG.FETCH.quickstart.demo' '{
  "group_name": "my-worker", "deliver": "earliest", "config": {"num_msgs": 10}
}'

# ACK to advance offset
nats request '$mq9.AI.MSG.ACK.quickstart.demo' '{
  "group_name": "my-worker", "mail_address": "quickstart.demo", "msg_id": 1
}'
```

---

## SDKs

This repo contains official SDKs for all major languages:

| Language   | Install                             | Directory     |
| ---------- | ----------------------------------- | ------------- |
| Python     | `pip install mq9`                   | `python/`     |
| JavaScript | `npm install mq9`                   | `javascript/` |
| Go         | `go get github.com/robustmq/mq9/go` | `go/`         |
| Rust       | `cargo add mq9`                     | `rust/`       |
| Java       | `io.mq9:mq9:0.1.0`                 | `java/`       |

### Python

```python
from mq9 import Mq9Client, Priority

async with Mq9Client("nats://localhost:4222") as client:
    address = await client.mailbox_create(name="agent.inbox", ttl=3600)

    # Send with priority
    await client.send(address, b'{"task":"analyze"}', priority=Priority.URGENT)

    # Continuous consume loop
    consumer = await client.consume(
        address,
        handler=async_handler,
        group_name="workers",
        auto_ack=True,
    )
    await consumer.stop()
```

### JavaScript / TypeScript

```typescript
import { Mq9Client, Priority } from "mq9";

const client = new Mq9Client("nats://localhost:4222");
await client.connect();

const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
await client.send(address, { task: "analyze" }, { priority: Priority.URGENT });

const consumer = await client.consume(address, async (msg) => {
  console.log(JSON.parse(new TextDecoder().decode(msg.payload)));
}, { groupName: "workers", autoAck: true });

await consumer.stop();
await client.close();
```

### Go

```go
client, _ := mq9.Connect("nats://localhost:4222")
defer client.Close()

address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
})

consumer, _ := client.Consume(ctx, address, func(msg mq9.Message) error {
    fmt.Println(string(msg.Payload))
    return nil
}, mq9.ConsumeOptions{GroupName: "workers", AutoAck: true})
defer consumer.Stop()
```

### Rust

```rust
let client = Mq9Client::connect("nats://localhost:4222").await?;
let address = client.mailbox_create(Some("agent.inbox"), 3600).await?;
client.send(&address, b"hello", SendOptions::default()).await?;

let consumer = client.consume(&address, |msg| async move {
    println!("{:?}", msg.payload);
    Ok(())
}, ConsumeOptions { group_name: Some("workers".into()), auto_ack: true, ..Default::default() }).await?;
consumer.stop().await;
```

### Java

```java
Mq9Client client = Mq9Client.connect("nats://localhost:4222").get();

String address = client.mailboxCreate("agent.inbox", 3600).get();
client.send(address, "hello".getBytes(),
    SendOptions.builder().priority(Priority.URGENT).build()).get();

Consumer consumer = client.consume(address, msg -> {
    System.out.println(new String(msg.payload));
    return CompletableFuture.completedFuture(null);
}, ConsumeOptions.builder().groupName("workers").autoAck(true).build()).get();
consumer.stop().get();
client.close();
```

---

## Key scenarios

- **Sub-Agent result delivery** — parent creates a private reply mailbox; sub-agent deposits result; parent FETCHes asynchronously
- **Multi-worker task queue** — shared `group_name` ensures each task is processed by exactly one worker
- **Cloud-to-edge** — commands stored while edge is offline; FETCHed in priority order on reconnect
- **Human-in-the-loop** — humans interact via the same protocol as any Agent; no webhooks needed
- **Async request-reply** — A sends to B with `reply_to`; B replies when ready; A FETCHes when convenient
- **Capability discovery** — Agents register capabilities; others find them by semantic search

---

## Protocol

mq9 exposes 10 commands over NATS request/reply under `$mq9.AI.*`:

| Command            | Subject                                    |
| ------------------ | ------------------------------------------ |
| Create mailbox     | `$mq9.AI.MAILBOX.CREATE`                   |
| Send message       | `$mq9.AI.MSG.SEND.{mail_address}`          |
| Fetch messages     | `$mq9.AI.MSG.FETCH.{mail_address}`         |
| ACK                | `$mq9.AI.MSG.ACK.{mail_address}`           |
| Query (inspect)    | `$mq9.AI.MSG.QUERY.{mail_address}`         |
| Delete message     | `$mq9.AI.MSG.DELETE.{mail_address}.{id}`   |
| Register Agent     | `$mq9.AI.AGENT.REGISTER`                   |
| Unregister Agent   | `$mq9.AI.AGENT.UNREGISTER`                 |
| Report status      | `$mq9.AI.AGENT.REPORT`                     |
| Discover Agents    | `$mq9.AI.AGENT.DISCOVER`                   |

Any NATS client works — no SDK required. Full protocol spec: [protocol.md](./protocol.md).

---

## Repository structure

```text
mq9/
  python/       — Python SDK (pip install mq9)
  javascript/   — TypeScript/JavaScript SDK (npm install mq9)
  java/         — Java SDK (io.mq9:mq9)
  go/           — Go SDK (github.com/robustmq/mq9/go)
  rust/         — Rust SDK (cargo add mq9)
  website/      — Documentation site (mq9.robustmq.com)
  VERSION       — Single source of truth for all SDK versions
```

---

## Documentation

Full documentation at [mq9.robustmq.com](https://mq9.robustmq.com).

- [What is mq9](https://mq9.robustmq.com/what) — concepts, positioning, design principles
- [For Agent](https://mq9.robustmq.com/for-agent) — protocol manual for AI Agents
- [For Engineer](https://mq9.robustmq.com/for-engineer) — integration guide, patterns, deployment

---

## Status

mq9 is under active development as part of [RobustMQ](https://github.com/robustmq/robustmq).
