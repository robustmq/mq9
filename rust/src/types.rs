use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, AtomicU64};
use std::sync::Arc;
use tokio::task::JoinHandle;

/// Message priority level.
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Priority {
    #[default]
    Normal,
    Urgent,
    Critical,
}

impl Priority {
    /// Return the wire string for the `mq9-priority` header.
    pub(crate) fn as_str(&self) -> &'static str {
        match self {
            Priority::Normal => "normal",
            Priority::Urgent => "urgent",
            Priority::Critical => "critical",
        }
    }
}

/// A message returned by [`crate::Mq9Client::fetch`] or [`crate::Mq9Client::query`].
#[derive(Debug, Clone)]
pub struct Message {
    pub msg_id: i64,
    pub payload: Vec<u8>,
    pub priority: Priority,
    pub create_time: i64,
}

/// Options for [`crate::Mq9Client::send`].
#[derive(Debug, Default)]
pub struct SendOptions {
    pub priority: Priority,
    pub key: Option<String>,
    /// Delay delivery by this many seconds.
    pub delay: Option<u64>,
    /// Message TTL in seconds.
    pub ttl: Option<u64>,
    pub tags: Option<Vec<String>>,
}

/// Options for a one-shot [`crate::Mq9Client::fetch`] call.
#[derive(Debug, Default)]
pub struct FetchOptions {
    pub group_name: Option<String>,
    /// `"latest"` | `"earliest"` | `"from_time"` | `"from_id"`.
    pub deliver: Option<String>,
    pub from_time: Option<u64>,
    pub from_id: Option<u64>,
    pub force_deliver: bool,
    pub num_msgs: Option<u32>,
    pub max_wait_ms: Option<u64>,
}

/// Options for a long-running [`crate::Mq9Client::consume`] loop.
#[derive(Debug, Default)]
pub struct ConsumeOptions {
    pub group_name: Option<String>,
    /// `"latest"` | `"earliest"` | `"from_time"` | `"from_id"`.
    pub deliver: Option<String>,
    pub num_msgs: Option<u32>,
    pub max_wait_ms: Option<u64>,
    /// When `true` the loop automatically ACKs messages after a successful handler call.
    /// Defaults to `false` — callers must opt-in explicitly.
    pub auto_ack: bool,
}

/// Handle to a background consume loop created by [`crate::Mq9Client::consume`].
pub struct Consumer {
    pub(crate) stop_tx: Option<tokio::sync::oneshot::Sender<()>>,
    pub(crate) task: Option<JoinHandle<()>>,
    pub(crate) running: Arc<AtomicBool>,
    pub(crate) count: Arc<AtomicU64>,
}

impl std::fmt::Debug for Consumer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Consumer")
            .field("is_running", &self.is_running())
            .field("processed_count", &self.processed_count())
            .finish()
    }
}

impl Consumer {
    /// Returns `true` while the background loop is still active.
    pub fn is_running(&self) -> bool {
        self.running.load(std::sync::atomic::Ordering::SeqCst)
    }

    /// Total number of messages for which the handler returned `Ok`.
    pub fn processed_count(&self) -> u64 {
        self.count.load(std::sync::atomic::Ordering::SeqCst)
    }

    /// Signal the loop to stop and wait for it to finish.
    pub async fn stop(mut self) {
        if let Some(tx) = self.stop_tx.take() {
            let _ = tx.send(());
        }
        if let Some(task) = self.task.take() {
            let _ = task.await;
        }
    }
}
