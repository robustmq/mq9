---
title: Mailbox Naming Conventions
description: Recommended naming conventions for mq9 mailbox addresses — structure, types, multi-tenancy, and A2A mapping.
outline: deep
---

# Mailbox Naming Conventions

This document defines the recommended naming conventions for mailbox addresses in mq9. A mailbox address is mq9's core addressing primitive for reliable asynchronous communication between agents.

These conventions are recommendations, not protocol-level requirements. mq9 SDKs follow these conventions by default, and we encourage the broader A2A ecosystem to adopt them for interoperability.

## Motivation

In mq9, every reliable asynchronous communication flows through a mailbox. The relationship between agents and mailboxes is many-to-many:

- An agent may own multiple mailboxes (one per capability, one per task, one per tenant context, etc.)
- A mailbox may be served by multiple agents (worker pools, primary-replica setups, broadcast groups)

Without a shared naming convention, every team invents its own scheme, leading to fragmentation across the agent ecosystem. A consistent convention provides:

- **Discoverability** — developers reading a mailbox address can infer its purpose without consulting documentation
- **Interoperability** — agents from different teams or organizations can collaborate without negotiating naming schemes
- **Tooling** — monitoring, audit, and management tools can rely on structural patterns
- **Migration** — agents can move between mq9 deployments without renaming infrastructure

## Basic structure

A mailbox address consists of segments separated by dots (`.`):

```
{namespace}.{type}.{identifier}[.{sub-identifier}]
```

- `namespace` — optional tenant or organizational prefix
- `type` — well-known mailbox type (`agent`, `task`, `pool`, `group`, `session`)
- `identifier` — the primary identifier (agent name, task id, capability, etc.)
- `sub-identifier` — optional further qualification (capability, version, channel, etc.)

Examples:

```
agent.translator                         # default mailbox for agent named "translator"
agent.translator.en2zh                   # capability-specific mailbox
task.7d3f-a1b2-c3d4                      # mailbox for a specific long-running task
pool.translators                         # worker pool for translator agents
group.alerts                             # broadcast group
acme.agent.translator                    # tenant-scoped mailbox
```

## Character set and length

**Allowed characters per segment:**

- Lowercase letters: `a-z`
- Digits: `0-9`
- Hyphens: `-`

Segments are separated by dots (`.`). The following characters are reserved and must not appear in any segment:

| Character | Reserved for |
| --------- | ------------ |
| `.` | Segment separator |
| `*` | Single-segment wildcard (subscriptions only) |
| `>` | Multi-segment wildcard (subscriptions only) |
| `$` | Reserved namespace prefix |

**Length limits:**

- Each segment: 1–64 characters
- Total address: up to 256 characters
- Minimum: 2 segments

## Reserved namespaces

The following top-level prefixes are reserved and must not be used by application code:

| Prefix | Reserved for |
| ------ | ------------ |
| `$mq9.*` | mq9 system mailboxes (broker control, internal coordination) |
| `$a2a.*` | A2A protocol-specific mailboxes |
| `$mcp.*` | MCP protocol-specific mailboxes |

Reserved namespaces start with `$` to make them visually distinct from application-level names.

## Standard mailbox types

### agent.* — Agent-scoped mailboxes

Used for messages directed to a specific agent.

```
agent.{agent-name}                       # default inbox
agent.{agent-name}.{capability}          # capability-specific inbox
agent.{agent-name}.v{version}            # version-specific inbox
agent.{agent-name}.{capability}.v{version}
```

Examples:

```
agent.translator                         # default
agent.translator.en2zh                   # English to Chinese
agent.translator.zh2en                   # Chinese to English
agent.code-reviewer.python               # reviews Python code
agent.code-reviewer.v2                   # version 2
agent.translator.en2zh.v3               # capability + version
```

The `{agent-name}` should match the agent's `name` field in its AgentCard. This allows direct mapping from agent identity to mailbox address.

### task.* — Task-scoped mailboxes

Used for long-running task coordination. Task mailboxes are typically temporary and cleaned up when the task completes.

```
task.{task-id}                           # task primary inbox
task.{task-id}.req                       # incoming requests
task.{task-id}.resp                      # outgoing responses
task.{task-id}.events                    # lifecycle events (submitted, working, completed)
```

Examples:

```
task.7d3f-a1b2-c3d4
task.7d3f-a1b2-c3d4.req
task.7d3f-a1b2-c3d4.resp
task.7d3f-a1b2-c3d4.events
```

Task IDs should be globally unique. UUIDs or A2A-style task identifiers are recommended.

### pool.* — Worker pool mailboxes

Used when multiple agent instances share the same capability. mq9 delivers each message to exactly one consumer in the pool.

```
pool.{capability}                        # pool by capability
pool.{pool-name}                         # named pool
```

Examples:

```
pool.translate-en2zh                     # all en2zh translators share the load
pool.code-reviewers
pool.urgent-handlers
```

