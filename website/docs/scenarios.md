# Scenarios

Eight concrete Agent communication patterns, ordered from registry and discovery patterns through to messaging patterns. Each example uses the NATS CLI or Python SDK against `nats://demo.robustmq.com:4222`.

---

## 1. Capability-Based Agent Routing

An orchestrator receives a task — say, translating a document — but does not hardcode which agent handles it. Instead, it queries the registry at runtime using a semantic description of the task, gets back a list of capable agents, picks the best match, and routes the message to that agent's mailbox.

This is the canonical mq9 pattern: **discover first, then send.**

```bash
# Step 1: Translator agent registers at startup
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "mq9://demo.robustmq.com/agent.translator.inbox",
  "payload": "Multilingual translation agent; supports EN/ZH/JA/KO/DE/FR; returns results as JSON"
}'

# Step 2: Orchestrator discovers capable agents by semantic intent
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "translate a document from Chinese to English",
  "limit": 3
}'
# Response includes matched agents with their mailbox addresses

# Step 3: Orchestrator sends task to the discovered agent's mailbox
nats request '$mq9.AI.MSG.SEND.agent.translator.inbox' '{
  "doc_id": "doc-001",
  "source_lang": "zh",
  "target_lang": "en",
  "reply_to": "orchestrator.results.a1b2c3"
}'
```

**Key mq9 features:** semantic DISCOVER, dynamic mailbox routing, store-first delivery.

---

## 2. Sub-Agent Result Delivery

An orchestrator spawns a sub-agent for a long-running task and cannot block waiting for the result. The orchestrator creates a private reply mailbox and shares the `mail_address` with the sub-agent at spawn time. The sub-agent deposits its result when done. The orchestrator FETCHes the reply whenever it is ready.

No polling loop, no callback registration, no shared state — just a mailbox.

```bash
# Orchestrator: create private reply mailbox (TTL covers max expected task duration)
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl": 3600}'
# Response: {"error":"","mail_address":"d7a5072lko83"}

# Orchestrator: dispatch task to sub-agent's mailbox, embed reply_to
nats request '$mq9.AI.MSG.SEND.task.dispatch' '{
  "task": "summarize /data/corpus",
  "reply_to": "d7a5072lko83"
}'

# Sub-agent: deposit result when done (orchestrator may be busy or temporarily offline)
nats request '$mq9.AI.MSG.SEND.d7a5072lko83' '{
  "status": "ok",
  "summary": "The corpus contains 14,203 documents across 8 topics..."
}'

# Orchestrator: FETCH result whenever ready — message was stored even if orchestrator was busy
nats request '$mq9.AI.MSG.FETCH.d7a5072lko83' '{
  "group_name": "orchestrator",
  "deliver": "earliest"
}'
# ACK to advance offset
nats request '$mq9.AI.MSG.ACK.d7a5072lko83' '{
  "group_name": "orchestrator",
  "mail_address": "d7a5072lko83",
  "msg_id": 1
}'
```

**Key mq9 features:** private mailbox, store-first delivery, FETCH+ACK async result pickup.

---

## 3. Multi-Worker Competing Task Queue

A producer sends tasks into a shared mailbox. Multiple workers compete to consume — each task is processed exactly once. Workers share a single `group_name`; the broker's offset advances on ACK, preventing duplicate delivery across workers. Workers can join or leave at any time without reconfiguration.

```bash
# One-time: create shared task queue mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"name": "task.queue", "ttl": 86400}'

# Producer: publish tasks with priority levels
nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:critical' \
  '{"task": "reindex_db", "id": "t-101"}'

nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:urgent' \
  '{"task": "flush_cache", "id": "t-102"}'

nats request '$mq9.AI.MSG.SEND.task.queue' \
  '{"task": "summarize_logs", "id": "t-103"}'

# Worker (any instance): fetch one task at a time from the shared group
nats request '$mq9.AI.MSG.FETCH.task.queue' '{
  "group_name": "workers",
  "deliver": "earliest",
  "config": {"num_msgs": 1}
}'
# Returns t-101 first (critical), then t-102, then t-103

# Worker: ACK after successful processing — advances shared offset
nats request '$mq9.AI.MSG.ACK.task.queue' '{
  "group_name": "workers",
  "mail_address": "task.queue",
  "msg_id": 1
}'
```

**Key mq9 features:** shared mailbox, stateful consumer group, three-tier priority ordering, competing consumers.

---

## 4. Agent Registration and Health Tracking

