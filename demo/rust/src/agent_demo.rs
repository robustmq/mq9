// mq9 Rust SDK — Agent Demo
//
// Demonstrates:
//   1. Agent registers its capabilities
//   2. Agent sends heartbeat via report
//   3. Discover by full-text search
//   4. Discover by semantic search
//   5. Send a task to discovered agent's mailbox
//   6. Agent unregisters at shutdown

use mq9::{Mq9Client, SendOptions};
use serde_json::json;

const SERVER: &str = "nats://demo.robustmq.com:4222";

#[tokio::main]
async fn main() -> mq9::Result<()> {
    let client = Mq9Client::connect(SERVER).await?;

    // ── 1. Create mailbox for the agent ─────────────────────────────────
    let address = client.mailbox_create(Some("demo.rust.translator"), 300).await?;
    println!("[mailbox] agent mailbox: {}", address);

    // ── 2. Register agent ────────────────────────────────────────────────
    client.agent_register(json!({
        "name": "demo.rust.translator",
        "mailbox": address,
        "payload": "Multilingual translation agent. Supports EN, ZH, JA, KO. Input: text + target language. Output: translated text."
    })).await?;
    println!("[register] agent registered: demo.rust.translator");

    // ── 3. Send heartbeat ────────────────────────────────────────────────
    client.agent_report(json!({
        "name": "demo.rust.translator",
        "mailbox": address,
        "report_info": "running, processed: 512 tasks, avg latency: 210ms"
    })).await?;
    println!("[report] heartbeat sent");

    // ── 4. Discover by full-text search ──────────────────────────────────
    let by_text = client.agent_discover(Some("translator"), None, Some(5), Some(1)).await?;
    println!("\n[discover] text='translator' → {} result(s):", by_text.len());
    for a in &by_text {
        println!("  name={}  mailbox={}", a["name"], a["mailbox"]);
    }

    // ── 5. Discover by semantic search ───────────────────────────────────
    let by_semantic = client.agent_discover(
        None,
        Some("I need to translate Chinese text into English"),
        Some(5),
        Some(1),
    ).await?;
    println!("\n[discover] semantic='translate Chinese to English' → {} result(s):", by_semantic.len());
    for a in &by_semantic {
        println!("  name={}  mailbox={}", a["name"], a["mailbox"]);
    }

    // ── 6. Send a task to discovered agent ───────────────────────────────
    if let Some(first) = by_semantic.first() {
        if let Some(target) = first["mailbox"].as_str() {
            let reply_address = client.mailbox_create(None, 60).await?;
            let payload = json!({
                "text": "你好，世界",
                "target_lang": "en",
                "reply_to": reply_address
            });
            let msg_id = client.send(target, payload.to_string(), SendOptions::default()).await?;
            println!("\n[send] task sent to {}  msg_id={}", target, msg_id);
            println!("[send] reply_to={}", reply_address);
        }
    }

    // ── 7. List all agents ────────────────────────────────────────────────
    let all = client.agent_discover(None, None, Some(20), Some(1)).await?;
    println!("\n[discover] all agents → {} registered", all.len());

    // ── 8. Unregister ─────────────────────────────────────────────────────
    client.agent_unregister(&address).await?;
    println!("\n[unregister] agent {} unregistered", address);

    client.close().await?;
    Ok(())
}
