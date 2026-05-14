use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use async_nats::HeaderMap;
use base64::Engine as _;
use serde_json::{json, Value};
use tokio::sync::oneshot;

use crate::error::{Mq9Error, Result};
use crate::types::{Consumer, ConsumeOptions, FetchOptions, Message, Priority, SendOptions};

// ---------------------------------------------------------------------------
// Subject builders
// ---------------------------------------------------------------------------

const PREFIX: &str = "$mq9.AI";

fn subj_mailbox_create() -> String {
    format!("{PREFIX}.MAILBOX.CREATE")
}
fn subj_msg_send(mail_address: &str) -> String {
    format!("{PREFIX}.MSG.SEND.{mail_address}")
}
fn subj_msg_fetch(mail_address: &str) -> String {
    format!("{PREFIX}.MSG.FETCH.{mail_address}")
}
fn subj_msg_ack(mail_address: &str) -> String {
    format!("{PREFIX}.MSG.ACK.{mail_address}")
}
fn subj_msg_query(mail_address: &str) -> String {
    format!("{PREFIX}.MSG.QUERY.{mail_address}")
}
fn subj_msg_delete(mail_address: &str, msg_id: i64) -> String {
    format!("{PREFIX}.MSG.DELETE.{mail_address}.{msg_id}")
}
fn subj_agent_register() -> String {
    format!("{PREFIX}.AGENT.REGISTER")
}
fn subj_agent_unregister() -> String {
    format!("{PREFIX}.AGENT.UNREGISTER")
}
fn subj_agent_report() -> String {
    format!("{PREFIX}.AGENT.REPORT")
}
fn subj_agent_discover() -> String {
    format!("{PREFIX}.AGENT.DISCOVER")
}

// ---------------------------------------------------------------------------
// ClientOptions
// ---------------------------------------------------------------------------

/// Configuration passed to [`Mq9Client::connect_with_options`].
pub struct ClientOptions {
    /// Per-request timeout. Defaults to 5 seconds.
    pub request_timeout: Duration,
    /// Sleep duration between retries inside `consume` when fetch fails.
    pub reconnect_delay: Duration,
}

impl Default for ClientOptions {
    fn default() -> Self {
        Self {
            request_timeout: Duration::from_secs(5),
            reconnect_delay: Duration::from_secs(1),
        }
    }
}

// ---------------------------------------------------------------------------
// Internal helpers: response parsing
// ---------------------------------------------------------------------------

/// Return `Err(Mq9Error::Server)` if the response's `error` field is non-empty.
fn check_error(resp: &Value) -> Result<()> {
    let err_str = resp
        .get("error")
        .and_then(|v| v.as_str())
        .unwrap_or_default();
    if !err_str.is_empty() {
        return Err(Mq9Error::Server(err_str.to_owned()));
    }
    Ok(())
}

/// Decode the `messages` array from a fetch/query response.
fn parse_messages(arr: &Value) -> Result<Vec<Message>> {
    let Some(items) = arr.as_array() else {
        return Ok(vec![]);
    };
    let mut messages = Vec::with_capacity(items.len());
    for item in items {
        let msg_id = item["msg_id"].as_i64().unwrap_or(0);
        let create_time = item["create_time"].as_i64().unwrap_or(0);
        let priority = match item["priority"].as_str().unwrap_or("normal") {
            "urgent" => Priority::Urgent,
            "critical" => Priority::Critical,
            _ => Priority::Normal,
        };
        // Server encodes payload as a base64 string.
        let payload = if let Some(s) = item["payload"].as_str() {
            base64::engine::general_purpose::STANDARD
                .decode(s)
                .unwrap_or_default()
        } else {
            vec![]
        };
        messages.push(Message {
            msg_id,
            payload,
            priority,
            create_time,
        });
    }
    Ok(messages)
}

// ---------------------------------------------------------------------------
// Mq9Client
// ---------------------------------------------------------------------------

/// Async client for the mq9 NATS-based Agent messaging broker.
///
/// Obtain an instance via [`Mq9Client::connect`] or
/// [`Mq9Client::connect_with_options`].
pub struct Mq9Client {
    nc: async_nats::Client,
    options: ClientOptions,
}

