---
title: System Architecture
description: mq9 system architecture — SDK layer, single-binary broker cluster, and pluggable storage.
outline: deep
---

# System Architecture

mq9 is composed of two parts: a **multi-language SDK** that agents and engineers use directly, and a **Broker** that handles all registry, messaging, and routing logic.

![mq9 system architecture](/diagram-architecture.svg)

---

## SDK Layer

The SDK is the only surface agents and services interact with. It wraps the NATS-based protocol into typed, language-idiomatic APIs — agents never send raw NATS requests directly.

Six official SDKs are provided:

| Language | Package | Install |
| -------- | ------- | ------- |
| Python | `mq9` | `pip install mq9` |
| JavaScript / TypeScript | `mq9` | `npm install mq9` |
| Go | `github.com/robustmq/mq9/go` | `go get github.com/robustmq/mq9/go` |
| Rust | `mq9` | `cargo add mq9` |
| Java | `io.mq9:mq9` | Maven / Gradle |
| C# | `mq9` | `dotnet add package mq9` |

All six SDKs expose an identical API surface. Adding a new protocol operation means updating all six simultaneously — there is no per-language divergence.

**Transport:** Every SDK communicates with the broker using the NATS protocol over `$mq9.AI.*` subjects. Any environment that can open a TCP connection to port 4222 can connect.

---

## Broker

The broker is a **single binary** with no external runtime dependencies. It handles three concerns:

### Protocol and routing

Receives all SDK requests over NATS, routes them to the correct internal handler: registry operations (`AGENT.REGISTER`, `AGENT.DISCOVER`, etc.) or messaging operations (`MSG.SEND`, `MSG.FETCH`, `MSG.ACK`, etc.).

### Agent Registry

Maintains the AgentCard index. Supports both full-text keyword search and semantic vector search over capability descriptions. TTL-based auto-expiry removes stale registrations.

### Reliable Async Messaging

Manages persistent mailboxes. Stores messages server-side, applies priority ordering (`critical > urgent > normal`), tracks consumer group offsets, and enforces message-level and mailbox-level TTLs.

---

## Cluster Mode

A single broker node handles millions of concurrent agent connections. When throughput or availability requirements grow, the broker scales horizontally.

![mq9 cluster topology](/diagram-cluster.svg)

Key properties of the cluster:

- **All nodes are active** — there is no primary/standby split. Agents can connect to any node.
- **Consistent routing** — the Meta Service (Raft-based) handles cluster membership, placement decisions, and leader election.
- **Transparent scale-out** — add a new broker node and it joins the cluster live. No downtime, no reconnection required from the SDK side.
- **Unchanged API** — the SDK connection string points to the cluster (or a load balancer in front). The API is identical whether there is one node or twenty.

### When to scale

| Scenario | Approach |
| -------- | -------- |
| Development / testing | Single node (`docker run robustmq/robustmq`) |
| Production, moderate load | Single node with persistent volume |
| High throughput / HA requirement | 3+ node cluster behind a load balancer |
| Data sovereignty / multi-region | Separate deployments per region; federation (roadmap) |

---

## Storage

The broker's storage layer is pluggable:

| Backend | Use case |
| ------- | -------- |
| Memory | Development, testing — no persistence |
| RocksDB | Production — durable, low-latency local storage |
| S3 Tiering | Cold archive for high-volume deployments (roadmap) |

Storage is decoupled from compute. In cluster mode, storage can scale independently of the broker nodes.

---

## Deployment

### Single node (development)

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

### Single node (production)

```bash
docker run -d \
  --name mq9 \
  -p 4222:4222 \
  -p 9090:9090 \
  -v /data/mq9:/data \
  --restart unless-stopped \
  robustmq/robustmq:latest
```

- Port `4222` — mq9/NATS protocol (SDK connections)
- Port `9090` — Prometheus metrics

### Cluster deployment

Refer to the [RobustMQ cluster deployment guide](https://robustmq.com) for multi-node configuration. The SDK `server` parameter accepts a comma-separated list of node addresses or a load balancer URL — no code change is required when moving from single-node to cluster.
