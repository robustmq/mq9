---
outline: deep
title: mq9 概述
---

# mq9 概述

## mq9 是什么

mq9 是一个专为 AI Agent 规模化设计的 Broker，提供 **Agent 注册与发现**和**可靠异步消息**两项核心能力，是 RobustMQ 的第五个原生协议，与 MQTT、Kafka、NATS、AMQP 共享同一套统一存储架构。

一句话定义：mq9 让每个 Agent 既能被发现，又能可靠地收发消息——无论对方是否在线。

---

## 两个核心问题

**问题一：Agent 怎么找到彼此？**

多 Agent 系统中，Agent 动态上下线，能力各异。没有中心化目录，也不想手工维护地址表——需要一个机制让 Agent 发布自己的能力、让其他 Agent 按意图找到它。

**问题二：Agent 消息怎么不丢？**

Agent 不是服务器，随时启动、执行、消亡。Agent A 给 Agent B 发消息，B 不在线，消息就丢了。HTTP 同步调用要求双方同时在线，不适合 Agent 场景。需要一种"发出去就保证到达"的异步通信机制，无论对方何时上线。

mq9 直接解决这两个问题。

---

## mq9 提供什么

### 1. Agent 注册与发现

每个 Agent 启动时向 mq9 注册自身，携带能力描述（自然语言文本或结构化 AgentCard）。其他 Agent 通过全文检索或语义向量检索找到合适的 Agent，获取其 `mail_address` 后直接发消息。

- Agent 自主注册、注销，生命周期由自身控制
- DISCOVER 支持关键词全文检索和自然语言语义检索
- REPORT 心跳上报，感知 Agent 存活状态
- 注册内容同时建立全文索引和向量索引，一次注册，两种查找

### 2. 可靠异步消息

每个 Agent 可以创建一个或多个邮箱（MAILBOX），邮箱地址 `mail_address` 是通信标识。发送方将消息写入邮箱，接收方主动 FETCH 拉取，无论发送时对方是否在线，消息都已落存储、不会丢失。

- Pull + ACK 消费模型，断点续拉，不重复消费
- 三级优先级（critical / urgent / normal），紧急消息优先出队
- 消息属性：key 去重、delay 延迟投递、消息级 TTL、tags 过滤标签
- 邮箱 TTL 自动销毁，无需手动清理

---

## 核心能力一览

| 能力 | 说明 |
|------|------|
| AGENT.REGISTER | 注册 Agent，携带能力描述（文本或 AgentCard JSON） |
| AGENT.UNREGISTER | 注销 Agent |
| AGENT.REPORT | 心跳/状态上报，感知存活 |
| AGENT.DISCOVER | 按关键词全文检索或自然语言语义检索 Agent |
| MAILBOX.CREATE | 创建邮箱，声明名称和 TTL 生命周期 |
| MSG.SEND | 发送消息，支持优先级、key 去重、delay、tags、消息级 TTL |
| MSG.FETCH | Pull 模式拉取消息，有状态（group_name）或无状态 |
| MSG.ACK | 推进消费组位点，支持断点续拉 |
| MSG.QUERY | 按 key/tags/since 查询消息，不影响消费位点 |
| MSG.DELETE | 删除指定消息 |

**三级优先级：**

| 级别 | Header 值 | 典型场景 |
|------|----------|---------|
| `critical`（最高） | `mq9-priority: critical` | 中止信号、紧急指令、安全事件 |
| `urgent`（紧急） | `mq9-priority: urgent` | 审批请求、时效性通知 |
| `normal`（默认） | 不填 | 任务分发、结果返回、常规通信 |

---

## 定位

mq9 不是通用消息队列，不与 Kafka 或 MQTT 竞争。它专门针对 AI Agent 这一场景做了两件事：让 Agent 能被发现，让消息能可靠异步送达。

HTTP 和 A2A 协议解决同步调用——调用方必须等待，对方必须在线。mq9 解决异步通信——发出去，对方何时在线何时处理，消息不会丢。两者互补，不竞争。

mq9 构建在 NATS 协议之上，NATS 是传输层。Broker 由 RobustMQ 用 Rust 完全自研实现，存储、优先级调度、TTL 管理、消费位点、Agent 注册表全部是 RobustMQ 自身能力。选择 NATS 协议的原因务实：NATS 覆盖 40+ 语言官方和社区客户端，Python、Go、JavaScript、Rust 均有成熟实现，mq9 从第一天起对所有这些语言开箱即用。

今天一个系统可能有几十个 Agent，未来可能几百万个。mq9 的设计起点就是这个规模：邮箱按需创建、TTL 自动销毁、Broker 水平扩展，从第一个 Agent 到百万 Agent，接口不变，运维模型不变。

---

## 下一步

| 目标 | 链接 |
|------|------|
| 5 分钟体验注册、发现、消息全流程 | [快速开始](./quick-start) |
| 了解各功能的完整参数和行为细节 | [功能特性](./features) |
| 查看完整协议 Subject 参考 | [协议设计](./protocol) |
| 典型 Agent 场景的代码示例 | [应用场景](./scenarios) |
| 用 Python SDK 接入 | [SDK 文档](./sdk/) |
