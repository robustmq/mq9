# mq9

The mailbox for AI Agents.

mq9 is an async messaging broker built specifically for Agent-to-Agent communication. Every Agent gets a mailbox. Send to any Agent — online or offline. Messages are stored and delivered when ready.

The broker implementation lives in [RobustMQ](https://github.com/robustmq/robustmq). This repo contains the multi-language SDKs and the documentation website.

---

## SDKs

- **Python** — `pip install mq9`
- **JavaScript** — `npm install mq9`
- **Go** — `go get github.com/robustmq/mq9/go`
- **Rust** — `cargo add mq9`
- **Java** — `io.mq9:mq9:0.1.0` (Maven Central)

---

## Quick start

### Python

```python
from mq9 import Mq9Client, Priority

async with Mq9Client("nats://localhost:4222") as client:
    address = await client.mailbox_create(name="agent.inbox", ttl=3600)
    await client.send(address, {"task": "analyze"}, priority=Priority.NORMAL)

    async def handler(msg):
        print(msg.payload)

    consumer = await client.consume(address, handler, group_name="workers")
    await consumer.stop()
```

### JavaScript

```typescript
import { Mq9Client, Priority } from "mq9";

const client = new Mq9Client("nats://localhost:4222");
await client.connect();

const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
await client.send(address, { task: "analyze" }, { priority: Priority.NORMAL });

const consumer = await client.consume(address, async (msg) => {
  console.log(msg.payload);
}, { groupName: "workers" });

await consumer.stop();
await client.close();
```

### Go

```go
client, _ := mq9.Connect("nats://localhost:4222")
defer client.Close()

address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{})

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
}, ConsumeOptions { auto_ack: true, ..Default::default() }).await?;
consumer.stop().await;
```

### Java

```java
Mq9Client client = Mq9Client.connect("nats://localhost:4222").get();

String address = client.mailboxCreate("agent.inbox", 3600).get();
client.send(address, "hello".getBytes(), SendOptions.builder().build()).get();

Consumer consumer = client.consume(address, msg -> {
    System.out.println(new String(msg.payload));
    return CompletableFuture.completedFuture(null);
}, ConsumeOptions.builder().groupName("workers").build()).get();
consumer.stop().get();
client.close();
```

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

## Protocol

mq9 exposes 10 commands over NATS request/reply under `$mq9.AI.*`. The full protocol spec is in the [RobustMQ repository](https://github.com/robustmq/robustmq/blob/main/docs/en/mq9/Protocol.md).

---

## Status

mq9 is under active development as part of [RobustMQ](https://github.com/robustmq/robustmq) — the fifth native protocol alongside MQTT, Kafka, NATS, and AMQP.
