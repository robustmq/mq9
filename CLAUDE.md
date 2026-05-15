# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This repo contains:

1. **mq9 documentation website** — a VitePress static site deployed to [mq9.robustmq.com](https://mq9.robustmq.com)
2. **Multi-language SDKs** — Python, Java, Go, Rust, JavaScript client SDKs for the mq9 protocol
3. **langchain-mq9** — Official LangChain/LangGraph toolkit (8 tools wrapping all mq9 operations)
4. **Demo directory** — Ready-to-run demos for all languages

mq9 is a message broker built specifically for Agent-to-Agent async communication. It is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq), alongside MQTT, Kafka, NATS, and AMQP. The core idea: every Agent gets a mailbox; sender and receiver do not need to be online at the same time.

The broker implementation lives in the RobustMQ repo. This repo owns the docs site and all language SDKs.

## Commands

```bash
npm install          # install deps
npm run docs:dev     # local dev server with hot reload
npm run docs:build   # build to website/.vitepress/dist
npm run docs:preview # preview the built site locally
```

## Deploy

Push to `main` → GitHub Actions (`.github/workflows/deploy.yml`) builds and deploys to GitHub Pages automatically. No manual steps.

## Site structure

The website lives in `website/` (not `docs/`).

| File | Purpose |
|------|---------|
| `website/index.md` | Home page (renders `<Home />` Vue component) |
| `website/what.md` | What mq9 is and why it exists |
| `website/for-agent.md` | How AI Agents use mq9 (audience: LLMs/Agents) |
| `website/for-engineer.md` | Integration guide (audience: developers) |
| `website/.vitepress/config.mts` | Site config, nav, SEO, analytics |
| `website/.vitepress/theme/` | Custom theme: `Home.vue`, `Layout.vue`, `custom.css` |

The nav has four pages: Home, What, For Agent, For Engineer. No sidebar.

`Home.vue` follows the structure of the RobustMQ mq9 homepage — Hero, Problem, Core Capabilities (3 cards with code), 8 Scenarios grid, SDK cards, RobustMQ relationship, Protocol overview, CTA. White background.

## Protocol (what the docs describe)

The broker exposes 10 commands over NATS request/reply under `$mq9.AI.*`:

- `MAILBOX.CREATE` — create a mailbox with optional name and TTL
- `MSG.SEND.{mail_address}` — send a message; supports headers for priority, delay, TTL, dedup key, tags
- `MSG.FETCH.{mail_address}` — pull messages; stateful (group_name) or stateless
- `MSG.ACK.{mail_address}` — advance consumer group offset
- `MSG.QUERY.{mail_address}` — inspect mailbox without affecting offset
- `MSG.DELETE.{mail_address}.{msg_id}` — delete a specific message
- `AGENT.REGISTER` / `AGENT.UNREGISTER` / `AGENT.REPORT` / `AGENT.DISCOVER` — Agent registry

The full protocol spec lives at `./protocol.md` (repo root) and `/Users/oker/robustmq/docs/en/mq9/Protocol.md`.

## SDK

The Python SDK (`mq9` on PyPI) is in `python/`. Key design decisions:

- Main class: `Mq9Client`
- `mailbox_create(*, name, ttl) -> str` returns mail_address directly
- `consume()` returns a `Consumer` object with `await consumer.stop()`; loops automatically with retry on handler error + `error_handler` callback
- `Priority` enum: `NORMAL / URGENT / CRITICAL`
- Agent methods (`agent_register`, `agent_unregister`, `agent_report`, `agent_discover`) are on `Mq9Client` directly

## langchain-mq9

Lives in `langchain-mq9/`. Published to PyPI as `langchain-mq9`. Depends on `mq9>=0.1.0` and `langchain-core>=0.2`.

8 tools exposed via `Mq9Toolkit(server=...).get_tools()`:

- `create_mailbox`, `send_message`, `fetch_messages`, `ack_messages`
- `query_messages`, `delete_message`, `agent_register`, `agent_discover`

All tools use FETCH+ACK model (stateful pull consumption). Works with LangChain Agents and LangGraph `create_react_agent`.

## Demo directory

`demo/` contains ready-to-run demos organized by language:

| Demo             | Description                                                                      |
| ---------------- | -------------------------------------------------------------------------------- |
| `message_demo`   | Mailbox, send/fetch/ack, priority, key dedup, tags, delay, query, delete         |
| `agent_demo`     | Register, heartbeat, full-text search, semantic search, send to discovered agent |
| `langchain_demo` | LangChain + LangGraph tool usage (Python only)                                   |

Languages: `python/`, `javascript/`, `go/`, `rust/`, `java/`.

## Release

Release is triggered by merging a PR with title starting `release:` into `main`. The `VERSION` file is the only file that needs to be changed manually — the release workflow auto-syncs the version to all SDK manifests (`python/pyproject.toml`, `langchain-mq9/pyproject.toml`, `javascript/package.json`, `rust/Cargo.toml`, `java/pom.xml`) before creating the tag and GitHub Release.

SDKs published: PyPI (mq9 + langchain-mq9), npm, crates.io, Maven Central, pkg.go.dev (Go module tag).
