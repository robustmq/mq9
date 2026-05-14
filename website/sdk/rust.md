---
title: Rust SDK — mq9
description: mq9 Rust SDK API reference and usage guide.
---

# Rust SDK

## Install

```toml
[dependencies]
mq9 = "0.1"
tokio = { version = "1", features = ["full"] }
```

Or:

```bash
cargo add mq9
```

## Quick start

```rust
use mq9::{Mq9Client, Priority, SendOptions, ConsumeOptions};

#[tokio::main]
async fn main() -> mq9::Result<()> {
    let client = Mq9Client::connect("nats://localhost:4222").await?;

    // Create a mailbox
    let address = client.mailbox_create(Some("agent.inbox"), 3600).await?;

    // Send a message
    let msg_id = client.send(&address, b"hello world", SendOptions::default()).await?;
    println!("sent: {}", msg_id);

    // Consume messages
    let consumer = client.consume(
        &address,
        |msg| async move {
            println!("received: {:?}", msg.payload);
            Ok(())
        },
        ConsumeOptions { auto_ack: true, ..Default::default() },
    ).await?;

    tokio::time::sleep(std::time::Duration::from_secs(10)).await;
    consumer.stop().await;
    Ok(())
}
```

## Mq9Client

```rust
Mq9Client::connect(server: &str) -> Result<Self>
Mq9Client::connect_with_options(server: &str, options: ClientOptions) -> Result<Self>
```

```rust
pub struct ClientOptions {
    pub request_timeout: Duration,   // default 5s
    pub reconnect_delay: Duration,   // default 2s
}
```

### close

```rust
client.close(self) -> Result<()>
```

---

## Mailbox

### mailbox_create

```rust
client.mailbox_create(name: Option<&str>, ttl: u64) -> Result<String>
```

- `name = None` — broker auto-generates the address.
- `ttl = 0` — never expires.

```rust
let address = client.mailbox_create(Some("agent.inbox"), 3600).await?;
let address = client.mailbox_create(None, 7200).await?; // auto-generated
```

---

## Messaging

### send

```rust
client.send(
    mail_address: &str,
    payload: impl Into<Vec<u8>>,
    options: SendOptions,
) -> Result<i64>   // msg_id; -1 for delayed messages
```

```rust
pub struct SendOptions {
    pub priority: Priority,           // default Priority::Normal
    pub key: Option<String>,          // dedup key
    pub delay: Option<u64>,           // seconds
    pub ttl: Option<u64>,             // message-level TTL in seconds
    pub tags: Option<Vec<String>>,
}
```

```rust
// Normal send
let msg_id = client.send("agent.inbox", b"hello", SendOptions::default()).await?;

// Urgent priority
let msg_id = client.send("agent.inbox", b"alert", SendOptions {
    priority: Priority::Urgent,
    ..Default::default()
}).await?;

// Dedup key
let msg_id = client.send("task.status", b"running", SendOptions {
    key: Some("state".into()),
    ..Default::default()
}).await?;

// Delayed delivery
let msg_id = client.send("agent.inbox", b"hello", SendOptions {
    delay: Some(60),
    ..Default::default()
}).await?;
```

### fetch

```rust
client.fetch(mail_address: &str, options: FetchOptions) -> Result<Vec<Message>>
```

```rust
pub struct FetchOptions {
    pub group_name: Option<String>,
    pub deliver: Option<String>,      // "latest"|"earliest"|"from_time"|"from_id"
    pub from_time: Option<u64>,
    pub from_id: Option<u64>,
    pub force_deliver: bool,
    pub num_msgs: Option<u32>,        // default 100
    pub max_wait_ms: Option<u64>,     // default 500
}
```

```rust
// Stateless
let messages = client.fetch("task.inbox", FetchOptions {
    deliver: Some("earliest".into()),
    ..Default::default()
}).await?;

// Stateful
let messages = client.fetch("task.inbox", FetchOptions {
    group_name: Some("workers".into()),
    ..Default::default()
}).await?;
for msg in &messages {
    client.ack("task.inbox", "workers", msg.msg_id).await?;
}
```

### ack

```rust
client.ack(mail_address: &str, group_name: &str, msg_id: i64) -> Result<()>
```

### consume

```rust
client.consume<F, Fut>(
    mail_address: &str,
    handler: F,
    options: ConsumeOptions,
) -> Result<Consumer>
where
    F: Fn(Message) -> Fut + Send + Sync + 'static,
    Fut: Future<Output = Result<()>> + Send + 'static,
```

```rust
pub struct ConsumeOptions {
    pub group_name: Option<String>,
    pub deliver: Option<String>,
    pub num_msgs: Option<u32>,
    pub max_wait_ms: Option<u64>,
    pub auto_ack: bool,              // default false — set true explicitly
}
```

- Handler returns `Err` → message **not ACKed**, error logged, loop continues.

```rust
let consumer = client.consume(
    "task.inbox",
    |msg| async move {
        println!("{:?}", msg.payload);
        Ok(())
    },
    ConsumeOptions {
        group_name: Some("workers".into()),
        auto_ack: true,
        ..Default::default()
    },
).await?;

tokio::time::sleep(Duration::from_secs(30)).await;
consumer.stop().await;
println!("processed: {}", consumer.processed_count());
```

### query

```rust
client.query(
    mail_address: &str,
    key: Option<&str>,
    limit: Option<u64>,
    since: Option<u64>,
) -> Result<Vec<Message>>
```

### delete

```rust
client.delete(mail_address: &str, msg_id: i64) -> Result<()>
```

---

## Agent management

### agent_register

```rust
client.agent_register(agent_card: serde_json::Value) -> Result<()>
// agent_card must contain "mailbox" field
```

### agent_unregister

```rust
client.agent_unregister(mailbox: &str) -> Result<()>
```

### agent_report

```rust
client.agent_report(report: serde_json::Value) -> Result<()>
```

### agent_discover

```rust
client.agent_discover(
    text: Option<&str>,
    semantic: Option<&str>,
    limit: Option<u32>,
    page: Option<u32>,
) -> Result<Vec<serde_json::Value>>
```

---

## Data types

### Priority

```rust
#[derive(Debug, Clone, PartialEq)]
pub enum Priority {
    Normal,
    Urgent,
    Critical,
}
```

### Message

```rust
pub struct Message {
    pub msg_id: i64,
    pub payload: Vec<u8>,
    pub priority: Priority,
    pub create_time: i64,   // unix timestamp (seconds)
}
```

### Consumer

```rust
impl Consumer {
    pub fn is_running(&self) -> bool;
    pub fn processed_count(&self) -> u64;
    pub async fn stop(self);
}
```

### Mq9Error

```rust
use mq9::Mq9Error;

#[derive(Debug, thiserror::Error)]
pub enum Mq9Error {
    #[error("server error: {0}")]
    Server(String),
    #[error("nats error: {0}")]
    Nats(Box<dyn std::error::Error + Send + Sync>),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("not connected")]
    NotConnected,
}

pub type Result<T> = std::result::Result<T, Mq9Error>;
```
