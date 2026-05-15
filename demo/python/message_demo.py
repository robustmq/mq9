"""
mq9 Python SDK — Message Demo

Demonstrates:
  1. Create a mailbox
  2. Send messages with different priorities
  3. Fetch + ACK (stateful consumption)
  4. Consume loop (auto poll)
  5. Message attributes: key dedup, tags, delay, ttl
  6. Query without affecting offset
  7. Delete a message
"""

import asyncio
import json
from mq9 import Mq9Client, Priority, Mq9Error

SERVER = "nats://demo.robustmq.com:4222"


async def main():
    async with Mq9Client(SERVER) as client:
        # ── 1. Create a mailbox ────────────────────────────────────────────
        address = await client.mailbox_create(name="demo.python.message", ttl=300)
        print(f"[mailbox] created: {address}")

        # ── 2. Send messages with different priorities ─────────────────────
        mid1 = await client.send(address, {"type": "task", "id": 1}, priority=Priority.NORMAL)
        print(f"[send] normal     msg_id={mid1}")

        mid2 = await client.send(address, {"type": "interrupt", "id": 2}, priority=Priority.URGENT)
        print(f"[send] urgent     msg_id={mid2}")

        mid3 = await client.send(address, {"type": "abort", "id": 3}, priority=Priority.CRITICAL)
        print(f"[send] critical   msg_id={mid3}")

        # ── 3. Message attributes ──────────────────────────────────────────
        # Key dedup: only the latest message with key="status" is kept
        await client.send(address, {"status": "running"}, key="status")
        await client.send(address, {"status": "60%"},     key="status")
        mid_status = await client.send(address, {"status": "done"}, key="status")
        print(f"[send] dedup key=status, latest msg_id={mid_status}")

        # Tags
        await client.send(address, {"order": "o-001"}, tags=["billing", "vip"])
        print(f"[send] with tags billing,vip")

        # Per-message TTL (expires in 10 s regardless of mailbox TTL)
        await client.send(address, {"temp": True}, ttl=10)
        print(f"[send] with message ttl=10s")

        # Delayed delivery (visible after 5 s)
        delayed_id = await client.send(address, {"delayed": True}, delay=5)
        print(f"[send] delay=5s  msg_id={delayed_id} (returns -1 for delayed)")

        # ── 4. Fetch + ACK (stateful) ──────────────────────────────────────
        # Messages returned in priority order: critical → urgent → normal
        messages = await client.fetch(address, group_name="workers", deliver="earliest", num_msgs=10)
        print(f"\n[fetch] got {len(messages)} messages (priority order):")
        for msg in messages:
            data = json.loads(msg.payload)
            print(f"  msg_id={msg.msg_id}  priority={msg.priority.value}  payload={data}")

        if messages:
            await client.ack(address, "workers", messages[-1].msg_id)
            print(f"[ack]   advanced offset to msg_id={messages[-1].msg_id}")

        # ── 5. Query without affecting offset ─────────────────────────────
        results = await client.query(address, key="status")
        print(f"\n[query] key=status → {len(results)} message(s)")
        for msg in results:
            print(f"  msg_id={msg.msg_id}  payload={json.loads(msg.payload)}")

        # ── 6. Consume loop ────────────────────────────────────────────────
        print("\n[consume] starting loop for 3 s …")

        async def handler(msg):
            data = json.loads(msg.payload)
            print(f"  [handler] msg_id={msg.msg_id}  payload={data}")

        async def on_error(msg, exc):
            print(f"  [error]   msg_id={msg.msg_id}  error={exc}")

        consumer = await client.consume(
            address,
            handler,
            group_name="consume-workers",
            deliver="earliest",
            auto_ack=True,
            error_handler=on_error,
        )
        await asyncio.sleep(3)
        await consumer.stop()
        print(f"[consume] stopped. processed={consumer.processed_count}")

        # ── 7. Delete a message ────────────────────────────────────────────
        await client.delete(address, mid1)
        print(f"\n[delete] msg_id={mid1} deleted")


if __name__ == "__main__":
    asyncio.run(main())