impl Mq9Client {
    // ------------------------------------------------------------------
    // Constructors / lifecycle
    // ------------------------------------------------------------------

    /// Connect to a NATS server using default [`ClientOptions`].
    pub async fn connect(server: &str) -> Result<Self> {
        Self::connect_with_options(server, ClientOptions::default()).await
    }

    /// Connect with custom options.
    pub async fn connect_with_options(server: &str, options: ClientOptions) -> Result<Self> {
        let nc = async_nats::connect(server)
            .await
            .map_err(|e| Mq9Error::Nats(Box::new(e)))?;
        Ok(Self { nc, options })
    }

    /// Drain outstanding messages and close the connection.
    pub async fn close(self) -> Result<()> {
        self.nc
            .drain()
            .await
            .map_err(|e| Mq9Error::Nats(Box::new(e)))?;
        Ok(())
    }

    // ------------------------------------------------------------------
    // Internal: NATS request helpers
    // ------------------------------------------------------------------

    /// Plain request (no custom NATS headers). Parses JSON response.
    async fn request(&self, subject: String, payload: Vec<u8>) -> Result<Value> {
        let msg = tokio::time::timeout(
            self.options.request_timeout,
            self.nc.request(subject, payload.into()),
        )
        .await
        .map_err(|_| Mq9Error::Nats(Box::from("request timed out")))?
        .map_err(|e| Mq9Error::Nats(Box::new(e)))?;

        let resp: Value = serde_json::from_slice(&msg.payload)?;
        check_error(&resp)?;
        Ok(resp)
    }

    /// Request with NATS headers. Uses the built-in `request_with_headers`.
    async fn request_with_headers(
        &self,
        subject: String,
        headers: HeaderMap,
        payload: Vec<u8>,
    ) -> Result<Value> {
        let msg = tokio::time::timeout(
            self.options.request_timeout,
            self.nc
                .request_with_headers(subject, headers, payload.into()),
        )
        .await
        .map_err(|_| Mq9Error::Nats(Box::from("request_with_headers timed out")))?
        .map_err(|e| Mq9Error::Nats(Box::new(e)))?;

        let resp: Value = serde_json::from_slice(&msg.payload)?;
        check_error(&resp)?;
        Ok(resp)
    }

    // ------------------------------------------------------------------
    // Mailbox
    // ------------------------------------------------------------------

    /// Create a mailbox and return its `mail_address`.
    ///
    /// - `name` — optional human-readable identifier; broker auto-assigns if `None`.
    /// - `ttl` — seconds until expiry; `0` = never expires.
    pub async fn mailbox_create(&self, name: Option<&str>, ttl: u64) -> Result<String> {
        let mut body = json!({ "ttl": ttl });
        if let Some(n) = name {
            body["name"] = Value::String(n.to_owned());
        }
        let resp = self
            .request(subj_mailbox_create(), serde_json::to_vec(&body)?)
            .await?;
        Ok(resp["mail_address"]
            .as_str()
            .unwrap_or_default()
            .to_owned())
    }

    // ------------------------------------------------------------------
    // Messaging
    // ------------------------------------------------------------------

    /// Send a message and return the broker-assigned `msg_id`.
    ///
    /// Returns `-1` for delayed messages (id assigned at delivery time).
    pub async fn send(
        &self,
        mail_address: &str,
        payload: impl Into<Vec<u8>>,
        options: SendOptions,
    ) -> Result<i64> {
        let subject = subj_msg_send(mail_address);
        let data: Vec<u8> = payload.into();

        let mut headers = HeaderMap::new();
        let mut has_headers = false;

        if options.priority != Priority::Normal {
            headers.insert("mq9-priority", options.priority.as_str());
            has_headers = true;
        }
        if let Some(ref k) = options.key {
            headers.insert("mq9-key", k.as_str());
            has_headers = true;
        }
        if let Some(d) = options.delay {
            headers.insert("mq9-delay", d.to_string().as_str());
            has_headers = true;
        }
        if let Some(t) = options.ttl {
            headers.insert("mq9-ttl", t.to_string().as_str());
            has_headers = true;
        }
        if let Some(ref tags) = options.tags {
            if !tags.is_empty() {
                headers.insert("mq9-tags", tags.join(",").as_str());
                has_headers = true;
            }
        }

        let resp = if has_headers {
            self.request_with_headers(subject, headers, data).await?
        } else {
            self.request(subject, data).await?
        };

        Ok(resp["msg_id"].as_i64().unwrap_or(0))
    }