An orchestrator needs to know which agents are alive and what they can do — without polling them individually. Agents register at startup, send periodic heartbeats via REPORT, and unregister at shutdown. The orchestrator uses DISCOVER to enumerate the live network at any time.

```bash
# Agent at startup: register with capability description
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "worker-image-42",
  "mailbox": "mq9://demo.robustmq.com/worker.image.42.inbox",
  "payload": "Image processing worker; supports JPEG/PNG/WebP; GPU-accelerated; max 4K resolution"
}'

# Agent: send heartbeat every 30 seconds
nats request '$mq9.AI.AGENT.REPORT' '{
  "mailbox": "mq9://demo.robustmq.com/worker.image.42.inbox",
  "status": "running",
  "processed_today": 1024,
  "queue_depth": 3
}'

# Orchestrator: discover all image-capable workers
nats request '$mq9.AI.AGENT.DISCOVER' '{"text": "image processing"}'

# Orchestrator: full registry enumeration
nats request '$mq9.AI.AGENT.DISCOVER' '{}'

# Agent at shutdown: unregister (removed from DISCOVER results immediately)
nats request '$mq9.AI.AGENT.UNREGISTER' '{
  "mailbox": "mq9://demo.robustmq.com/worker.image.42.inbox"
}'
```

**Key mq9 features:** AGENT.REGISTER / UNREGISTER / REPORT lifecycle, DISCOVER for live agent enumeration.

---

## 5. Cloud-to-Edge Command Delivery

A cloud orchestrator delivers commands to edge agents that may be offline for hours due to intermittent connectivity. When an edge agent reconnects, it FETCHes all pending commands in priority order — `critical` reconfiguration or abort commands are returned before any accumulated `normal` routine tasks. No retry logic or bridging is needed on the cloud side.

```bash
# Cloud: create edge agent's mailbox (long TTL to survive extended offline periods)
nats request '$mq9.AI.MAILBOX.CREATE' '{
  "name": "edge.agent.sensor7",
  "ttl": 604800
}'

# Cloud: send critical reconfiguration (processed first on reconnect)
nats request '$mq9.AI.MSG.SEND.edge.agent.sensor7' \
  --header 'mq9-priority:critical' \
  '{"cmd": "reconfigure", "params": {"sampling_rate": 100, "mode": "high_fidelity"}}'

# Cloud: send routine tasks (processed after critical commands)
nats request '$mq9.AI.MSG.SEND.edge.agent.sensor7' \
  '{"cmd": "run_diagnostic", "target": "sensor-bank-2"}'

nats request '$mq9.AI.MSG.SEND.edge.agent.sensor7' \
  '{"cmd": "upload_logs", "since": 1712600000}'

# Edge agent: on reconnect, fetch all pending commands (returned in priority order)
nats request '$mq9.AI.MSG.FETCH.edge.agent.sensor7' '{
  "group_name": "sensor7",
  "deliver": "earliest",
  "config": {"num_msgs": 50}
}'

# Edge agent: ACK each command after processing
nats request '$mq9.AI.MSG.ACK.edge.agent.sensor7' '{
  "group_name": "sensor7",
  "mail_address": "edge.agent.sensor7",
  "msg_id": 1
}'
```

**Key mq9 features:** message persistence across offline periods, priority-ordered pull on reconnect, private mailbox.

---

## 6. Human-in-the-Loop Approval

An agent generates a decision that requires human review before proceeding — for example, deleting a production dataset or sending a communication on behalf of a user. The approval request goes into a shared mailbox. A human operator (using any NATS client or a UI backed by mq9) fetches it and sends a decision to the agent's private reply mailbox. The agent blocks on FETCH until the decision arrives or the TTL expires.

Humans interact using the exact same mq9 protocol as any other agent — no separate approval service, no webhook infrastructure.

