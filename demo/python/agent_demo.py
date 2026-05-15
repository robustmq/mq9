"""
mq9 Python SDK — Agent Demo

Demonstrates:
  1. Agent registers its capabilities
  2. Agent sends heartbeat via report
  3. Another agent discovers by full-text search
  4. Another agent discovers by semantic search
  5. Send a task to discovered agent's mailbox
  6. Agent unregisters at shutdown
"""

import asyncio
import json
from mq9 import Mq9Client, Priority, Mq9Error

SERVER = "nats://demo.robustmq.com:4222"


async def main():
    async with Mq9Client(SERVER) as client:
        # ── 1. Create mailbox for the agent ───────────────────────────────
        address = await client.mailbox_create(name="demo.python.translator", ttl=300)
        print(f"[mailbox] agent mailbox: {address}")

        # ── 2. Register agent ──────────────────────────────────────────────
        agent_card = {
            "name": "demo.python.translator",
            "mailbox": address,
            "payload": (
                "Multilingual translation agent. "
                "Supports EN, ZH, JA, KO. "
                "Input: text + target language. Output: translated text."
            ),
        }
        await client.agent_register(agent_card)
        print(f"[register] agent registered: {agent_card['name']}")

        # ── 3. Send heartbeat ──────────────────────────────────────────────
        await client.agent_report({
            "name": "demo.python.translator",
            "mailbox": address,
            "report_info": "running, processed: 128 tasks, avg latency: 320ms",
        })
        print(f"[report] heartbeat sent")

        # ── 4. Discover by full-text search ───────────────────────────────
        agents = await client.agent_discover(text="translator", limit=5)
        print(f"\n[discover] text='translator' → {len(agents)} result(s):")
        for a in agents:
            print(f"  name={a.get('name')}  mailbox={a.get('mailbox')}")

        # ── 5. Discover by semantic search ────────────────────────────────
        agents = await client.agent_discover(
            semantic="I need to translate Chinese text into English",
            limit=5,
        )
        print(f"\n[discover] semantic='translate Chinese to English' → {len(agents)} result(s):")
        for a in agents:
            print(f"  name={a.get('name')}  mailbox={a.get('mailbox')}")

        # ── 6. Send a task to the discovered agent ─────────────────────────
        if agents:
            target = agents[0].get("mailbox")
            if target:
                reply_address = await client.mailbox_create(ttl=60)
                msg_id = await client.send(
                    target,
                    {"text": "你好，世界", "target_lang": "en", "reply_to": reply_address},
                    priority=Priority.NORMAL,
                )
                print(f"\n[send] task sent to {target}  msg_id={msg_id}")
                print(f"[send] reply_to={reply_address}")

        # ── 7. List all registered agents ─────────────────────────────────
        all_agents = await client.agent_discover(limit=20)
        print(f"\n[discover] all agents → {len(all_agents)} registered")

        # ── 8. Unregister at shutdown ──────────────────────────────────────
        await client.agent_unregister(address)
        print(f"\n[unregister] agent {address} unregistered")


if __name__ == "__main__":
    asyncio.run(main())