    /// Fetch a batch of messages from `mail_address`.
    pub async fn fetch(
        &self,
        mail_address: &str,
        options: FetchOptions,
    ) -> Result<Vec<Message>> {
        let subject = subj_msg_fetch(mail_address);

        let mut body = json!({
            "deliver": options.deliver.as_deref().unwrap_or("latest"),
            "force_deliver": options.force_deliver,
            "config": {
                "num_msgs": options.num_msgs.unwrap_or(100),
                "max_wait_ms": options.max_wait_ms.unwrap_or(500),
            },
        });

        if let Some(ref gn) = options.group_name {
            body["group_name"] = Value::String(gn.clone());
        }
        if let Some(ft) = options.from_time {
            body["from_time"] = Value::Number(ft.into());
        }
        if let Some(fi) = options.from_id {
            body["from_id"] = Value::Number(fi.into());
        }

        let resp = self.request(subject, serde_json::to_vec(&body)?).await?;
        let empty = Value::Array(vec![]);
        let arr = resp.get("messages").unwrap_or(&empty);
        parse_messages(arr)
    }

    /// Acknowledge a message, advancing the consumer group's offset.
    pub async fn ack(
        &self,
        mail_address: &str,
        group_name: &str,
        msg_id: i64,
    ) -> Result<()> {
        let subject = subj_msg_ack(mail_address);
        let body = json!({
            "group_name": group_name,
            "mail_address": mail_address,
            "msg_id": msg_id,
        });
        self.request(subject, serde_json::to_vec(&body)?).await?;
        Ok(())
    }

