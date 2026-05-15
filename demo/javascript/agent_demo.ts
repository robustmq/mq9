/**
 * mq9 JavaScript SDK — Agent Demo
 *
 * Demonstrates:
 *   1. Agent registers its capabilities
 *   2. Agent sends heartbeat via report
 *   3. Discover by full-text search
 *   4. Discover by semantic search
 *   5. Send a task to discovered agent's mailbox
 *   6. Agent unregisters at shutdown
 */

import { Mq9Client, Priority } from "mq9";

const SERVER = "nats://demo.robustmq.com:4222";

async function main() {
  const client = new Mq9Client(SERVER);
  await client.connect();

  try {
    // ── 1. Create mailbox for the agent ─────────────────────────────────
    const address = await client.mailboxCreate({ name: "demo.js.translator", ttl: 300 });
    console.log(`[mailbox] agent mailbox: ${address}`);

    // ── 2. Register agent ────────────────────────────────────────────────
    await client.agentRegister({
      name: "demo.js.translator",
      mailbox: address,
      payload:
        "Multilingual translation agent. " +
        "Supports EN, ZH, JA, KO. " +
        "Input: text + target language. Output: translated text.",
    });
    console.log(`[register] agent registered: demo.js.translator`);

    // ── 3. Send heartbeat ────────────────────────────────────────────────
    await client.agentReport({
      name: "demo.js.translator",
      mailbox: address,
      report_info: "running, processed: 64 tasks",
    });
    console.log(`[report] heartbeat sent`);

    // ── 4. Discover by full-text search ──────────────────────────────────
    const byText = await client.agentDiscover({ text: "translator", limit: 5 });
    console.log(`\n[discover] text='translator' → ${byText.length} result(s):`);
    for (const a of byText) {
      console.log(`  name=${a["name"]}  mailbox=${a["mailbox"]}`);
    }

    // ── 5. Discover by semantic search ───────────────────────────────────
    const bySemantic = await client.agentDiscover({
      semantic: "I need to translate Chinese text into English",
      limit: 5,
    });
    console.log(`\n[discover] semantic='translate Chinese to English' → ${bySemantic.length} result(s):`);
    for (const a of bySemantic) {
      console.log(`  name=${a["name"]}  mailbox=${a["mailbox"]}`);
    }

    // ── 6. Send a task to discovered agent ───────────────────────────────
    if (bySemantic.length > 0) {
      const target = bySemantic[0]["mailbox"] as string;
      if (target) {
        const replyAddress = await client.mailboxCreate({ ttl: 60 });
        const msgId = await client.send(
          target,
          { text: "你好，世界", target_lang: "en", reply_to: replyAddress },
          { priority: Priority.NORMAL }
        );
        console.log(`\n[send] task sent to ${target}  msg_id=${msgId}`);
        console.log(`[send] reply_to=${replyAddress}`);
      }
    }

    // ── 7. List all agents ────────────────────────────────────────────────
    const all = await client.agentDiscover({ limit: 20 });
    console.log(`\n[discover] all agents → ${all.length} registered`);

    // ── 8. Unregister ─────────────────────────────────────────────────────
    await client.agentUnregister(address);
    console.log(`\n[unregister] agent ${address} unregistered`);

  } finally {
    await client.close();
  }
}

main().catch(console.error);
