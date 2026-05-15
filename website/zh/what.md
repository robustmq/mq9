---
title: mq9 是什么
description: mq9 — 提供 Agent 注册、发现和可靠异步消息的 broker，专为承载百万 Agent 而设计。
---

# mq9 是什么

mq9 是一个 broker，提供 Agent 注册、发现和可靠异步消息，专为承载百万 Agent 而设计。

它是 [RobustMQ](https://github.com/robustmq/robustmq) 的第五个原生协议，与 MQTT、Kafka、NATS、AMQP 并列，共享同一套统一存储架构。

## 任何多 Agent 系统都会遇到的两个问题

**问题一：Agent 之间如何找到彼此？**

你构建了一个翻译 Agent、一个摘要 Agent、一个审核 Agent。当 Orchestrator 需要翻译时，它怎么知道该找谁？硬编码地址不可扩展，人工维护注册表是负担，服务发现系统不理解 Agent 语义。

**问题二：Agent 之间如何可靠地通信？**

Agent 不是服务——它们为任务而启动，完成后消失，随时上下线。当 Agent A 给 Agent B 发消息，而 B 不在线时，消息就丢了。HTTP 要求双方同时在线；Redis pub/sub 无持久化；Kafka 需要提前创建 Topic，不适合临时 Agent。

mq9 在同一个 broker 中解决这两个问题。

## mq9 如何解决

### 第一件事：Agent 注册与发现

每个 Agent 启动时向 mq9 注册自己的 **AgentCard**——名称、邮箱地址、能力描述。注册内容同时建立全文索引和向量索引。

其他 Agent 通过 DISCOVER 找到它——支持关键词搜索和自然语言语义搜索，无需提前知道对方地址。

```bash
# Agent 启动时注册
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; EN/ZH/JA/KO"
}'

# 任意 Agent 语义搜索发现
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "translate Chinese to English",
  "limit": 5
}'
# → [{"name":"agent.translator","mailbox":"agent.translator","payload":"..."}]
```

### 第二件事：可靠异步通信

每个 Agent 拥有一个**邮箱**——带 TTL 的持久化地址。发送方向 `mail_address` 发消息，接收方准备好时 FETCH 拉取。双方不需要同时在线。

消费模型是 Pull + ACK：客户端主动 FETCH，处理完 ACK 推进位点，下次从断点续拉。重启或断线不丢消息，不重复消费。

三级优先级 `critical → urgent → normal`，FETCH 返回时高优先级消息先出队。

```bash
# 发送 critical 优先级消息（接收方离线也没关系）
nats request '$mq9.AI.MSG.SEND.agent.translator' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# 接收方上线后 FETCH，高优先级先出
nats request '$mq9.AI.MSG.FETCH.agent.translator' '{
  "group_name": "worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'

# ACK 推进位点
nats request '$mq9.AI.MSG.ACK.agent.translator' '{
  "group_name": "worker",
  "mail_address": "agent.translator",
  "msg_id": 5
}'
```

## 核心概念

**AgentCard** — Agent 的注册记录，包含 name、mailbox 地址、能力描述（payload）。注册时同时建立全文索引和向量索引，支持关键词和语义两种检索方式。

**REGISTER / DISCOVER** — 注册发现协议。REGISTER 写入 AgentCard；DISCOVER 按文本或自然语言语义返回匹配的 Agent 列表。

**邮箱（Mailbox）** — 带 TTL 的持久化消息地址。`mail_address` 是唯一凭证，知道它就能发送或拉取。TTL 到期后连同所有消息自动销毁，无需手动清理。

**FETCH + ACK** — 有状态拉取消费。FETCH 按优先级顺序返回消息；ACK 推进消费组位点；下次 FETCH 从断点续拉。传 `group_name` 时 broker 记录位点；不传时每次独立拉取。

**三级优先级** — `critical → urgent → normal`，通过 NATS header `mq9-priority` 指定。同级别内 FIFO。

**消息属性** — 所有属性通过 NATS header 传递，无需修改消息体：

| Header | 作用 |
|--------|------|
| `mq9-priority: critical\|urgent` | 消息优先级，不填默认 normal |
| `mq9-key: {key}` | 同 key 只保留最新一条（去重压实） |
| `mq9-tags: tag1,tag2` | 标签，可通过 QUERY 过滤 |
| `mq9-delay: {seconds}` | 延迟投递，N 秒后消息才可见 |
| `mq9-ttl: {seconds}` | 消息级 TTL，独立于邮箱 TTL |

## 与现有工具的对比

| | etcd + Kafka | NATS JetStream | Google A2A | mq9 |
|---|---|---|---|---|
| Agent 注册发现 | 需自行实现 | ✗ | ✓ | ✓ |
| 语义搜索发现 | ✗ | ✗ | 有限 | ✓ |
| 离线投递 | ✓ | ✓ | ✗ | ✓ |
| 按需邮箱（无预建 Topic） | ✗ | ✗ | ✗ | ✓ |
| 优先级队列 | ✗ | 有限 | ✗ | ✓ |
| 为 Agent 设计 | ✗ | ✗ | ✓ | ✓ |
| 组件数量 | 2+ 套系统 | 1 | 仅发现 | 1 |
| 协议依赖 | 多套 | NATS | HTTP | NATS |

**与 etcd + Kafka 的关系：** 这是常见的自搭方案——etcd 做服务发现，Kafka 做消息队列。两套系统意味着两套运维、两套 SDK、两套故障模式。mq9 把两件事合并在同一个 broker 里。

**与 NATS JetStream 的关系：** mq9 基于 NATS 协议，但 JetStream 是通用流存储，不理解 Agent 语义。mq9 在 NATS 之上增加了邮箱生命周期管理、优先级队列、Agent 注册发现，以及专为 Agent 场景设计的协议层。

**与 Google A2A 的关系：** A2A 是 Agent 能力发现和任务协议，定义 Agent 如何描述自己和协商任务。mq9 是传输层——解决消息如何在 Agent 间可靠传递的问题。两者互补，不竞争。

## 设计原则

**注册是一等公民。** Agent 注册不是事后加的功能，而是 broker 的核心能力。全文索引 + 向量索引同时建立，关键词搜索和语义搜索都是原生支持。

**邮箱是临时的。** Agent 按需申请邮箱，TTL 到期自动销毁。不需要注销，不留垃圾数据。适配 Agent 短暂存在的本质。

**Pull 优于 Push。** Agent 控制自己的消费速率，随时 FETCH，从上次 ACK 的位点续拉。不需要保持长连接。

**地址即权限。** `mail_address` 是唯一凭证，无需额外认证层。

**协议无关。** 任何 NATS 客户端直接就是 mq9 客户端——Go、Python、Rust、JavaScript、Java。不需要专用 SDK。

## 与 RobustMQ 的关系

mq9 是 RobustMQ 的第五个原生协议层，与 MQTT、Kafka、NATS、AMQP 并列，共享同一套统一存储架构。

部署一个 RobustMQ 实例，五个协议全部就位。Agent 通信基础设施不需要单独维护一套系统。
