/**
 * mq9 JavaScript SDK — Message Demo
 *
 * Demonstrates:
 *   1. Create a mailbox
 *   2. Send messages with different priorities
 *   3. Fetch + ACK (stateful consumption)
 *   4. Consume loop (auto poll)
 *   5. Message attributes: key dedup, tags, delay, ttl
 *   6. Query without affecting offset
 *   7. Delete a message
 */

import { Mq9Client, Priority, Mq9Error } from "mq9";

const SERVER = "nats://demo.robustmq.com:4222";

async function main() {
  const client = new Mq9Client(SERVER);
  await client.connect();

  try {
    // ── 1. Create a mailbox ──────────────────────────────────────────────
    const address = await client.mailboxCreate({ name: "demo.js.message", ttl: 300 });
    console.log(`[mailbox] created: ${address}`);

    // ── 2. Send messages with different priorities ───────────────────────
    const mid1 = await client.send(address, { type: "task", id: 1 });
    console.log(`[send] normal    msg_id=${mid1}`);

    const mid2 = await client.send(address, { type: "interrupt", id: 2 }, { priority: Priority.URGENT });
    console.log(`[send] urgent    msg_id=${mid2}`);

    const mid3 = await client.send(address, { type: "abort", id: 3 }, { priority: Priority.CRITICAL });
    console.log(`[send] critical  msg_id=${mid3}`);

    // ── 3. Message attributes ────────────────────────────────────────────
    // Key dedup: only the latest message with key="status" is kept
    await client.send(address, { status: "running" }, { key: "status" });
    await client.send(address, { status: "60%" },     { key: "status" });
    const midStatus = await client.send(address, { status: "done" }, { key: "status" });
    console.log(`[send] dedup key=status, latest msg_id=${midStatus}`);

    // Tags
    await client.send(address, { order: "o-001" }, { tags: ["billing", "vip"] });
    console.log(`[send] with tags billing,vip`);

    // Per-message TTL
    await client.send(address, { temp: true }, { ttl: 10 });
    console.log(`[send] with message ttl=10s`);

    // Delayed delivery
    const delayedId = await client.send(address, { delayed: true }, { delay: 5 });
    console.log(`[send] delay=5s  msg_id=${delayedId} (returns -1 for delayed)`);

    // ── 4. Fetch + ACK (stateful) ────────────────────────────────────────
    const messages = await client.fetch(address, {
      groupName: "workers",
      deliver: "earliest",
      numMsgs: 10,
    });
    console.log(`\n[fetch] got ${messages.length} messages (priority order):`);
    for (const msg of messages) {
      const data = JSON.parse(new TextDecoder().decode(msg.payload));
      console.log(`  msg_id=${msg.msgId}  priority=${msg.priority}  payload=${JSON.stringify(data)}`);
    }

    if (messages.length > 0) {
      const lastId = messages[messages.length - 1].msgId;
      await client.ack(address, "workers", lastId);
      console.log(`[ack]   advanced offset to msg_id=${lastId}`);
    }

    // ── 5. Query without affecting offset ────────────────────────────────
    const results = await client.query(address, { key: "status" });
    console.log(`\n[query] key=status → ${results.length} message(s)`);
    for (const msg of results) {
      console.log(`  msg_id=${msg.msgId}  payload=${new TextDecoder().decode(msg.payload)}`);
    }

    // ── 6. Consume loop ──────────────────────────────────────────────────
    console.log("\n[consume] starting loop for 3 s …");

    const consumer = await client.consume(
      address,
      async (msg) => {
        const data = JSON.parse(new TextDecoder().decode(msg.payload));
        console.log(`  [handler] msg_id=${msg.msgId}  payload=${JSON.stringify(data)}`);
      },
      {
        groupName: "consume-workers",
        deliver: "earliest",
        autoAck: true,
        errorHandler: async (msg, err) => {
          console.error(`  [error]   msg_id=${msg.msgId}  error=${err.message}`);
        },
      }
    );

    await new Promise((r) => setTimeout(r, 3000));
    await consumer.stop();
    console.log(`[consume] stopped. processed=${consumer.processedCount}`);

    // ── 7. Delete a message ──────────────────────────────────────────────
    await client.delete(address, mid1);
    console.log(`\n[delete] msg_id=${mid1} deleted`);

  } finally {
    await client.close();
  }
}

main().catch(console.error);
