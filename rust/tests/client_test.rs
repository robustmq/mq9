//! Integration-style unit tests for the mq9 Rust SDK.
//!
//! All tests use an in-process fake NATS server that implements just enough of
//! the NATS protocol for request/reply to work:
//!
//! * Sends INFO on connect
//! * Reads CONNECT + PING, replies PONG
//! * Tracks SUB <subject> <sid> commands
//! * On PUB <subject> <reply> <len>, calls a handler, then delivers the response
//!   as `MSG <reply> <sid> <len>\r\n<payload>\r\n` using the sid from any matching SUB
//! * Handles HPUB the same way (stripping the header section before delivering payload)

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;

use base64::Engine as _;
use serde_json::{json, Value};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use std::sync::Mutex as StdMutex;
use tokio::sync::Mutex;

// ---------------------------------------------------------------------------
// Core fake NATS session
// ---------------------------------------------------------------------------

/// Called with (subject, payload) → returns the response bytes.
type HandlerFn = Arc<dyn Fn(String, Vec<u8>) -> Vec<u8> + Send + Sync + 'static>;

async fn run_fake_nats_session(stream: TcpStream, handler: HandlerFn) {
    let (reader, mut writer) = stream.into_split();
    let mut reader = BufReader::new(reader);
    // sid → subject_pattern (for wildcard matching)
    let mut subscriptions: HashMap<String, String> = HashMap::new();

    // 1. Send INFO.
    writer
        .write_all(
            b"INFO {\"server_id\":\"fake\",\"version\":\"2.10.0\",\"proto\":1,\
              \"host\":\"127.0.0.1\",\"port\":4222,\"max_payload\":1048576,\
              \"headers\":true,\"no_responders\":false}\r\n",
        )
        .await
        .unwrap();

    // 2. Wait for CONNECT + PING, reply PONG.
    let mut line = String::new();
    let mut connected = false;
    loop {
        line.clear();
        if reader.read_line(&mut line).await.unwrap_or(0) == 0 {
            return;
        }
        let t = line.trim_end_matches(['\r', '\n']);
        if t.starts_with("CONNECT") {
            connected = true;
        } else if t == "PING" && connected {
            writer.write_all(b"PONG\r\n").await.unwrap();
            break;
        }
    }

    // 3. Main loop.
    loop {
        line.clear();
        if reader.read_line(&mut line).await.unwrap_or(0) == 0 {
            break;
        }
        let trimmed = line.trim_end_matches(['\r', '\n']).to_string();
        let parts: Vec<&str> = trimmed.splitn(5, ' ').collect();
        let cmd = parts.first().copied().unwrap_or("");

        match cmd {
            "PING" => {
                writer.write_all(b"PONG\r\n").await.unwrap();
            }
            "PONG" | "UNSUB" => {}
            "SUB" => {
                // SUB <subject> [queue] <sid>
                // Minimal: last token is sid, second token is subject.
                if parts.len() >= 3 {
                    let subject = parts[1].to_owned();
                    let sid = parts[parts.len() - 1].to_owned();
                    subscriptions.insert(sid, subject);
                }
            }
            "PUB" => {
                // PUB <subject> [reply] <bytes>
                if parts.len() < 3 {
                    continue;
                }
                let (subject, reply, byte_str) = if parts.len() == 4 {
                    (parts[1], parts[2], parts[3])
                } else {
                    (parts[1], "", parts[2])
                };
                let byte_count: usize = byte_str.trim().parse().unwrap_or(0);
                let mut payload = vec![0u8; byte_count];
                reader.read_exact(&mut payload).await.unwrap_or(0);
                let mut crlf = [0u8; 2];
                reader.read_exact(&mut crlf).await.unwrap_or(0);

                if !reply.is_empty() {
                    let resp = handler(subject.to_owned(), payload);
                    let sid = find_sid_for(&subscriptions, reply).unwrap_or_else(|| "1".to_owned());
                    let header = format!("MSG {} {} {}\r\n", reply, sid, resp.len());
                    writer.write_all(header.as_bytes()).await.unwrap();
                    writer.write_all(&resp).await.unwrap();
                    writer.write_all(b"\r\n").await.unwrap();
                }
            }
            "HPUB" => {
                // HPUB <subject> [reply] <hdr_len> <total_len>
                if parts.len() < 4 {
                    continue;
                }
                let (subject, reply, hdr_str, total_str) = if parts.len() == 5 {
                    (parts[1], parts[2], parts[3], parts[4])
                } else {
                    (parts[1], "", parts[2], parts[3])
                };
                let hdr_len: usize = hdr_str.trim().parse().unwrap_or(0);
                let total_len: usize = total_str.trim().parse().unwrap_or(0);
                let payload_len = total_len.saturating_sub(hdr_len);

                let mut hdr_buf = vec![0u8; hdr_len];
                reader.read_exact(&mut hdr_buf).await.unwrap_or(0);
                let mut pay_buf = vec![0u8; payload_len];
                reader.read_exact(&mut pay_buf).await.unwrap_or(0);
                let mut crlf = [0u8; 2];
                reader.read_exact(&mut crlf).await.unwrap_or(0);

                if !reply.is_empty() {
                    let resp = handler(subject.to_owned(), pay_buf);
                    let sid = find_sid_for(&subscriptions, reply).unwrap_or_else(|| "1".to_owned());
                    let header = format!("MSG {} {} {}\r\n", reply, sid, resp.len());
                    writer.write_all(header.as_bytes()).await.unwrap();
                    writer.write_all(&resp).await.unwrap();
                    writer.write_all(b"\r\n").await.unwrap();
                }
            }
            _ => {}
        }
    }
}

