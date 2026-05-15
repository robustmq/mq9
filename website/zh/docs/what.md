---
title: mq9 是什么
description: mq9 — Agent 注册中心 + 可靠异步通信，专为承载百万 Agent 而设计。
outline: deep
---

# mq9 是什么

![mq9 架构流程](/flow.svg)

mq9 是一个 broker，提供 Agent 注册、发现和可靠异步通信——专为承载百万 Agent 而设计。

## 为什么 mq9 存在

mq9 的愿景是让 Agent 之间的通信**开箱即用**。每个多 Agent 系统都会遇到同样的两个基础问题：Agent 如何找到彼此，以及 Agent 如何可靠地通信。没有标准化的基础设施，每个团队都在重复构建相同的管道。mq9 的存在，就是为了把这两个问题解决好，让开发者专注于 Agent 逻辑，而不是基础设施。

## 两个核心问题

**问题一：Agent 找不到彼此。**

Agent 不是有固定地址的静态服务。它们动态启动、专注于不同任务，在系统设计时地址未知。手工维护目录不可扩展。没有注册中心，每个 Agent 都需要被告知其他每个 Agent 的位置——这是一个随规模平方级增长的协调问题。

**问题二：Agent 无法可靠地交换消息。**

Agent 是短暂的。它们会意外下线、在任务中途重启，当另一个 Agent 试图联系时可能根本还不存在。即发即忘的传输会丢消息。Push 订阅要求双方同时在线。结果是：消息丢失、重试逻辑散落在每个 Agent 中，每个团队都在重建同样脆弱的协调胶水代码。

**mq9 在同一个 broker 中解决这两个问题。**

## mq9 如何解决

### Agent 注册与发现

Agent 启动时向 mq9 注册自己的能力描述——即 AgentCard。其他 Agent 通过关键词或自然语言意图搜索注册表来找到所需服务。

![Agent 注册与发现流程](/diagram-registry.svg)

注册表支持两种搜索模式：

| 模式 | 方式 | 适用场景 |
| ---- | --- | -------- |
| 语义 | 自然语言意图 | "找一个能总结 PDF 的 Agent" |
| 全文 | 关键词匹配 | `translator`、`billing`、`risk-check` |

**AgentCard** 是注册载荷——名称加上自由文本能力描述。mq9 同时建立关键词索引和向量索引。无需定义 schema，无需配置服务网格。

### 可靠异步通信

发现 Agent 后，通信是第二件事。mq9 给每个 Agent 一个**邮箱**——一个持久化地址，消息在此保存，直到接收方准备好拉取。

心智模型是**邮件，而不是 RPC**。你发送到一个地址，接收方在准备好时读取，双方不需要同时在线。

**FETCH + ACK 消费模型：**

![FETCH + ACK 位点追踪](/diagram-fetch-ack.svg)

当消费者离线时消息不会丢失。重连后，FETCH 从上次 ACK 处续拉。

**三级优先级：**

![三级优先级队列](/diagram-priority.svg)

同一邮箱内，高优先级消息先返回——同级内 FIFO。Agent 在离线数小时后重连，优先处理 `critical` 消息（紧急停止、中止信号），再处理普通任务分发。

## 定位

mq9 不是通用消息队列。它专为 Agent 通信而生，专注于两件事：让 Agent 可被发现，让消息可靠送达。

| | **mq9** | **etcd + Kafka** | **NATS JetStream** | **Google A2A** |
| --- | --- | --- | --- | --- |
| Agent 注册 | 内置，语义 + 关键词搜索 | etcd 是键值存储，无语义搜索 | 无原生注册 | 仅 Agent 发现，无消息传输 |
| 异步通信 | FETCH+ACK，离线投递，优先级 | Kafka 负责消息；无原生 Agent 注册 | Streams + 持久消费者；无 Agent 注册 | 无传输层 |
| 优先级投递 | 三级（critical / urgent / normal） | 无原生消息优先级 | 无原生优先级 | N/A |
| 离线投递 | 是——先存储，重连后 FETCH | 是（Kafka） | 是 | 否 |
| 部署 | 单 broker，一次部署 | 两套独立系统运维 | 单服务，但无注册中心 | 仅协议，无 broker |
| Agent 生命周期 | TTL 自动过期 | 手动清理 | 手动清理 | N/A |

**vs. A2A（Agent-to-Agent 协议）** — A2A 定义 Agent 在应用层如何协商任务。mq9 在传输层处理可靠投递和发现。两者互补——A2A 工作流可以在 mq9 之上运行。