    /// Start a background consume loop and return a [`Consumer`] handle.
    ///
    /// The spawned task loops forever: fetch → call `handler` per message →
    /// optional auto-ACK.  Call [`Consumer::stop`] to shut it down.
    ///
    /// - Handler returning `Err` skips the ACK and logs the error.
    /// - Fetch errors are logged and retried after `reconnect_delay`.
    pub async fn consume<F, Fut>(
        &self,
        mail_address: &str,
        handler: F,
        options: ConsumeOptions,
    ) -> Result<Consumer>
    where
        F: Fn(Message) -> Fut + Send + Sync + 'static,
        Fut: std::future::Future<Output = Result<()>> + Send + 'static,
    {
        let running = Arc::new(AtomicBool::new(true));
        let count = Arc::new(AtomicU64::new(0));

        let running_clone = Arc::clone(&running);
        let count_clone = Arc::clone(&count);

        let (stop_tx, stop_rx) = oneshot::channel::<()>();

        // Clone the NATS client and options into the task.
        let inner_client = Mq9Client {
            nc: self.nc.clone(),
            options: ClientOptions {
                request_timeout: self.options.request_timeout,
                reconnect_delay: self.options.reconnect_delay,
            },
        };
        let mail_address = mail_address.to_owned();
        let reconnect_delay = self.options.reconnect_delay;
        let handler = Arc::new(handler);

        let task = tokio::spawn(async move {
            let mut stop_rx = stop_rx;

            loop {
                // Non-blocking check for stop signal.
                if stop_rx.try_recv().is_ok() {
                    break;
                }

                let fetch_opts = FetchOptions {
                    group_name: options.group_name.clone(),
                    deliver: options.deliver.clone(),
                    num_msgs: options.num_msgs,
                    max_wait_ms: options.max_wait_ms,
                    force_deliver: false,
                    from_time: None,
                    from_id: None,
                };

                let messages = match inner_client.fetch(&mail_address, fetch_opts).await {
                    Ok(msgs) => msgs,
                    Err(e) => {
                        tracing::error!("mq9 fetch error: {e}");
                        tokio::time::sleep(reconnect_delay).await;
                        continue;
                    }
                };

                for msg in messages {
                    // Check for stop between messages.
                    if stop_rx.try_recv().is_ok() {
                        running_clone.store(false, Ordering::SeqCst);
                        return;
                    }

                    let msg_id = msg.msg_id;
                    match handler(msg).await {
                        Ok(()) => {
                            count_clone.fetch_add(1, Ordering::SeqCst);
                            if options.auto_ack {
                                if let Some(ref gn) = options.group_name {
                                    if let Err(e) =
                                        inner_client.ack(&mail_address, gn, msg_id).await
                                    {
                                        tracing::error!(
                                            "mq9 ack error for msg_id={msg_id}: {e}"
                                        );
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            tracing::error!("mq9 handler error for msg_id={msg_id}: {e}");
                            // Do NOT ack — leave message available for redelivery.
                        }
                    }
                }
            }

            running_clone.store(false, Ordering::SeqCst);
        });

        Ok(Consumer {
            stop_tx: Some(stop_tx),
            task: Some(task),
            running,
            count,
        })
    }

    /// Query messages without affecting the consumer group offset.
    pub async fn query(
        &self,
        mail_address: &str,
        key: Option<&str>,
        limit: Option<u64>,
        since: Option<u64>,
    ) -> Result<Vec<Message>> {
        let subject = subj_msg_query(mail_address);
        let mut body = json!({});
        if let Some(k) = key {
            body["key"] = Value::String(k.to_owned());
        }
        if let Some(l) = limit {
            body["limit"] = Value::Number(l.into());
        }
        if let Some(s) = since {
            body["since"] = Value::Number(s.into());
        }
        let resp = self.request(subject, serde_json::to_vec(&body)?).await?;
        let empty = Value::Array(vec![]);
        let arr = resp.get("messages").unwrap_or(&empty);
        parse_messages(arr)
    }

    /// Delete a specific message by id.
    pub async fn delete(&self, mail_address: &str, msg_id: i64) -> Result<()> {
        let subject = subj_msg_delete(mail_address, msg_id);
        self.request(subject, b"{}".to_vec()).await?;
        Ok(())
    }

    // ------------------------------------------------------------------
    // Agent management
    // ------------------------------------------------------------------

    /// Register an Agent with its A2A-compatible agent card.
    ///
    /// `agent_card` must contain at least a `"mailbox"` field.
    pub async fn agent_register(&self, agent_card: Value) -> Result<()> {
        self.request(subj_agent_register(), serde_json::to_vec(&agent_card)?)
            .await?;
        Ok(())
    }

    /// Unregister an Agent by its mailbox address.
    pub async fn agent_unregister(&self, mailbox: &str) -> Result<()> {
        let body = json!({ "mailbox": mailbox });
        self.request(subj_agent_unregister(), serde_json::to_vec(&body)?)
            .await?;
        Ok(())
    }

    /// Report Agent status / metrics.
    ///
    /// `report` must contain at least a `"mailbox"` field.
    pub async fn agent_report(&self, report: Value) -> Result<()> {
        self.request(subj_agent_report(), serde_json::to_vec(&report)?)
            .await?;
        Ok(())
    }

    /// Discover Agents by free-text or semantic query.
    pub async fn agent_discover(
        &self,
        text: Option<&str>,
        semantic: Option<&str>,
        limit: Option<u32>,
        page: Option<u32>,
    ) -> Result<Vec<Value>> {
        let mut body = json!({
            "limit": limit.unwrap_or(20),
            "page": page.unwrap_or(1),
        });
        if let Some(t) = text {
            body["text"] = Value::String(t.to_owned());
        }
        if let Some(s) = semantic {
            body["semantic"] = Value::String(s.to_owned());
        }
        let resp = self
            .request(subj_agent_discover(), serde_json::to_vec(&body)?)
            .await?;
        Ok(resp["agents"].as_array().cloned().unwrap_or_default())
    }
}
