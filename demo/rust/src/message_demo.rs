// mq9 Rust SDK — Message Demo
//
// Demonstrates:
//   1. Create a mailbox
//   2. Send messages with different priorities
//   3. Fetch + ACK (stateful consumption)
//   4. Consume loop (auto poll)
//   5. Message attributes: key dedup, tags, delay, ttl
//   6. Query without affecting offset
//   7. Delete a message

use mq9::{ConsumeOptions, FetchOptions, Mq9Client, Priority, SendOptions};
use serde_json::json;
use std::time::Duration;

const SERVER: &str = "nats://demo.robustmq.com:4222";

#[tokio::main]
async fn main() -> mq9::Result<()> {
    // ── 1. Create a mailbox ──────────────────────────────────────────────
    let client = Mq9Client::connect(SERVER).await?;
    let address = client.mailbox_create(Some("demo.rust.message"), 300).await?;
    println!("[mailbox] created: {}", address);

    // ── 2. Send messages with different priorities ───────────────────────
    let mid1 = client.send(&address, json!({"type": "task", "id": 1}).to_string(), SendOptions::default()).await?;
    println!("[send] normal    msg_id={}", mid1);

    let mid2 = client.send(&address, json!({"type": "interrupt", "id": 2}).to_string(), SendOptions {
        priority: Priority::Urgent,
        ..Default::default()
    }).await?;
    println!("[send] urgent    msg_id={}", mid2);

    let mid3 = client.send(&address, json!({"type": "abort", "id": 3}).to_string(), SendOptions {
        priority: Priority::Critical,
        ..Default::default()
    }).await?;
    println!("[send] critical  msg_id={}", mid3);

    // ── 3. Message attributes ────────────────────────────────────────────
    // Key dedup: only the latest message with key="status" is kept
    client.send(&address, json!({"status": "running"}).to_string(), SendOptions { key: Some("status".into()), ..Default::default() }).await?;
    client.send(&address, json!({"status": "60%"}).to_string(),     SendOptions { key: Some("status".into()), ..Default::default() }).await?;
    let mid_status = client.send(&address, json!({"status": "done"}).to_string(), SendOptions {
        key: Some("status".into()),
        ..Default::default()
    }).await?;
    println!("[send] dedup key=status, latest msg_id={}", mid_status);

    // Tags
    client.send(&address, json!({"order": "o-001"}).to_string(), SendOptions {
        tags: Some(vec!["billing".into(), "vip".into()]),
        ..Default::default()
    }).await?;
    println!("[send] with tags billing,vip");

    // Per-message TTL
    client.send(&address, json!({"temp": true}).to_string(), SendOptions {
        ttl: Some(10),
        ..Default::default()
    }).await?;
    println!("[send] with message ttl=10s");

    // Delayed delivery
    let delayed_id = client.send(&address, json!({"delayed": true}).to_string(), SendOptions {
        delay: Some(5),
        ..Default::default()
    }).await?;
    println!("[send] delay=5s  msg_id={} (returns -1 for delayed)", delayed_id);

    // ── 4. Fetch + ACK (stateful) ────────────────────────────────────────
    let messages = client.fetch(&address, FetchOptions {
        group_name: Some("workers".into()),
        deliver: Some("earliest".into()),
        num_msgs: Some(10),
        ..Default::default()
    }).await?;
    println!("\n[fetch] got {} messages (priority order):", messages.len());
    for msg in &messages {
        println!("  msg_id={}  priority={:?}  payload={}", msg.msg_id, msg.priority,
            String::from_utf8_lossy(&msg.payload));
    }

    if let Some(last) = messages.last() {
        client.ack(&address, "workers", last.msg_id).await?;
        println!("[ack]   advanced offset to msg_id={}", last.msg_id);
    }

    // ── 5. Query without affecting offset ────────────────────────────────
    let results = client.query(&address, Some("status"), None, None).await?;
    println!("\n[query] key=status → {} message(s)", results.len());
    for msg in &results {
        println!("  msg_id={}  payload={}", msg.msg_id, String::from_utf8_lossy(&msg.payload));
    }

    // ── 6. Consume loop ──────────────────────────────────────────────────
    println!("\n[consume] starting loop for 3 s …");

    let consumer = client.consume(
        &address,
        |msg| async move {
            println!("  [handler] msg_id={}  priority={:?}  payload={}",
                msg.msg_id, msg.priority, String::from_utf8_lossy(&msg.payload));
            Ok(())
        },
        ConsumeOptions {
            group_name: Some("consume-workers".into()),
            deliver: Some("earliest".into()),
            auto_ack: true,
            ..Default::default()
        },
    ).await?;

    tokio::time::sleep(Duration::from_secs(3)).await;
    consumer.stop().await;
    println!("[consume] stopped. processed={}", consumer.processed_count());

    // ── 7. Delete a message ──────────────────────────────────────────────
    client.delete(&address, mid1).await?;
    println!("\n[delete] msg_id={} deleted", mid1);

    client.close().await?;
    Ok(())
}
