---
outline: deep
---

# A2A Integration

## Overview

[A2A (Agent2Agent)](https://a2a-protocol.org) is an open protocol by Google for agent-to-agent communication. It defines standard types for tasks, messages, artifacts, and streaming events — so agents built with different frameworks can interoperate.

mq9 acts as the **transport layer** for A2A. Instead of running an HTTP server, each agent registers its `AgentCard` in the mq9 registry and receives tasks via its mailbox. Any A2A-compliant client can discover and send tasks to any mq9 agent — regardless of what language or framework built them.

## Language independence

Because mq9 is the shared transport, agents written in different languages work together out of the box:

- A **Python** agent (`Mq9A2AAgent`) can receive tasks from a **Go** client
- A **Java** agent can call a **Python** agent using standard A2A `SendMessageRequest`
- Any language that speaks A2A over mq9 can communicate with any other

The broker holds the mailbox and registry — it doesn't care about the language on either side.

## How it works

![A2A over mq9 flow](/diagram-a2a-flow.svg)

| Step | What happens |
| --- | --- |
| ① Agent startup | Agent calls `MAILBOX.CREATE`, then `AGENT.REGISTER` with its `AgentCard` |
| ② Client discover | Client calls `AGENT.DISCOVER` with a natural-language query; broker returns matching agents |
| ③ Send task | Client sends `SendMessageRequest` to the agent's mailbox, with a callback mailbox in the `mq9-reply-to` header |
| ④ Stream events | Agent processes the task and sends A2A events (`Task`, `working`, `artifact`, `completed`) back to the callback mailbox one by one; the last event carries `mq9-a2a-last: true` |

mq9 replaces the HTTP+SSE transport that A2A typically uses. Each streaming event is one mq9 message on the callback mailbox.

## SDKs

| Language | Package | Status |
| --- | --- | --- |
| [Python](./a2a/python) | `mq9` (built-in) | Available |
| Go | coming soon | Planned |
| Java | coming soon | Planned |
| JavaScript | coming soon | Planned |
| Rust | coming soon | Planned |
| C# | coming soon | Planned |
