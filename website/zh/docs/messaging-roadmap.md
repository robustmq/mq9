---
title: 可靠异步消息 — 设计理念与能力路线图
description: mq9 如何从消息基础设施演进为专为 Agent 设计的通信层 —— 重新定义的抽象、能力分层与长期目标。
outline: deep
---

# 可靠异步通信 — 设想与规划

## 为什么"Agent 消息"不只是消息

消息中间件已经存在了几十年。工程基础 —— 持久化、可靠投递、高吞吐、低延迟、高可用、集群 —— 都已经是成熟领域。mq9 不否认这个基础；它建立在这个基础之上。但 mq9 的差异化优势不是基础本身，而是基础之上的那层抽象。

传统 broker 的每一个抽象，都是为"消息的单位是字节流、服务几乎总是在线"的世界设计的。Agent 工作负载同时打破了这些假设。

| 传统 broker | mq9 |
|---|---|
| topic / queue | mailbox（每个 Agent 独占，1:1 绑定） |
| topic 名称路由 | Agent 地址 / 能力路由 |
| 短小、即发即忘的消息 | 长时任务（分钟到小时级） |
| Consumer 偶尔离线 | Agent 频繁离线 —— 这是设计预期，不是故障 |
| pub/sub 拓扑 | N-to-N Agent 协作与会话 |
| 不透明字节流 | 结构化任务（A2A Message with Parts） |
| client_id（无意义字符串） | AgentCard（身份 + 已声明能力） |

这张表不是营销对比，而是设计约束。每一行都代表一个地方：如果复用传统 broker，开发者就不得不绕过抽象而不是利用抽象。

mq9 的核心判断：从一开始就为 Agent 场景设计正确的抽象，让工程基础回归其本来的角色 —— 地基，而不是天花板。

### Registry 与 Messaging 是同一个概念

在传统 broker 中，客户端身份是偶然的。`client_id` 是连接管理的句柄，不是一等实体。mq9 将 Agent 视为一等实体：一个 Agent 有一张 AgentCard，声明其名称、能力和元数据。Registry 管理 Agent 的存在；mailbox 管理 Agent 的通信。它们是同一个概念的两个侧面，而不是两个独立系统的拼接。

这种统一性使得意图路由成为可能：发送方描述它需要做什么，broker 将这个意图与已注册 Agent 的声明能力进行匹配 —— 发送方无需知道也无需关心由哪个具体 Agent 处理任务。

## 已经构建的能力

当前版本覆盖了可靠离线投递和结构化消费所需的核心消息原语。

### 持久化 Mailbox

每个 Agent 拥有一个带可配置 TTL 的 mailbox。消息在 broker 上持久化存储。消息到达时 Agent 无需在线 —— Agent 重连后执行 FETCH 即可获取。这是支撑"设计上允许离线"工作负载的基础性保证。

### 三级优先级

消息携带三个优先级之一：`CRITICAL`、`URGENT` 或 `NORMAL`。同一优先级内按 FIFO 投递，高优先级优先处理。发送方无需对方检查消息内容，就能通过优先级传递紧迫性信号。

### Pull 消费与服务端 Offset 追踪

mq9 使用 pull 模型（FETCH + ACK），broker 端追踪 consumer group offset。Agent 拉取一批消息、处理、ACK 推进 offset。如果 Agent 在处理过程中崩溃，未 ACK 的消息会在下次 FETCH 时重新投递。这是 resume-from-offset —— 状态由 broker 持有，而不是客户端。

### 每条消息的属性头

每条消息携带结构化元数据 header：

- `mq9-key` —— 去重键；broker 在消息进入 mailbox 之前丢弃重复消息
- `mq9-tags` —— 过滤标签；接收方可以只 FETCH 匹配特定 tag 集合的消息
- `mq9-delay` —— 延迟投递；消息被 broker 持有，直到发送时间偏移量到期
- `mq9-ttl` —— 独立于 mailbox TTL 的单条消息 TTL；过期消息静默丢弃

### N-to-N 拓扑

共享 mailbox 天然支持 fan-in（多发送方、单接收方）、fan-out（单发送方、多个竞争消费者拉取同一 mailbox）和广播模式。这些不是特殊模式 —— 它们自然地从 mailbox + consumer group 模型中涌现出来。

## 能力路线图

路线图分为三个层级。Tier 1 是当前工程重点。Tier 2 和 Tier 3 代表方向性承诺，而非具体发布时间表。

### Tier 1 — 夯实基础

#### 六种语言 SDK 全面对齐

Python SDK 已完成。Go、JavaScript、Java、Rust 和 C# 已完成脚手架搭建。Tier 1 的工作是将所有六个 SDK 推进至功能对齐：覆盖全部 10 条协议命令、符合各语言习惯的异步 API、带重试的 consume loop，以及各生态系统的包发布。

SDK 对齐是其他所有事情的前提 —— 无论多么高级的能力，如果开发者无法用自己的语言调用，都毫无意义。

#### 长任务生命周期追踪

当前消息机制覆盖发送和接收。缺少的是两者之间的任务状态机。一个长时运行的 Agent 任务应当暴露离散状态：`submitted → working → input-required → completed`（以及 `failed`）。这些状态需要在 broker 上追踪，以便：

- 调用方 Agent 无需轮询消息就能查询任务状态
- 崩溃的 Agent 在重连后可以携带状态快照从中断处恢复任务，而不丢失进度
- 编排 Agent 可以向人类展示任务状态，而无需检查消息内容

