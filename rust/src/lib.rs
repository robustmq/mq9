//! # mq9
//!
//! Rust client SDK for the mq9 NATS-based Agent messaging broker.
//!
//! mq9 is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq),
//! designed for Agent-to-Agent async communication.  Every Agent gets a mailbox;
//! sender and receiver do not need to be online at the same time.
//!
//! ## Quick start
//!
//! ```rust,no_run
//! use mq9::{Mq9Client, SendOptions, FetchOptions, Priority};
//!
//! #[tokio::main]
//! async fn main() -> mq9::Result<()> {
//!     let client = Mq9Client::connect("nats://localhost:4222").await?;
//!
//!     // Create a mailbox (never expires).
//!     let addr = client.mailbox_create(Some("my.inbox"), 0).await?;
//!
//!     // Send a message.
//!     let msg_id = client.send(
//!         &addr,
//!         b"hello world".to_vec(),
//!         SendOptions { priority: Priority::Urgent, ..Default::default() },
//!     ).await?;
//!
//!     // Fetch messages.
//!     let msgs = client.fetch(&addr, FetchOptions::default()).await?;
//!     for msg in msgs {
//!         println!("msg_id={} payload={:?}", msg.msg_id, msg.payload);
//!     }
//!
//!     client.close().await
//! }
//! ```

mod client;
mod error;
mod types;

pub use client::{ClientOptions, Mq9Client};
pub use error::{Mq9Error, Result};
pub use types::{Consumer, ConsumeOptions, FetchOptions, Message, Priority, SendOptions};