**mq9 不是：**
- HTTP/gRPC 在常驻服务之间的替代品
- 数据管道或事件日志
- 编排框架——它负责移动消息和启用发现，而非做决策

## 核心概念

### AgentCard

Agent 的注册记录，包含 Agent 的名称和自由文本能力描述。mq9 同时建立关键词和语义向量索引。Agent 无需事先知道对方地址即可通过 AgentCard 相互发现。

### REGISTER / DISCOVER

`AGENT.REGISTER` — 将 AgentCard 发布到注册表。启动时调用；定期发送 `AGENT.REPORT` 心跳以表明 Agent 仍在线。

`AGENT.DISCOVER` — 按关键词或语义查询搜索注册表。返回匹配 Agent 的名称和邮箱地址列表。

### 邮箱（Mailbox）

命名的持久化消息存储，按需创建，带 TTL。`mail_address` 是投递地址。知道它的人都可以发送或拉取——不可猜测性是安全边界。

`ttl: 0` — 邮箱永不过期。TTL 创建后不可更改。

### FETCH + ACK

带位点追踪的拉取消费。`group_name` 启用有状态消费——broker 记录哪些消息已被确认。省略 `group_name` 则进行无状态的一次性读取。

### 三级优先级

消息通过 `mq9-priority` header 标记为 `critical`、`urgent` 或 `normal`。FETCH 按优先级顺序返回。同级内按 FIFO 投递。

## 核心能力

| 能力 | 详情 |
| --- | --- |
| Agent 注册 | 携带能力描述注册；全文 + 语义向量双索引 |
| Agent 发现 | 全文（`text`）或语义（`semantic`）搜索 |
| Agent 心跳 | `AGENT.REPORT` 保持注册表实时有效 |
| 持久邮箱 | 消息在服务端存储直到被消费；TTL 自动销毁 |
| Pull + ACK 消费 | 带服务端位点追踪的有状态消费组；断点续拉 |
| 三级优先级 | `critical` > `urgent` > `normal`；存储层强制执行 |
| 消息去重 | `mq9-key`：同一 key 只保留最新一条 |
| 延迟投递 | `mq9-delay`：N 秒后消息才可见 |
| 消息级 TTL | `mq9-ttl`：消息独立于邮箱 TTL 过期 |
| 标签过滤 | `mq9-tags`：通过 QUERY 按逗号分隔标签过滤 |
| N-to-N 拓扑 | 共享邮箱支持 fan-in、fan-out 和竞争消费者模式 |

## 设计原则

**注册与通信是一个系统，而非两个。** 注册表告诉你 Agent 在哪里，邮箱确保消息到达它们。将这两件事拆分成独立系统会产生两个集成面、两种故障模式和两套运维平面。mq9 将它们统一在一起。

**Pull 优于 Push。** Agent 控制自己的消费速率。准备好时 FETCH，从上次 ACK 处续拉。不需要保持长连接。

**地址即权限边界。** `mail_address` 是唯一凭证——无需 token、无需 ACL、无需认证层。不可猜测性是安全模型。

**协议中立的传输。** 任何 NATS 客户端就是 mq9 客户端——Go、Python、Rust、JavaScript、Java。不需要专有 SDK。

**单节点够用，按需扩展。** 单实例处理数百万并发 Agent 连接。需要时集群模式可用——API 不变。

## 协议总览

所有命令在 `$mq9.AI.*` 下使用 NATS request/reply。

| 类别 | Subject | 说明 |
| --- | --- | --- |
| Agent 注册 | `$mq9.AI.AGENT.REGISTER` | 注册 Agent |
| Agent 注册 | `$mq9.AI.AGENT.UNREGISTER` | 注销 Agent |
| Agent 注册 | `$mq9.AI.AGENT.REPORT` | Agent 心跳 / 状态 |
| Agent 注册 | `$mq9.AI.AGENT.DISCOVER` | 按关键词或语义搜索 Agent |
| 邮箱 | `$mq9.AI.MAILBOX.CREATE` | 创建邮箱（可选名称和 TTL）|
| 消息 | `$mq9.AI.MSG.SEND.{mail_address}` | 发送消息 |
| 消息 | `$mq9.AI.MSG.FETCH.{mail_address}` | 拉取消息 |
| 消息 | `$mq9.AI.MSG.ACK.{mail_address}` | 推进消费组位点 |
| 消息 | `$mq9.AI.MSG.QUERY.{mail_address}` | 检查邮箱（不影响位点） |
| 消息 | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}` | 删除指定消息 |

*协议参考见[给 Agent](/zh/docs/for-agent)，集成代码见[给工程师](/zh/docs/for-engineer)。*
