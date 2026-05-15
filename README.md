# mq9

**Agent registration, discovery, and reliable async messaging — in one broker.**

mq9 is a broker built specifically for AI Agent networks. It solves the two foundational problems every multi-agent system faces: how agents find each other, and how they communicate reliably. Designed to scale to millions of agents.

→ [mq9.robustmq.com](https://mq9.robustmq.com) · [Protocol Spec](./protocol.md) · [RobustMQ](https://github.com/robustmq/robustmq)

---

## Two Problems. One Broker.

**Problem 1 — Agents cannot find each other.**
Agents are dynamic. They come online with different capabilities, at different times. Without a registry, every team hardcodes addresses or builds their own directory. mq9 gives every Agent a place to publish its capabilities and be discovered by others — by keyword or by semantic intent.

**Problem 2 — Agents are not always online at the same time.**
Agents are task-driven — they start, execute, and stop. When Agent A sends to Agent B and B is offline, the message is lost. HTTP requires both sides to be online. Redis pub/sub has no persistence. mq9 solves this with persistent mailboxes: send a message, the recipient gets it whenever they come online.

---

## Try it — public demo server

```bash
export NATS_URL=nats://demo.robustmq.com:4222

# 1. Register an Agent
nats request '$mq9.AI.AGENT.REGISTER' \
  '{"name":"agent.translator","mailbox":"agent.translator","payload":"Multilingual translation; EN/ZH/JA/KO"}'

# 2. Discover Agents by semantic intent
nats request '$mq9.AI.AGENT.DISCOVER' \
  '{"semantic":"translate Chinese to English","limit":5}'

# 3. Create a mailbox
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.translator","ttl":3600}'

# 4. Send a message with priority
nats request '$mq9.AI.MSG.SEND.agent.translator' \
  --header 'mq9-priority:critical' \
  '{"task":"translate","text":"Hello world","lang":"zh"}'

# 5. Fetch messages (priority order: critical → urgent → normal)
nats request '$mq9.AI.MSG.FETCH.agent.translator' \
  '{"group_name":"workers","deliver":"earliest"}'

# 6. ACK to advance offset
nats request '$mq9.AI.MSG.ACK.agent.translator' \
  '{"group_name":"workers","mail_address":"agent.translator","msg_id":1}'
```

---

## SDKs

| Language   | Install                             | Directory     |
| ---------- | ----------------------------------- | ------------- |
| Python     | `pip install mq9`                   | `python/`     |
| JavaScript | `npm install mq9`                   | `javascript/` |
| Go         | `go get github.com/robustmq/mq9/go` | `go/`         |
| Rust       | `cargo add mq9`                     | `rust/`       |
| Java       | `io.mq9:mq9:0.1.0`                  | `java/`       |

### Python

```python
from mq9 import Mq9Client, Priority

async with Mq9Client("nats://localhost:4222") as client:
    # Register Agent
    await client.agent_register({
        "name": "agent.translator",
        "mailbox": "agent.translator",
        "payload": "Multilingual translation; EN/ZH/JA/KO",
    })

    # Discover Agents by semantic intent
    agents = await client.agent_discover(semantic="translate Chinese to English", limit=5)

    # Create mailbox and send
    address = await client.mailbox_create(name="agent.inbox", ttl=3600)
    await client.send(address, b'{"task":"analyze"}', priority=Priority.URGENT)

    # Continuous consume loop
    consumer = await client.consume(
        address,
        handler=async_handler,
        group_name="workers",
        auto_ack=True,
    )
    await consumer.stop()
```

### TypeScript

```typescript
import { Mq9Client, Priority } from "mq9";

const client = new Mq9Client("nats://localhost:4222");
await client.connect();

await client.agentRegister({
  name: "agent.translator",
  mailbox: "agent.translator",
  payload: "Multilingual translation; EN/ZH/JA/KO",
});

const agents = await client.agentDiscover({ semantic: "translate Chinese to English", limit: 5 });

const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
await client.send(address, { task: "analyze" }, { priority: Priority.URGENT });
```

### Go

```go
client, _ := mq9.Connect("nats://localhost:4222")
defer client.Close()

client.AgentRegister(ctx, mq9.AgentInfo{
    Name:    "agent.translator",
    Mailbox: "agent.translator",
    Payload: "Multilingual translation; EN/ZH/JA/KO",
})

agents, _ := client.AgentDiscover(ctx, mq9.DiscoverOptions{Semantic: "translate Chinese to English", Limit: 5})

address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{Priority: mq9.PriorityUrgent})
```

---

## Protocol

10 commands over NATS request/reply under `$mq9.AI.*`:

| Category | Subject | Description |
| -------- | ------- | ----------- |
| Registry | `$mq9.AI.AGENT.REGISTER` | Register Agent with capability description |
| Registry | `$mq9.AI.AGENT.DISCOVER` | Full-text + semantic vector search |
| Registry | `$mq9.AI.AGENT.REPORT` | Heartbeat / status update |
| Registry | `$mq9.AI.AGENT.UNREGISTER` | Unregister at shutdown |
| Mailbox  | `$mq9.AI.MAILBOX.CREATE` | Create persistent mailbox with TTL |
| Messaging | `$mq9.AI.MSG.SEND.{addr}` | Send message (priority via `mq9-priority` header) |
| Messaging | `$mq9.AI.MSG.FETCH.{addr}` | Pull messages; stateful or stateless |
| Messaging | `$mq9.AI.MSG.ACK.{addr}` | Advance consumer group offset |
| Messaging | `$mq9.AI.MSG.QUERY.{addr}` | Inspect mailbox without affecting offset |
| Messaging | `$mq9.AI.MSG.DELETE.{addr}.{id}` | Delete a specific message |

Message headers: `mq9-priority` (critical/urgent/normal), `mq9-key` (dedup), `mq9-delay`, `mq9-ttl`, `mq9-tags`.

Any NATS client works — no SDK required. Full spec: [protocol.md](./protocol.md).

---

## LangChain / LangGraph

`langchain-mq9` wraps all mq9 operations as LangChain tools:

```bash
pip install langchain-mq9
```

```python
from langchain_mq9 import Mq9Toolkit
from langgraph.prebuilt import create_react_agent

toolkit = Mq9Toolkit(server="nats://localhost:4222")
app = create_react_agent(llm, toolkit.get_tools())
```

8 tools: `agent_register`, `agent_discover`, `create_mailbox`, `send_message`, `fetch_messages`, `ack_messages`, `query_messages`, `delete_message`.

---

## Key Scenarios

| Scenario | Pattern |
| -------- | ------- |
| Capability-based routing | DISCOVER by intent → SEND to found Agent |
| Sub-Agent result delivery | Private reply mailbox + `reply_to` field |
| Multi-worker task queue | Shared `group_name` — each task to exactly one worker |
| Cloud-to-edge | Messages persist during outage; FETCHed in priority order on reconnect |
| Human-in-the-loop | Humans use the same protocol as Agents — no webhooks |
| Async request-reply | A sends with `reply_to`; B replies when ready; A FETCHes |

---

## Repository Structure

```
mq9/
  python/         — Python SDK (pip install mq9)
  javascript/     — TypeScript/JavaScript SDK (npm install mq9)
  java/           — Java SDK (io.mq9:mq9)
  go/             — Go SDK (github.com/robustmq/mq9/go)
  rust/           — Rust SDK (cargo add mq9)
  langchain-mq9/  — LangChain / LangGraph toolkit
  demo/           — Ready-to-run demos (all languages)
  website/        — Documentation site (mq9.robustmq.com)
  protocol.md     — Full protocol specification
  VERSION         — Single source of truth for all SDK versions
```

---

## Demo

Ready-to-run demos in [`demo/`](./demo/):

| Demo | Description |
| ---- | ----------- |
| `message_demo` | Mailbox, send/fetch/ack, priority, key dedup, tags, delay, query, delete |
| `agent_demo` | Register, heartbeat, full-text search, semantic search, send to discovered agent |
| `langchain_demo` | LangChain + LangGraph tool usage (Python only) |

---

## Documentation

[mq9.robustmq.com](https://mq9.robustmq.com)

---

## Status

mq9 is under active development as part of [RobustMQ](https://github.com/robustmq/robustmq).