这个特性使 mq9 适用于运行时间长达分钟乃至小时的任务，而不仅仅是毫秒级场景。

#### 有状态会话支持

一个任务往往包含多个轮次：编排者发送任务，Worker 询问澄清问题，编排者回答，Worker 完成任务。目前每条消息都是独立的。Tier 1 在 broker 层面引入 `correlation_id` 追踪：一个 session 将相关消息分组，broker 维护 session 历史，Agent 可以获取 session 视图而不是无序的 mailbox 视图。

这使多轮 Agent 交换成为一等原语，而不是每个开发者都要按惯例重新实现的东西。

#### 关键任务的 Exactly-Once 投递

At-least-once 投递（当前的保证）对幂等任务已经足够。关键的非幂等任务 —— 支付、资源配置、不可逆状态变更 —— 需要 exactly-once 语义。Tier 1 引入可选的 exactly-once 投递模式，基于 broker 端去重结合协作式 ACK 隔离实现。

#### Dead Letter 处理

超出重试预算的消息目前会阻塞 consumer group。Tier 1 为每个 mailbox 增加可配置的 dead-letter mailbox：超过最大重试次数的消息自动移入其中，携带原始 header 和失败原因。Dead-letter mailbox 本身是一个普通的 mq9 mailbox —— 可以用完全相同的原语进行消费、监控和告警。

### Tier 2 — 语义路由与访问控制

#### 意图路由

目前发送方必须知道接收方的 `mail_address`。Tier 2 引入意图路由：发送方描述需要做什么（以结构化的能力请求形式），broker 将该意图与已注册 AgentCard 的能力声明进行向量匹配，选择最匹配的可用 Agent 并路由消息。

这将发送方逻辑与接收方身份解耦 —— 发送方无需知道哪个具体 Agent 会处理任务，只需描述任务类型。

#### 每个 Mailbox 的访问控制

目前，知道 mailbox 地址就足以向其发送消息。Tier 2 增加权限层：每个 mailbox 的显式 send/receive 授权，绑定到已认证身份。凭证模型在 broker 层面支持 OAuth Bearer token、API key 和 mTLS —— 无需应用层强制执行。

#### 授权模型

Mailbox 级别的访问控制需要一个更高层次的模型：哪些客户端在什么条件下被允许向哪些 mailbox 发送消息。授权模型将此形式化为一个 broker 在发送时评估的策略，在消息持久化之前完成检查。

#### 内容策略引擎

某些部署需要对消息内容执行规则 —— 阻止包含不允许数据类型、违反合规要求或尝试 prompt injection 的消息。内容策略引擎在投递前对消息内容进行语义评估（而非仅做结构检查）。违反策略的消息在 broker 边界被拒绝，返回结构化错误，永远不会到达接收方 Agent。

#### 审计日志

每个 send、fetch、ACK 和 delete 事件都可以记录到审计流。审计流可通过同一 RobustMQ 实例上的 Kafka 协议消费 —— 无需额外 pipeline。这满足了企业合规需求，而不增加基础设施复杂度。

### Tier 3 — 长期能力

#### 上下文感知

目前 Agent 负责在每条消息中重新传输相关上下文。这是浪费的：broker 已经见过 session 中的每条消息。Tier 3 引入 broker 端上下文追踪：对于有活跃 session 的 Agent 对，broker 维护压缩的对话历史，并在投递前用相关历史上下文丰富传入消息。Agent 不再重传完整上下文；broker 来管理它。

#### 隐私保护消息

Agent 间消息可能携带敏感数据。Tier 3 为特定 Agent 对增加端到端加密：消息由发送方 Agent 运行时加密，仅目标接收方可解密。Broker 存储和路由密文 —— 永远不接触明文。这支持 broker 运营方与 Agent 运营方属于不同信任域的部署场景。

#### 跨集群消息路由

单个 mq9 集群拥有单一地址空间。Tier 3 引入联邦机制：消息可寻址到远端 mq9 节点上的 Agent。Broker 解析目标集群，跨联邦边界路由消息，并像本地投递一样完成交付。这使多地域和多租户部署无需应用层路由逻辑。

#### OpenTelemetry 集成

消息流的完整可观测性：每个 send 和 deliver 操作都发射兼容 OpenTelemetry 的 span。分布式 trace 跨越发送方 Agent → broker → 接收方 Agent。这使得在任何标准可观测性后端中诊断延迟、追踪任务失败、理解多 Agent 工作流的完整执行图成为可能。

## Kubernetes 类比

Kafka 之于 Agent 消息，犹如 OpenStack 之于容器编排：一个强大的通用系统，可以被改造来工作，但它不是为目标工作负载设计的。每一个 Agent 特定模式 —— 离线投递、长任务状态、能力路由、每 Agent 身份 —— 都需要在上面叠加自定义应用层逻辑。

mq9 之于 Kafka，犹如 Kubernetes 之于 OpenStack：不是被改造的通用工具，而是从零开始为目标工作负载设计的专用工具。每一个抽象都针对 Agent 场景优化。工程基础（持久化、吞吐、高可用）属于同一类问题；上层抽象则完全不同。

如果这个判断是正确的，mq9 的天花板与 Kubernetes 到达的天花板相同：成为其目标工作负载的事实标准基础设施层。每一个 Agent 框架、每一个多 Agent 系统、每一个企业 AI 部署最终都需要一个消息层。mq9 的赌注是：正确的抽象，如果足够早地建立，会随时间复利积累。
