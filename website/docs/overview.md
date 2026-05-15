# mq9 Overview

## What is mq9

mq9 is a broker for AI Agent networks — it provides Agent registration, discovery, and reliable asynchronous messaging, designed to scale from a handful of Agents to millions.

---

## Two Foundational Problems

### Problem 1: Agents cannot find each other

As Agent networks grow, hardcoding endpoints and addresses becomes unmanageable. An orchestrator that needs to delegate a translation task should not need to know in advance which agent handles it or where it lives. Agents need a place to publish their capabilities and a way to be found dynamically — by keyword, or by semantic intent.

Without a registry, every multi-Agent system builds its own directory service. The results are incompatible, un-searchable, and operationally brittle.

### Problem 2: Agents are not always online at the same time

Agents are task-driven — they start, execute, and stop. When Agent A sends a result to Agent B and B is offline, the message is lost unless someone builds persistence around it. Current workarounds:

- **Redis pub/sub**: No persistence — messages are gone if the recipient is offline
- **Kafka**: Topic creation and maintenance overhead; not designed for ephemeral agents
- **Homegrown queues**: Every team rebuilds the same thing; Agent implementations are incompatible

These are all workarounds. Offline delivery should be guaranteed by the infrastructure, not worked around by each team.

---

## What mq9 Provides

### 1. Agent Registry and Discovery

Every Agent that joins the network can register itself with a capability description. Other Agents — or orchestrators — discover registered Agents using two search modes:

- **Full-text search**: keyword matching against registered capability descriptions
- **Semantic vector search**: natural language intent matching, returns the most capable agent for the job even without exact keyword overlap

A registered Agent sends periodic heartbeats via `AGENT.REPORT`. When an Agent shuts down, it calls `AGENT.UNREGISTER` to remove itself from discovery results. The registry always reflects the live network.

### 2. Reliable Async Messaging

Every mailbox is an isolated, persistent communication address. Senders write messages; recipients actively pull when they are ready. Messages are stored until explicitly consumed and acknowledged — the sender and receiver do not need to be online at the same time.

Pull + ACK means consumers process at their own pace. Consumer group offsets are tracked server-side: if a consumer restarts, the next FETCH resumes from the last ACK position with no duplicate delivery.

---

## Key Capabilities

| Capability | Details |
| --- | --- |
| Agent registration | Register with a capability description; full-text and semantic vector indexed |
| Agent discovery | Full-text (`text`) or semantic (`semantic`) search; pagination supported |
| Agent heartbeat | `AGENT.REPORT` keeps registry current; unresponsive agents are visible |
| Persistent mailboxes | Messages stored server-side until consumed; TTL-based auto-destruction |
| Pull + ACK consumption | Stateful consumer groups with server-side offset tracking; resume-from-offset |
| Three-tier priority | `critical` > `urgent` > `normal`; enforced by storage layer |
| Key deduplication | `mq9-key`: only the latest message per key is retained |
| Delayed delivery | `mq9-delay`: message becomes visible after N seconds |
| Per-message TTL | `mq9-ttl`: message expires independently of mailbox TTL |
| Tag filtering | `mq9-tags`: filter messages by comma-separated tags via QUERY |
| N-to-N topologies | Shared mailboxes support fan-in, fan-out, and competing consumer patterns |

---

## Protocol at a Glance

All commands use NATS request/reply under `$mq9.AI.*`. The broker always returns a response.

| Category | Subject | Description |
| --- | --- | --- |
| Agent registry | `$mq9.AI.AGENT.REGISTER` | Register an Agent |
| Agent registry | `$mq9.AI.AGENT.UNREGISTER` | Unregister an Agent |
| Agent registry | `$mq9.AI.AGENT.REPORT` | Agent heartbeat / status |
| Agent registry | `$mq9.AI.AGENT.DISCOVER` | Search Agents by keyword or semantic intent |
| Mailbox | `$mq9.AI.MAILBOX.CREATE` | Create a mailbox with optional name and TTL |
| Messaging | `$mq9.AI.MSG.SEND.{mail_address}` | Send a message |
| Messaging | `$mq9.AI.MSG.FETCH.{mail_address}` | Pull messages |
| Messaging | `$mq9.AI.MSG.ACK.{mail_address}` | Advance consumer group offset |
| Messaging | `$mq9.AI.MSG.QUERY.{mail_address}` | Inspect mailbox without affecting offset |
| Messaging | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}` | Delete a specific message |

---

## Where to Go Next

| Destination | What you will find |
| --- | --- |
| [Quick Start](./quick-start) | Run all core operations against the demo server in under 10 minutes using the NATS CLI |
| [Features](./features) | Detailed reference for Agent registry, messaging consumption model, priority, and message attributes |
| [Scenarios](./scenarios) | Eight concrete Agent communication patterns with working code examples |
| [Protocol](./protocol) | Full subject reference, request/response fields, and error codes |
