# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

This repo contains two things:

1. **mq9 documentation website** — a VitePress static site deployed to [mq9.robustmq.com](https://mq9.robustmq.com)
2. **Multi-language SDKs** — Python, Java, Go, Rust, JavaScript client SDKs for the mq9 protocol

mq9 is a message broker built specifically for Agent-to-Agent async communication. It is the fifth native protocol in [RobustMQ](https://github.com/robustmq/robustmq), alongside MQTT, Kafka, NATS, and AMQP. The core idea: every Agent gets a mailbox; sender and receiver do not need to be online at the same time.

The broker implementation lives in the RobustMQ repo. This repo owns the docs site and all language SDKs.

## Commands

```bash
npm install          # install deps
npm run docs:dev     # local dev server with hot reload
npm run docs:build   # build to docs/.vitepress/dist
npm run docs:preview # preview the built site locally
```

## Deploy

Push to `main` → GitHub Actions (`.github/workflows/deploy.yml`) builds and deploys to GitHub Pages automatically. No manual steps.

## Site structure

| File | Purpose |
|------|---------|
| `docs/index.md` | Home page (renders `<Home />` Vue component) |
| `docs/what.md` | What mq9 is and why it exists |
| `docs/for-agent.md` | How AI Agents use mq9 (audience: LLMs/Agents) |
| `docs/for-engineer.md` | Integration guide (audience: developers) |
| `docs/.vitepress/config.mts` | Site config, nav, SEO, analytics |
| `docs/.vitepress/theme/` | Custom theme: `Home.vue`, `Layout.vue`, `custom.css` |

The nav has four pages: Home, What, For Agent, For Engineer. No sidebar.

## Protocol (what the docs describe)

The broker exposes 10 commands over NATS request/reply under `$mq9.AI.*`:

- `MAILBOX.CREATE` — create a mailbox with optional name and TTL
- `MSG.SEND.{mail_address}` — send a message; supports headers for priority, delay, TTL, dedup key, tags
- `MSG.FETCH.{mail_address}` — pull messages; stateful (group_name) or stateless
- `MSG.ACK.{mail_address}` — advance consumer group offset
- `MSG.QUERY.{mail_address}` — inspect mailbox without affecting offset
- `MSG.DELETE.{mail_address}.{msg_id}` — delete a specific message
- `AGENT.REGISTER` / `AGENT.UNREGISTER` / `AGENT.REPORT` / `AGENT.DISCOVER` — Agent registry

The full protocol spec lives at `/Users/oker/robustmq/docs/en/mq9/Protocol.md`.

## SDK (separate repo)

The Python SDK (`mq9` on PyPI) is being developed in `robustmq-sdk`. Key design decisions already settled:

- Main class: `Mq9Client`
- `mailbox_create(*, name, ttl) -> str` returns mail_address directly
- `consume()` returns a `Consumer` object with `await consumer.stop()`; loops automatically with retry on handler error + `error_handler` callback
- `Priority` enum: `NORMAL / URGENT / CRITICAL`
- Agent methods (`agent_register`, `agent_unregister`, `agent_report`, `agent_discover`) are on `Mq9Client` directly; `agent_card` is a plain dict (caller uses a2a python sdk to build it)
