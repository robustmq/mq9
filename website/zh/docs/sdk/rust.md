---
title: Rust SDK — mq9
description: mq9 Rust SDK API 参考与使用指南。
---

# Rust SDK

## 安装

```toml
[dependencies]
mq9 = "0.1"
tokio = { version = "1", features = ["full"] }
```

或：

```bash
cargo add mq9
```

## 快速开始

```rust
use mq9::{Mq9Client, Priority, SendOptions, ConsumeOptions};

#[tokio::main]
async fn main() -> mq9::Result<()> {
    let client = Mq9Client::connect("nats://localhost:4222").await?;

    // 创建邮箱
    let address = client.mailbox_create(Some("agent.inbox"), 3600).await?;

    // 发送消息
    let msg_id = client.send(&address, b"hello world", SendOptions::default()).await?;
    println!("sent: {}", msg_id);

    // 消费消息
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
    pub request_timeout: Duration,   // 默认 5s
    pub reconnect_delay: Duration,   // 默认 2s
}
```

### close

```rust
client.close(self) -> Result<()>
```

---

## 邮箱

### mailbox_create

```rust
client.mailbox_create(name: Option<&str>, ttl: u64) -> Result<String>
```

- `name = None` — broker 自动生成地址。
- `ttl = 0` — 永不过期。

```rust
let address = client.mailbox_create(Some("agent.inbox"), 3600).await?;
let address = client.mailbox_create(None, 7200).await?; // 自动生成
```

---

## 消息收发

### send

```rust
client.send(
    mail_address: &str,
    payload: impl Into<Vec<u8>>,
    options: SendOptions,
) -> Result<i64>   // msg_id；延迟消息返回 -1
```

```rust
pub struct SendOptions {
    pub priority: Priority,           // 默认 Priority::Normal
    pub key: Option<String>,          // 去重键
    pub delay: Option<u64>,           // 秒
    pub ttl: Option<u64>,             // 消息级别 TTL（秒）
    pub tags: Option<Vec<String>>,
}
```

```rust
// 普通发送
let msg_id = client.send("agent.inbox", b"hello", SendOptions::default()).await?;

// 紧急优先级
let msg_id = client.send("agent.inbox", b"alert", SendOptions {
    priority: Priority::Urgent,
    ..Default::default()
}).await?;

// 去重键
let msg_id = client.send("task.status", b"running", SendOptions {
    key: Some("state".into()),
    ..Default::default()
}).await?;

// 延迟投递
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
    pub num_msgs: Option<u32>,        // 默认 100
    pub max_wait_ms: Option<u64>,     // 默认 500
}
```

```rust
// 无状态
let messages = client.fetch("task.inbox", FetchOptions {
    deliver: Some("earliest".into()),
    ..Default::default()
}).await?;

// 有状态
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
    pub auto_ack: bool,              // 默认 false — 需显式设置为 true
}
```

- handler 返回 `Err` → 消息**不会被 ACK**，记录错误日志，循环继续。

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

## Agent 管理

### agent_register

```rust
client.agent_register(agent_card: serde_json::Value) -> Result<()>
// agent_card 必须包含 "mailbox" 字段
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

## 数据类型

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
    pub create_time: i64,   // Unix 时间戳（秒）
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