/// Find the subscription sid whose subject pattern matches `inbox`.
/// NATS wildcards: `*` matches a single token, `>` matches the rest.
fn find_sid_for(subscriptions: &HashMap<String, String>, inbox: &str) -> Option<String> {
    for (sid, pattern) in subscriptions {
        if nats_subject_matches(pattern, inbox) {
            return Some(sid.clone());
        }
    }
    None
}

/// Minimal NATS subject matching (supports `*` and `>`).
fn nats_subject_matches(pattern: &str, subject: &str) -> bool {
    let pat_tokens: Vec<&str> = pattern.split('.').collect();
    let sub_tokens: Vec<&str> = subject.split('.').collect();

    let mut pi = 0;
    let mut si = 0;
    while pi < pat_tokens.len() && si < sub_tokens.len() {
        match pat_tokens[pi] {
            ">" => return true,
            "*" => {
                pi += 1;
                si += 1;
            }
            t if t == sub_tokens[si] => {
                pi += 1;
                si += 1;
            }
            _ => return false,
        }
    }
    pi == pat_tokens.len() && si == sub_tokens.len()
}

// ---------------------------------------------------------------------------
// Server factories
// ---------------------------------------------------------------------------

/// Start a server with a synchronous handler. Returns port.
async fn make_server<H>(handler: H) -> u16
where
    H: Fn(String, Vec<u8>) -> Vec<u8> + Send + Sync + 'static,
{
    let handler: HandlerFn = Arc::new(handler);
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();

    tokio::spawn(async move {
        loop {
            if let Ok((stream, _)) = listener.accept().await {
                let h = Arc::clone(&handler);
                tokio::spawn(run_fake_nats_session(stream, h));
            }
        }
    });

    tokio::time::sleep(std::time::Duration::from_millis(5)).await;
    port
}

/// Simple helper: always reply with a fixed JSON value.
/// Returns (port, captured_subject, captured_payload).
/// Uses `std::sync::Mutex` (not tokio) because the handler is a sync closure.
async fn one_shot_server(
    response: Value,
) -> (u16, Arc<StdMutex<String>>, Arc<StdMutex<Vec<u8>>>) {
    let cap_subj: Arc<StdMutex<String>> = Arc::new(StdMutex::new(String::new()));
    let cap_pay: Arc<StdMutex<Vec<u8>>> = Arc::new(StdMutex::new(vec![]));

    let cs = Arc::clone(&cap_subj);
    let cp = Arc::clone(&cap_pay);
    let resp_bytes = serde_json::to_vec(&response).unwrap();

    let port = make_server(move |subj, payload| {
        *cs.lock().unwrap() = subj;
        *cp.lock().unwrap() = payload;
        resp_bytes.clone()
    })
    .await;

    (port, cap_subj, cap_pay)
}

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