```python
import nats, asyncio, json

async def run():
    nc = await nats.connect("nats://demo.robustmq.com:4222")

    # Agent: create private reply mailbox (TTL = review window)
    reply = await nc.request("$mq9.AI.MAILBOX.CREATE", b'{"ttl": 7200}')
    reply_addr = json.loads(reply.data)["mail_address"]

    # Agent: submit decision for human review
    await nc.request(
        "$mq9.AI.MSG.SEND.approvals",
        json.dumps({
            "action": "delete_dataset",
            "target": "ds-prod-2024",
            "requestor": "agent.cleanup",
            "reply_to": reply_addr
        }).encode(),
        headers={"mq9-priority": "urgent"}
    )

    # Human operator (NATS CLI or UI):
    #   nats request '$mq9.AI.MSG.FETCH.approvals' '{"deliver":"earliest"}'
    #   → reads the pending request, sees reply_to address
    #   nats request '$mq9.AI.MSG.SEND.<reply_addr>' '{"approved":true,"reviewer":"alice"}'

    # Agent: wait for decision (max_wait_ms = review window in ms)
    resp = await nc.request(
        f"$mq9.AI.MSG.FETCH.{reply_addr}",
        json.dumps({
            "deliver": "earliest",
            "config": {"max_wait_ms": 7200000}
        }).encode()
    )
    messages = json.loads(resp.data).get("messages", [])
    if messages:
        decision = json.loads(messages[0]["payload"])
        print("Approval decision:", decision)
    else:
        print("Review window expired — request timed out")

asyncio.run(run())
```

**Key mq9 features:** same protocol for humans and agents, async FETCH with configurable wait, store-first delivery, private reply mailbox.

---

## 7. Async Request-Reply

Agent A needs a result from Agent B, but B may not be available immediately and A cannot afford to block. A creates a private reply mailbox, embeds the `mail_address` as a `reply_to` field in the request, and continues other work. B processes the request at its own pace and deposits the result into A's reply mailbox. A FETCHes the reply whenever it is ready.

```bash
# Agent A: create private reply mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl": 600}'
# Response: {"error":"","mail_address":"reply.a1b2c3"}

# Agent A: send request to Agent B's mailbox with reply_to embedded
nats request '$mq9.AI.MSG.SEND.agent.translator.inbox' '{
  "request": "translate",
  "text": "Hello, world",
  "source_lang": "en",
  "target_lang": "fr",
  "reply_to": "reply.a1b2c3"
}'

# Agent A: continues other work while B processes...

# Agent B: fetch pending requests from its own mailbox
nats request '$mq9.AI.MSG.FETCH.agent.translator.inbox' '{
  "group_name": "translator-worker",
  "deliver": "earliest"
}'

# Agent B: deposit result into A's reply mailbox
nats request '$mq9.AI.MSG.SEND.reply.a1b2c3' '{
  "result": "Bonjour, le monde",
  "source_lang": "en",
  "target_lang": "fr"
}'

# Agent B: ACK its own offset
nats request '$mq9.AI.MSG.ACK.agent.translator.inbox' '{
  "group_name": "translator-worker",
  "mail_address": "agent.translator.inbox",
  "msg_id": 1
}'

# Agent A: FETCH reply when ready — result is already stored
nats request '$mq9.AI.MSG.FETCH.reply.a1b2c3' '{"deliver": "earliest"}'
```

**Key mq9 features:** private reply mailbox, store-first delivery, non-blocking async request-reply pattern.

---

## 8. Alert Broadcasting

Any agent can detect an anomaly and publish an alert to a shared mailbox at `critical` priority. Multiple handler groups independently consume from the same mailbox — each group receives all alerts with its own offset. Handlers that are temporarily offline receive all missed alerts on reconnect; `critical` priority ensures they are returned before any lower-priority backlog.

```bash
# One-time: create shared alerts mailbox (no TTL — never expires)
nats request '$mq9.AI.MAILBOX.CREATE' '{"name": "alerts", "ttl": 0}'

# Any monitoring agent: publish alert at critical priority
nats request '$mq9.AI.MSG.SEND.alerts' \
  --header 'mq9-priority:critical' \
  '{
    "type": "anomaly",
    "source": "monitor-7",
    "detail": "CPU > 95% for 5 consecutive minutes",
    "ts": 1712600100
  }'

# Handler group 1 (e.g., pager duty integration): fetch and ACK
nats request '$mq9.AI.MSG.FETCH.alerts' '{
  "group_name": "pagerduty-handler",
  "deliver": "earliest"
}'
nats request '$mq9.AI.MSG.ACK.alerts' '{
  "group_name": "pagerduty-handler",
  "mail_address": "alerts",
  "msg_id": 5
}'

# Handler group 2 (e.g., audit log writer): independent offset, receives the same alerts
nats request '$mq9.AI.MSG.FETCH.alerts' '{
  "group_name": "audit-log",
  "deliver": "earliest"
}'
nats request '$mq9.AI.MSG.ACK.alerts' '{
  "group_name": "audit-log",
  "mail_address": "alerts",
  "msg_id": 5
}'
```

**Key mq9 features:** message persistence (handlers receive alerts even if temporarily offline), critical priority, multiple independent consumer groups, fan-out via shared mailbox.