Agents register themselves to a pool by subscribing to the same mailbox address.

### group.* — Broadcast group mailboxes

Each message published to a group mailbox is delivered to all subscribers.

```
group.{group-name}
group.{group-name}.{channel}             # sub-channel within the group
```

Examples:

```
group.workers                            # broadcast to all worker agents
group.alerts
group.alerts.security                    # security-specific sub-channel
group.config-updates
```

### session.* — Session-scoped mailboxes

Used for stateful multi-turn conversations between agents.

```
session.{session-id}
session.{session-id}.history             # full message history for replay
```

Examples:

```
session.abc-123-def-456
session.abc-123-def-456.history
```

Session IDs should be globally unique. Sessions are created at the start of a multi-turn interaction and torn down when the conversation completes.

## Multi-tenant addressing

Tenant prefixes provide isolation when multiple organizations share the same broker:

```
{tenant-id}.{standard-mailbox-address}
```

Examples:

```
acme.agent.translator                    # ACME's translator
beta.agent.translator                    # Beta's translator (same name, isolated)
acme.task.7d3f-a1b2
team.eng.pool.deployers
```

Mailboxes in different tenant namespaces are isolated by access control rules at the broker level.

## Mapping from A2A AgentCard

mq9 recommends mapping A2A AgentCard fields directly to mailbox addresses:

| AgentCard field | Mailbox address |
| --------------- | --------------- |
| `name` | `agent.{name}` |
| `name` + `skills[].id` | `agent.{name}.{skill-id}` |
| `name` + `version` | `agent.{name}.v{version}` |
| `name` + `skills[].id` + `version` | `agent.{name}.{skill-id}.v{version}` |

Given this AgentCard:

```json
{
  "name": "translator",
  "version": "2.0",
  "skills": [
    { "id": "en2zh", "name": "English to Chinese" },
    { "id": "zh2en", "name": "Chinese to English" }
  ]
}
```

The recommended mailbox addresses are:

```
agent.translator
agent.translator.v2
agent.translator.en2zh
agent.translator.zh2en
agent.translator.en2zh.v2
agent.translator.zh2en.v2
```

mq9 SDK automatically generates these addresses when an agent registers with an AgentCard.

## Wildcards in subscriptions

mq9 supports two wildcard characters in subscription patterns:

| Wildcard | Matches | Example |
| -------- | ------- | ------- |
| `*` | Exactly one segment | `agent.translator.*` — all capabilities of translator |
| `>` | One or more trailing segments (end only) | `agent.translator.>` — everything under translator |

More examples:

```
agent.*.en2zh                            # all agents with en2zh capability
task.7d3f-a1b2-c3d4.>                    # all channels of a specific task
group.alerts.>                           # all alert sub-channels
```

Wildcards are valid in subscription patterns only — not when publishing messages.

## Examples in context

### Agent-to-agent call

```python
# Client sends to the translator's capability-specific mailbox
client.send("agent.translator.en2zh", {"text": "Hello world"})

# Translator fetches from the same address
messages = await agent.fetch("agent.translator.en2zh", group_name="workers")
```

### Worker pool for load distribution

```python
# Three instances all subscribe to the same pool address
# mq9 delivers each message to exactly one of them
agent_1.subscribe("pool.translators")
agent_2.subscribe("pool.translators")
agent_3.subscribe("pool.translators")

client.send("pool.translators", {"text": "Hello world"})
```

### Long-running task with status updates

```python
task_id = "doc-analysis-7d3f"

# Client submits work and subscribes to events
client.send(f"task.{task_id}.req", {"document": doc_content})
client.subscribe(f"task.{task_id}.events")

# Agent publishes progress
agent.publish(f"task.{task_id}.events", {"status": "working"})
agent.publish(f"task.{task_id}.resp",   {"result": analysis})
agent.publish(f"task.{task_id}.events", {"status": "completed"})
```

### Broadcast notification

```python
# All workers subscribe; all receive each message
worker_1.subscribe("group.alerts")
worker_2.subscribe("group.alerts")

monitor.publish("group.alerts", {"severity": "high", "message": "..."})
```

### Multi-tenant deployment

```python
# ACME and Beta run the same agent type on the same broker, isolated by prefix
acme_agent.subscribe("acme.agent.translator")
beta_agent.subscribe("beta.agent.translator")

acme_client.send("acme.agent.translator", message)
beta_client.send("beta.agent.translator", message)
```

## Compatibility

**NATS** — mq9 mailbox addresses are valid NATS subjects. mq9 deployments can interoperate with NATS clients at the transport layer.

**A2A** — These conventions are designed to be A2A-friendly. AgentCards published by A2A-compliant agents map directly to mq9 mailbox addresses. The conventions do not modify the A2A protocol; they define how A2A agents are reachable within an mq9 deployment.

**Other protocols** — The conventions reserve namespaces for MCP (`$mcp.*`) and other emerging agent protocols. Mapping guidance will be published as these protocols mature.