async fn client_on(port: u16) -> mq9::Mq9Client {
    mq9::Mq9Client::connect_with_options(
        &format!("nats://127.0.0.1:{port}"),
        mq9::ClientOptions {
            request_timeout: std::time::Duration::from_secs(3),
            reconnect_delay: std::time::Duration::from_millis(50),
        },
    )
    .await
    .unwrap()
}

fn b64(s: &str) -> String {
    base64::engine::general_purpose::STANDARD.encode(s.as_bytes())
}

// ===========================================================================
// 1. mailbox_create
// ===========================================================================

#[tokio::test]
async fn test_mailbox_create_with_name() {
    let (port, cap_subj, cap_payload) = one_shot_server(json!({
        "error": "",
        "mail_address": "agent.inbox"
    }))
    .await;

    let client = client_on(port).await;
    let addr = client.mailbox_create(Some("agent.inbox"), 3600).await.unwrap();

    assert_eq!(addr, "agent.inbox");
    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MAILBOX.CREATE");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["name"], "agent.inbox");
    assert_eq!(body["ttl"], 3600);
}

#[tokio::test]
async fn test_mailbox_create_without_name() {
    let (port, _subj, cap_payload) = one_shot_server(json!({
        "error": "",
        "mail_address": "auto.xyz"
    }))
    .await;

    let client = client_on(port).await;
    let addr = client.mailbox_create(None, 0).await.unwrap();

    assert_eq!(addr, "auto.xyz");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert!(body.get("name").is_none(), "name must be absent when None");
    assert_eq!(body["ttl"], 0);
}

#[tokio::test]
async fn test_mailbox_create_server_error() {
    let (port, _subj, _payload) =
        one_shot_server(json!({ "error": "quota exceeded" })).await;

    let client = client_on(port).await;
    let err = client.mailbox_create(Some("x"), 0).await.unwrap_err();
    assert!(
        matches!(&err, mq9::Mq9Error::Server(s) if s == "quota exceeded"),
        "unexpected: {err:?}"
    );
}

// ===========================================================================
// 2. send
// ===========================================================================

#[tokio::test]
async fn test_send_no_options_returns_msg_id() {
    let (port, cap_subj, _payload) =
        one_shot_server(json!({ "error": "", "msg_id": 7 })).await;

    let client = client_on(port).await;
    let msg_id = client
        .send("task.q", b"hello".to_vec(), mq9::SendOptions::default())
        .await
        .unwrap();

    assert_eq!(msg_id, 7);
    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MSG.SEND.task.q");
}

#[tokio::test]
async fn test_send_delay_returns_minus_one() {
    let (port, _subj, _payload) =
        one_shot_server(json!({ "error": "", "msg_id": -1 })).await;

    let client = client_on(port).await;
    let msg_id = client
        .send(
            "task.q",
            b"x".to_vec(),
            mq9::SendOptions {
                delay: Some(60),
                ..Default::default()
            },
        )
        .await
        .unwrap();

    assert_eq!(msg_id, -1);
}

#[tokio::test]
async fn test_send_urgent_priority_uses_header() {
    let (port, cap_subj, _payload) =
        one_shot_server(json!({ "error": "", "msg_id": 3 })).await;

    let client = client_on(port).await;
    let msg_id = client
        .send(
            "task.q",
            b"hi".to_vec(),
            mq9::SendOptions {
                priority: mq9::Priority::Urgent,
                ..Default::default()
            },
        )
        .await
        .unwrap();

    assert_eq!(msg_id, 3);
    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MSG.SEND.task.q");
}

#[tokio::test]
async fn test_send_with_key_delay_ttl_tags() {
    let (port, _subj, _payload) =
        one_shot_server(json!({ "error": "", "msg_id": 10 })).await;

    let client = client_on(port).await;
    let msg_id = client
        .send(
            "task.q",
            b"data".to_vec(),
            mq9::SendOptions {
                key: Some("dedup-key".into()),
                delay: Some(30),
                ttl: Some(120),
                tags: Some(vec!["a".into(), "b".into()]),
                ..Default::default()
            },
        )
        .await
        .unwrap();

    assert_eq!(msg_id, 10);
}

