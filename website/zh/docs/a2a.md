---
outline: deep
---

# A2A 集成

## 概述

[A2A（Agent2Agent）](https://a2a-protocol.org) 是 Google 发布的开放协议，专为 Agent 之间的互操作通信而设计。它定义了任务、消息、制品（Artifact）和流式事件的标准类型，让不同框架构建的 Agent 能够相互通信。

mq9 是 A2A 的**传输层**。每个 Agent 不需要运行 HTTP 服务器，只需将 `AgentCard` 注册到 mq9 注册中心，通过自己的 mailbox 接收任务。任何 A2A 兼容的客户端都可以发现并向 mq9 上的 Agent 发送任务——无论它们用哪种语言或框架构建。

## 语言无关性

mq9 是共享的传输层，不同语言构建的 Agent 天然可以互通：

- **Python** Agent（`Mq9A2AAgent`）可以接收 **Go** 客户端发来的任务
- **Java** Agent 可以用标准 A2A `SendMessageRequest` 调用 **Python** Agent
- 任何通过 mq9 实现了 A2A 的语言都可以与其他语言互通

Broker 持有 mailbox 和注册中心，它不关心两端是什么语言。

## 工作原理

![A2A over mq9 流程](/diagram-a2a-flow.svg)

| 步骤 | 说明 |
| --- | --- |
| ① Agent 启动 | Agent 调用 `MAILBOX.CREATE`，然后用 `AgentCard` 调用 `AGENT.REGISTER` |
| ② Client 发现 | Client 用自然语言查询调用 `AGENT.DISCOVER`，Broker 返回匹配的 Agent 列表 |
| ③ 发送任务 | Client 将 `SendMessageRequest` 发送到 Agent 的 mailbox，并在 `mq9-reply-to` header 中携带回调 mailbox |
| ④ 流式返回事件 | Agent 处理任务，将 A2A 事件（`Task`、`working`、`artifact`、`completed`）逐条发回回调 mailbox；最后一条事件携带 `mq9-a2a-last: true` |

mq9 替代了 A2A 通常使用的 HTTP+SSE 传输层。每个流式事件对应回调 mailbox 中的一条 mq9 消息。

## SDK 支持

| 语言 | 包 | 状态 |
| --- | --- | --- |
| [Python](./a2a/python) | `mq9`（内置） | 已支持 |
| Go | 即将推出 | 规划中 |
| Java | 即将推出 | 规划中 |
| JavaScript | 即将推出 | 规划中 |
| Rust | 即将推出 | 规划中 |
| C# | 即将推出 | 规划中 |
