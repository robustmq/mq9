---
title: mq9 路线图
description: mq9 开发路线图——注册中心、可靠通信与走向生产级 Agent 基础设施的路径。
outline: deep
---

# mq9 路线图

mq9 的注册中心与通信层均已就位。本页描述当前状态、未来方向，以及两条主要能力线的演化路径。

各阶段不严格顺序执行，优先级会根据实际使用场景和社区反馈调整。方向固定，顺序灵活。

---

## 当前状态

Agent 注册中心与可靠异步通信层均已可用。

### Agent 注册中心

- REGISTER / UNREGISTER / REPORT / DISCOVER
- 全文检索与语义向量搜索
- TTL 自动过期

### 可靠异步通信

- 带 TTL 生命周期的持久化邮箱
- 三级优先级（`critical` / `urgent` / `normal`）
- Pull + ACK 消费，服务端 offset 追踪
- 消息属性：key 去重、tags 过滤、delay 延迟投递、消息级 TTL
- 离线投递——消息等待接收方 FETCH

### SDK 与集成

- 六种语言 SDK（Python 已完整实现；Go、JavaScript、Java、Rust、C# 已搭建框架）
- `langchain-mq9` — LangChain / LangGraph 工具包
- MCP Server 支持

---

## Tier 1 — 夯实基础

在扩展能力之前，现有原语必须达到生产级。

### 注册中心

- Agent Card schema 稳定化——字段规范化、版本管理
- 心跳与健康状态持久化
- A2A AgentCard 导入——自动从 `/.well-known/agent.json` 接入 A2A 兼容 Agent

### 通信

- 六种语言 SDK 完整实现
- 有状态会话支持——多轮交互中的 correlation_id 追踪
- 长任务生命周期——broker 端维护 `submitted → working → completed` 状态，支持客户端断线重连后恢复

### 基础设施

- 集群模式稳定化与部署文档完善
- 公共节点 `demo.robustmq.com`——稳定、可观测、可用于开发测试

---

## Tier 2 — 语义路由与访问控制

### 语义路由

当前 DISCOVER 是拉取式的：发送方查询、选择目标、主动发送。下一步是意图驱动路由：发送方描述需要做什么，mq9 自动路由到最匹配的注册 Agent。

- 消息可选携带语义意图描述，而不是指定固定的 `mail_address`
- broker 将消息意图与注册 AgentCard 的能力描述进行向量匹配
- 路由在 broker 内部完成，对发送方透明

### 访问控制与授权

- 超出"地址即凭证"模型的细粒度邮箱发送/接收权限
- Entitlement 模型：哪些 client 可以使用哪些 Agent
- broker 层支持 OAuth Bearer token / API key / mTLS
- 权限管理 API

### 审计日志

- 每条消息的发送、拉取、ACK、删除事件均可记录
- 满足合规场景的可追溯要求
- 审计流可通过同一 RobustMQ 实例的 Kafka 协议消费，无需额外基础设施

---

## Tier 3 — 信任、联邦与上下文

### 信任与完整性

- AgentCard 元数据的密码学签名
- Agent 身份的 Verifiable Credentials（W3C VC）
- 防篡改审计追踪

### 联邦

- 跨注册中心发现：不同组织的 mq9 注册中心可以联邦
- 大规模部署的 registry-of-registries 模式
- Agent 地址在联邦节点间可携带

### 上下文感知（探索方向）

- broker 具备会话感知——追踪 Agent 对之间的对话历史
- Agent 不再在每条消息中重传完整上下文
- 基础设施从无状态管道进化为有状态上下文网络

---

## 能力线详细规划

- [Agent 注册中心——设想与规划](/zh/docs/registry-roadmap)
- [可靠异步通信——设想与规划](/zh/docs/messaging-roadmap)

---

## SDK 完善计划

| 语言 | 当前状态 | 目标 |
| ---- | -------- | ---- |
| Python | 已完整实现 | 完成 |
| Go | 已搭建框架 | 完整实现 |
| JavaScript | 已搭建框架 | 完整实现 |
| Java | 已搭建框架 | 完整实现 |
| Rust | 已搭建框架 | 完整实现 |
| C# | 已搭建框架 | 完整实现 |

六种语言暴露完全相同的 API 接口。新增协议操作时，六种语言同步更新。

---

## 公共基础设施

- `demo.robustmq.com` — 共享演示节点，用于开发测试。不用于生产。
- 自托管 — mq9 是 RobustMQ 的一部分，RobustMQ 是开源的。有数据主权要求的组织可以部署自己的节点，协议相同。