// ===========================================================================
// 3. fetch
// ===========================================================================

#[tokio::test]
async fn test_fetch_stateless_decodes_payload() {
    let msgs = json!([
        {"msg_id": 1, "payload": b64("hello"), "priority": "normal",   "create_time": 1000},
        {"msg_id": 2, "payload": b64("world"), "priority": "urgent",   "create_time": 1001},
    ]);
    let (port, cap_subj, cap_payload) =
        one_shot_server(json!({ "error": "", "messages": msgs })).await;

    let client = client_on(port).await;
    let messages = client
        .fetch("inbox.abc", mq9::FetchOptions::default())
        .await
        .unwrap();

    assert_eq!(messages.len(), 2);
    assert_eq!(messages[0].msg_id, 1);
    assert_eq!(messages[0].payload, b"hello");
    assert_eq!(messages[0].priority, mq9::Priority::Normal);
    assert_eq!(messages[1].priority, mq9::Priority::Urgent);
    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MSG.FETCH.inbox.abc");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert!(body.get("group_name").is_none());
    assert_eq!(body["deliver"], "latest");
}

#[tokio::test]
async fn test_fetch_stateful_with_group_name() {
    let msgs = json!([
        {"msg_id": 5, "payload": b64("task"), "priority": "critical", "create_time": 9999},
    ]);
    let (port, _subj, cap_payload) =
        one_shot_server(json!({ "error": "", "messages": msgs })).await;

    let client = client_on(port).await;
    let messages = client
        .fetch(
            "inbox.abc",
            mq9::FetchOptions {
                group_name: Some("worker-1".into()),
                deliver: Some("earliest".into()),
                ..Default::default()
            },
        )
        .await
        .unwrap();

    assert_eq!(messages[0].priority, mq9::Priority::Critical);
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["group_name"], "worker-1");
    assert_eq!(body["deliver"], "earliest");
}

#[tokio::test]
async fn test_fetch_empty() {
    let (port, _subj, _payload) =
        one_shot_server(json!({ "error": "", "messages": [] })).await;

    let client = client_on(port).await;
    let messages = client
        .fetch("inbox.abc", mq9::FetchOptions::default())
        .await
        .unwrap();

    assert!(messages.is_empty());
}

// ===========================================================================
// 4. ack
// ===========================================================================

#[tokio::test]
async fn test_ack_sends_correct_body() {
    let (port, cap_subj, cap_payload) = one_shot_server(json!({ "error": "" })).await;

    let client = client_on(port).await;
    client.ack("task.q", "worker-1", 42).await.unwrap();

    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MSG.ACK.task.q");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["group_name"], "worker-1");
    assert_eq!(body["mail_address"], "task.q");
    assert_eq!(body["msg_id"], 42);
}

// ===========================================================================
// 5. consume — happy path
// ===========================================================================

#[tokio::test]
async fn test_consume_happy_path() {
    let call_count = Arc::new(AtomicUsize::new(0));
    let ack_received = Arc::new(AtomicBool::new(false));

    let cc = Arc::clone(&call_count);
    let ar = Arc::clone(&ack_received);

    let fetch_resp = serde_json::to_vec(&json!({ "error": "", "messages": [
        {"msg_id": 1, "payload": b64("ping"), "priority": "normal", "create_time": 100}
    ]}))
    .unwrap();
    let ack_resp = serde_json::to_vec(&json!({ "error": "" })).unwrap();
    let slow_empty = serde_json::to_vec(&json!({ "error": "", "messages": [] })).unwrap();

    let port = make_server(move |subj, _payload| {
        let n = cc.fetch_add(1, Ordering::SeqCst);
        if subj.contains("ACK") {
            ar.store(true, Ordering::SeqCst);
            ack_resp.clone()
        } else if n == 0 {
            fetch_resp.clone()
        } else {
            std::thread::sleep(std::time::Duration::from_millis(500));
            slow_empty.clone()
        }
    })
    .await;

    let client = client_on(port).await;
    let received: Arc<Mutex<Vec<mq9::Message>>> = Arc::new(Mutex::new(vec![]));
    let recv_clone = Arc::clone(&received);

    let consumer = client
        .consume(
            "inbox",
            move |msg| {
                let rc = Arc::clone(&recv_clone);
                async move {
                    rc.lock().await.push(msg);
                    Ok(())
                }
            },
            mq9::ConsumeOptions {
                group_name: Some("g1".into()),
                auto_ack: true,
                ..Default::default()
            },
        )
        .await
        .unwrap();

    tokio::time::sleep(std::time::Duration::from_millis(400)).await;

    let processed = consumer.processed_count();
    assert!(processed >= 1, "expected ≥1 processed, got {processed}");
    {
        let msgs = received.lock().await;
        assert!(!msgs.is_empty());
        assert_eq!(msgs[0].payload, b"ping");
    }
    consumer.stop().await;
    assert!(ack_received.load(Ordering::SeqCst), "ACK not seen");
}

