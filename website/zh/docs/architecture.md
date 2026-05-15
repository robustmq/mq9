---
title: 系统架构
description: mq9 系统架构——SDK 层、单二进制 Broker 集群与可插拔存储。
outline: deep
---

# 系统架构

mq9 由两部分组成：**多语言 SDK**（Agent 和工程师直接使用）与 **Broker**（负责注册中心、消息存储和路由的所有逻辑）。

![mq9 系统架构](/diagram-architecture.svg)

---

## SDK 层

SDK 是 Agent 和服务与 mq9 交互的唯一接口。它将基于 NATS 的协议封装为类型化、符合各语言习惯的 API——Agent 无需直接发送原始 NATS 请求。

官方提供六种语言 SDK：

| 语言 | 包名 | 安装 |
| ---- | ---- | ---- |
| Python | `mq9` | `pip install mq9` |
| JavaScript / TypeScript | `mq9` | `npm install mq9` |
| Go | `github.com/robustmq/mq9/go` | `go get github.com/robustmq/mq9/go` |
| Rust | `mq9` | `cargo add mq9` |
| Java | `io.mq9:mq9` | Maven / Gradle |
| C# | `mq9` | `dotnet add package mq9` |

六种语言暴露完全相同的 API 接口。新增协议操作时，六种语言同步更新，不存在语言间的接口差异。

**传输层：** 所有 SDK 均通过 NATS 协议在 `$mq9.AI.*` Subject 上与 Broker 通信。任何能够建立到 4222 端口 TCP 连接的环境都可以接入。

---

## Broker

Broker 是一个**单一二进制**，无需任何外部运行时依赖。它处理三个核心职责：

### 协议与路由

接收所有 SDK 请求（通过 NATS），路由到对应的内部处理器：注册中心操作（`AGENT.REGISTER`、`AGENT.DISCOVER` 等）或消息操作（`MSG.SEND`、`MSG.FETCH`、`MSG.ACK` 等）。

### Agent 注册中心

维护 AgentCard 索引。支持对能力描述的全文关键词搜索和语义向量搜索。基于 TTL 的自动过期机制会清除失活的注册记录。

### 可靠异步通信

管理持久化邮箱。将消息存储在服务端，按优先级排序（`critical > urgent > normal`），追踪消费组位点，并执行消息级和邮箱级 TTL。

---

## 集群模式

单个 Broker 节点可承载数百万并发 Agent 连接。当吞吐量或可用性要求提高时，Broker 可水平扩展。

![mq9 集群拓扑](/diagram-cluster.svg)

集群的核心特性：

- **所有节点均为活跃节点** — 无主备之分。Agent 可以连接任意节点。
- **一致性路由** — 元服务（基于 Raft）负责集群成员管理、数据放置决策和 Leader 选举。
- **无感知水平扩容** — 新增 Broker 节点后立即加入集群，无需停机，SDK 侧无需重连。
- **API 不变** — SDK 的连接地址指向集群（或其前置负载均衡器）。无论是单节点还是二十节点，API 完全相同。

### 何时扩容

| 场景 | 方案 |
| ---- | ---- |
| 开发 / 测试 | 单节点（`docker run robustmq/robustmq`） |
| 生产环境，中等负载 | 单节点 + 持久化存储卷 |
| 高吞吐 / 高可用要求 | 3+ 节点集群 + 负载均衡器 |
| 数据主权 / 多地域 | 各地域独立部署；联邦发现（路线图） |

---

## 存储

Broker 的存储层可插拔：

| 后端 | 适用场景 |
| ---- | -------- |
| Memory | 开发、测试——无持久化 |
| RocksDB | 生产环境——持久化、低延迟本地存储 |
| S3 分层 | 大规模部署的冷数据归档（路线图） |

存储与计算解耦。在集群模式下，存储层可独立于 Broker 节点进行扩容。

---

## 部署

### 单节点（开发环境）

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

### 单节点（生产环境）

```bash
docker run -d \
  --name mq9 \
  -p 4222:4222 \
  -p 9090:9090 \
  -v /data/mq9:/data \
  --restart unless-stopped \
  robustmq/robustmq:latest
```

- 端口 `4222` — mq9/NATS 协议（SDK 连接）
- 端口 `9090` — Prometheus 指标

### 集群部署

多节点配置请参考 [RobustMQ 集群部署指南](https://robustmq.com)。SDK 的 `server` 参数接受逗号分隔的节点地址列表或负载均衡器地址——从单节点迁移到集群无需修改任何代码。