// ===========================================================================
// 5b. consume — handler error → no ack, count stays 0
// ===========================================================================

#[tokio::test]
async fn test_consume_handler_error_no_ack() {
    let ack_called = Arc::new(AtomicBool::new(false));
    let ac = Arc::clone(&ack_called);
    let first = Arc::new(AtomicBool::new(false));
    let f = Arc::clone(&first);

    let fetch_resp = serde_json::to_vec(&json!({ "error": "", "messages": [
        {"msg_id": 7, "payload": b64("bad"), "priority": "normal", "create_time": 200}
    ]}))
    .unwrap();
    let ack_resp = serde_json::to_vec(&json!({ "error": "" })).unwrap();
    let slow_empty = serde_json::to_vec(&json!({ "error": "", "messages": [] })).unwrap();

    let port = make_server(move |subj, _payload| {
        if subj.contains("ACK") {
            ac.store(true, Ordering::SeqCst);
            return ack_resp.clone();
        }
        if !f.swap(true, Ordering::SeqCst) {
            fetch_resp.clone()
        } else {
            std::thread::sleep(std::time::Duration::from_millis(500));
            slow_empty.clone()
        }
    })
    .await;

    let client = client_on(port).await;

    let consumer = client
        .consume(
            "inbox",
            move |_msg| async move { Err(mq9::Mq9Error::Server("oops".into())) },
            mq9::ConsumeOptions {
                group_name: Some("g1".into()),
                auto_ack: true,
                ..Default::default()
            },
        )
        .await
        .unwrap();

    tokio::time::sleep(std::time::Duration::from_millis(300)).await;

    assert_eq!(consumer.processed_count(), 0, "handler error must not count");
    consumer.stop().await;
    assert!(!ack_called.load(Ordering::SeqCst), "must not ACK on error");
}

// ===========================================================================
// 5c. consume — stop() terminates the loop
// ===========================================================================

#[tokio::test]
async fn test_consume_stop() {
    let port = make_server(|_subj, _payload| {
        std::thread::sleep(std::time::Duration::from_secs(10));
        serde_json::to_vec(&json!({ "error": "", "messages": [] })).unwrap()
    })
    .await;

    let client = client_on(port).await;

    let consumer = client
        .consume(
            "inbox",
            |_msg| async move { Ok(()) },
            mq9::ConsumeOptions::default(),
        )
        .await
        .unwrap();

    assert!(consumer.is_running());
    tokio::time::timeout(std::time::Duration::from_secs(5), consumer.stop())
        .await
        .expect("stop() must complete within 5 s");
}

// ===========================================================================
// 6. query
// ===========================================================================

#[tokio::test]
async fn test_query_with_filters() {
    let msgs = json!([
        {"msg_id": 3, "payload": b64("q"), "priority": "normal", "create_time": 500},
    ]);
    let (port, cap_subj, cap_payload) =
        one_shot_server(json!({ "error": "", "messages": msgs })).await;

    let client = client_on(port).await;
    let messages = client
        .query("inbox", Some("status"), Some(5), Some(400))
        .await
        .unwrap();

    assert_eq!(messages.len(), 1);
    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MSG.QUERY.inbox");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["key"], "status");
    assert_eq!(body["limit"], 5);
    assert_eq!(body["since"], 400);
}

#[tokio::test]
async fn test_query_without_filters() {
    let (port, _subj, cap_payload) =
        one_shot_server(json!({ "error": "", "messages": [] })).await;

    let client = client_on(port).await;
    let messages = client.query("inbox", None, None, None).await.unwrap();

    assert!(messages.is_empty());
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert!(body.get("key").is_none());
    assert!(body.get("limit").is_none());
    assert!(body.get("since").is_none());
}

// ===========================================================================
// 7. delete
// ===========================================================================

#[tokio::test]
async fn test_delete_correct_subject() {
    let (port, cap_subj, _payload) = one_shot_server(json!({ "error": "" })).await;

    let client = client_on(port).await;
    client.delete("task.q", 99).await.unwrap();

    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.MSG.DELETE.task.q.99");
}

// ===========================================================================
// 8. agent_register
// ===========================================================================

#[tokio::test]
async fn test_agent_register_passes_card() {
    let (port, cap_subj, cap_payload) = one_shot_server(json!({ "error": "" })).await;

    let client = client_on(port).await;
    let card = json!({
        "mailbox": "agent.payments",
        "name": "PaymentAgent",
        "version": "1.0"
    });
    client.agent_register(card.clone()).await.unwrap();

    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.AGENT.REGISTER");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body, card);
}

// ===========================================================================
// 9. agent_unregister
// ===========================================================================

#[tokio::test]
async fn test_agent_unregister() {
    let (port, cap_subj, cap_payload) = one_shot_server(json!({ "error": "" })).await;

    let client = client_on(port).await;
    client.agent_unregister("agent.payments").await.unwrap();

    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.AGENT.UNREGISTER");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["mailbox"], "agent.payments");
}

// ===========================================================================
// 10. agent_report
// ===========================================================================

#[tokio::test]
async fn test_agent_report() {
    let (port, cap_subj, cap_payload) = one_shot_server(json!({ "error": "" })).await;

    let client = client_on(port).await;
    let report = json!({
        "mailbox": "agent.payments",
        "status": "healthy",
        "load": 0.3
    });
    client.agent_report(report.clone()).await.unwrap();

    assert_eq!(*cap_subj.lock().unwrap(), "$mq9.AI.AGENT.REPORT");
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["mailbox"], "agent.payments");
    assert_eq!(body["status"], "healthy");
}

// ===========================================================================
// 11. agent_discover
// ===========================================================================

#[tokio::test]
async fn test_agent_discover_with_text() {
    let agents = json!([{"mailbox": "agent.pay", "name": "PayAgent"}]);
    let (port, _subj, cap_payload) =
        one_shot_server(json!({ "error": "", "agents": agents })).await;

    let client = client_on(port).await;
    let result = client
        .agent_discover(Some("payment"), None, None, None)
        .await
        .unwrap();

    assert_eq!(result.len(), 1);
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["text"], "payment");
    assert_eq!(body["limit"], 20);
    assert_eq!(body["page"], 1);
}

#[tokio::test]
async fn test_agent_discover_with_semantic_and_pagination() {
    let (port, _subj, cap_payload) =
        one_shot_server(json!({ "error": "", "agents": [] })).await;

    let client = client_on(port).await;
    let result = client
        .agent_discover(None, Some("process payment refund"), Some(5), Some(2))
        .await
        .unwrap();

    assert!(result.is_empty());
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert_eq!(body["semantic"], "process payment refund");
    assert_eq!(body["limit"], 5);
    assert_eq!(body["page"], 2);
    assert!(body.get("text").is_none());
}

#[tokio::test]
async fn test_agent_discover_empty() {
    let (port, _subj, cap_payload) =
        one_shot_server(json!({ "error": "", "agents": [] })).await;

    let client = client_on(port).await;
    let result = client.agent_discover(None, None, None, None).await.unwrap();

    assert!(result.is_empty());
    let body: Value = serde_json::from_slice(&cap_payload.lock().unwrap()).unwrap();
    assert!(body.get("text").is_none());
    assert!(body.get("semantic").is_none());
    assert_eq!(body["limit"], 20);
    assert_eq!(body["page"], 1);
}
