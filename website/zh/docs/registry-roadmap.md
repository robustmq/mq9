---
title: Agent Registry — 愿景与能力路线图
description: mq9 Agent Registry 的演进方向、设计依据，以及它在 A2A 生态中的定位。从 MVP 到企业级的三个能力层级。
outline: deep
---

# Agent 注册中心 — 设想与规划

## 这解决了什么问题

Agent 之间的异步通信，前提是它们能找到彼此。没有 Registry 的消息队列，迫使每个调用方硬编码端点、自行维护地址簿、手动处理服务变更。Registry 就是消息层所依赖的地址簿。

mq9 将这两层作为一个开源系统一并提供：先找到 Agent，再可靠地与它通信。本文档聚焦于 Registry 侧——它今天能做什么、要成为生产级系统还需要什么，以及长期方向。

---

## 行业背景

Agent Registry 问题正在被多个独立方向同时推进。理解这个全景，有助于解释 mq9 所做的选择。

### 生态系统的各种方向

截至 2025 年中，已有五个值得关注的项目：

**MCP Registry** 采用中心化方式：Go 语言 REST API，GitHub OAuth 做身份认证，DNS TXT 记录做所有权验证。部署简单；单点信任。

**A2A Agent Cards** 走完全相反的路径。每个 Agent 在 `/.well-known/agent.json` 自行发布机器可读的描述符。没有中央权威机构。发现天然是联邦式的——任何爬虫或索引都可以消费它。

**AGNTCY Agent Discovery Service（ADS）** 使用 IPFS Kademlia DHT 做 P2P 路由，OCI artifacts 作为包格式，Sigstore 做供应链完整性验证。去中心化程度最高；运维复杂度也最高。

**Microsoft Entra Agent ID** 将 Agent 作为企业身份图中的一等公民。Registry 是身份管理的副产品，依赖 Azure AD。

**NANDA Index** 使用 Ed25519 签名的 `AgentAddr` 记录，采用三层设计：密码学身份、语义元数据、路由。签名模型借鉴了 DNSSEC 的思路。

### 关于 Registry 质量的研究结论

ArXiv 2508.03095 提出了四个评估维度：Security、Authentication、Scalability 和 Maintenance。它将信任框架归纳为三个支柱：Identity Assurance（你知道是谁注册了这个 Agent）、Integrity Verification（描述符未被篡改）、Privacy Preservation（发现过程不泄露内部拓扑）。

### A2A 社区对治理的讨论

Google 在 A2A Discussion #741（kthota-g，2025 年 6 月）中提出了一个正式治理模型，包含四个角色：Administrator、Catalog Manager、User 和 Viewer，以及 Agent Entitlements（目录级访问控制）、Open Discovery、Agent Search 等概念。同时引用了 W3C DCAT v3 作为候选的元数据词汇表，以实现跨系统互操作。

### Registry 的三个演进阶段

整个行业的 Registry 实现呈现出一个可识别的演进模式：

1. **静态文件** — Agent Cards 放在已知 URL，无查询能力，无生命周期管理。
2. **动态 REST API** — 中心化 Registry，支持 CRUD、搜索、TTL、认证。运维简单；需要信任运营方。
3. **去中心化密码学可验证 Registry** — 签名溯源、基于 DID 的身份、内容寻址存储。最大化去信任；运维开销显著。

今天大多数生产系统处于第二阶段。第三阶段基础设施正在涌现，但尚未成熟到可以普遍使用。

---

## mq9 的定位

mq9 并不试图解决所有 Registry 问题。明确的范围：

- 中等规模，开箱即用。不需要 Kubernetes operator 才能启动。
- A2A 兼容。mq9 必须能够从 `/.well-known/agent.json` 拉取 A2A AgentCard，并自动将这些 Agent 导入 mq9 Registry。这是进入更广泛 A2A 生态的入场券。
- Apache 许可证开源。本路线图中的所有功能均不需要企业许可证。

mq9 **不**构建的内容：

- 企业治理层（Entra 风格的身份、RBAC 层级、合规报告）。
- 去中心化身份层（DID 解析、链上溯源、IPFS 存储）。

目标是：「让 Agent 在通信之前能找到彼此，做到工业级水准」。在核心稳固之前，其他一切都在范围之外。

---

## 能力层级

路线图分为三个层级。Tier 1 是任何生产使用的前提。Tier 2 是成熟产品的要求。Tier 3 针对企业级和研究级场景。

各层级并非严格顺序执行。部分 Tier 2 工作（语义搜索）已经部分上线。排序反映优先级，而非交付时间表。

### Tier 1 — MVP

这些能力是 mq9 Registry 被推荐用于任何生产部署之前必须具备的。

#### Agent Card 数据模型

每个注册的 Agent 必须有一个结构化描述符，至少包含：

- `id` — 全局唯一标识符（UUID 或 URI）
- `name` — 人类可读名称
- `version` — semver 版本字符串
- `capability_description` — 描述 Agent 功能的自由文本
- `endpoint` — 如何访问该 Agent（URL 或 mq9 邮箱地址）
- `auth_schemes` — 支持的认证方式列表
- `metadata` — 供调用方使用的任意键值对
- `tags` — 用于分类过滤的索引标签

此 schema 与 A2A AgentCard 结构兼容，因此通过 `/.well-known/agent.json` 注册的 Agent 可以无需字段映射直接导入。

#### 生命周期操作

REGISTER、DEREGISTER、UPDATE 和版本管理。Agent 更新时，旧版本记录必须保留以便审计。按名称查询的客户端默认获取最新版本，并可以请求指定版本。

#### 多维查询

Registry 只有在能高效找到 Agent 时才有价值。必需的查询维度：

- 按名称（精确匹配和前缀匹配）
- 按能力描述（全文搜索）
- 按 tag（集合交集）
- 按 owner 或团队
- 按语义相似度（基于能力描述的 embedding 近邻搜索）

#### 心跳与自动过期

Agent 必须通过 `AGENT.REPORT` 定期发送心跳。如果在配置的 TTL 窗口内没有心跳到达，Registry 将该 Agent 标记为不可用，并从查询结果中移除。这防止了过期条目的积累，确保 DISCOVER 只返回实际运行的 Agent。

#### 基础认证

注册和查询接口必须要求认证。此层级可接受的方案：OAuth 2.0（客户端凭证流）或 API key。未认证的写操作必须被拒绝。

#### 持久化存储

Registry 状态必须在 broker 重启后保留。这是最低持久性要求。高可用（复制、故障切换）属于 Tier 2。

#### A2A 兼容性

mq9 必须能够从给定 URL 拉取 `/.well-known/agent.json`，解析 A2A AgentCard，并自动将 Agent 注册到 mq9 Registry 中。这使得 mq9 无需要求 Agent 采用新的注册协议，即可参与更广泛的 A2A 生态。

---

### Tier 2 — 成熟产品

Tier 2 能力是 mq9 被推荐用于团队级或生产关键部署所必须具备的。

#### 语义搜索

当 Agent 名称和描述与查询使用了不同词汇时，对能力描述的全文搜索就力不从心了。语义搜索使用 vector embedding（例如存储在旁挂向量索引中），允许调用方用自然语言描述需求，即使关键词重叠度很低也能获得相关结果。

此功能今天已部分上线；路线图项目是稳定 API、明确 embedding 模型要求，并确保它随 Registry 规模增长而保持扩展性。

#### 权限模型（Entitlement）

并非每个 Agent 都应该对每个调用方可见。权限模型（即 A2A Discussion #741 中描述的"Agent Entitlements"概念）定义了哪些客户端（通过其认证主体标识）可以发现和调用哪些 Agent。

此层级的模型不需要复杂：每个 Agent 一个简单的允许列表（可以发现和调用它的主体），覆盖大多数使用场景。

#### 审计日志

每次 REGISTER、DEREGISTER、UPDATE 和 DISCOVER 操作都应记录时间戳、操作主体和操作详情。对于任何需要追溯「谁在何时注册了什么」的部署，这是必要条件。

#### 生命周期管理

Agent 会经历不同状态：已注册、活跃、已废弃、已吊销。Tier 2 增加明确的状态转换，以及将 Agent 标记为 deprecated（仍可发现，但附带废弃通知）或 revoked（不可发现，不可调用）的能力。

此层级的版本管理意味着：同一 Agent 的多个版本可以在 Registry 中共存。调用方可以锁定到特定版本，也可以请求最新稳定版。

#### 联邦发现（Federation）

跨 Registry 发现：mq9 Registry 实例可以配置为将未解析的查询转发到对等 Registry。这允许团队本地 Registry 回退到组织级 Registry 来查找它自身不托管的 Agent。

此层级的 Federation 比较简单：一个静态的上游 Registry 列表，按序尝试。不需要分布式协议。

#### 高可用

Registry 在单节点故障时必须保持可用。这需要 Registry 状态的复制和 leader 选举。具体机制（Raft、主从复制等）是实现细节；可观测的要求是：无单点故障。

---

### Tier 3 — 企业级深化

Tier 3 针对大规模企业部署或高安全性环境中出现的需求。这些是长期规划项目，没有承诺的时间表。

#### 密码学完整性

Agent 描述符应由注册主体签名，以便消费方可以验证描述符在注册后未被篡改。这与 AGNTCY ADS 使用 Sigstore、NANDA Index 使用 Ed25519 的做法一致。

更长期地看：支持 W3C Verifiable Credentials（W3C VC）作为签名和溯源格式，实现与更广泛去中心化身份生态的互操作。

#### 隐私保护发现

某些部署需要选择性披露：Agent 应该对授权调用方可见，而不将其完整描述符暴露给所有人。这可能使用查询结果上的基于属性的访问控制，或用于能力证明的零知识技术。研究框架参见 ArXiv 2508.03095 的"Privacy Preservation"支柱。

#### 注册时安全扫描

Agent 注册时，可以对其 endpoint 和描述符进行扫描，检查已知漏洞模式、格式异常的 payload 或可疑元数据。这对于任何 Agent 都可以自行注册的开放 Registry 尤为重要。

#### DID 与去中心化身份

支持 Decentralized Identifiers（DID）作为 Agent 标识符，使 Agent 无需依赖 mq9 作为信任根即可证明其身份。这使 Registry 成为缓存和索引层，而非权威身份来源。

#### 跨地域联邦

Tier 2 的 Federation 是静态且本地的。Tier 3 的 Federation 跨越地理区域并提供一致性保证：任何地方的发现查询都在有界延迟内返回相同结果。

#### OpenTelemetry 集成

通过 OpenTelemetry 原生导出 Registry 操作的 trace 和 metrics，使运维人员能够将 Registry 活动与更广泛的可观测性体系关联起来。

---

## 对集成方的含义

如果你今天正在基于 mq9 构建：

- Tier 1 数据模型（Agent Card schema、REGISTER/DISCOVER/REPORT/UNREGISTER）已稳定。可以直接基于它构建。
- 语义搜索已可用，但 API 接口在 Tier 2 稳定之前可能有变化。
- A2A 兼容性（消费 `/.well-known/agent.json`）是硬性承诺——mq9 始终支持这一点。
- 权限模型尚不存在。如果今天需要发现层面的访问控制，在应用层自行实现。

Registry 和消息层共享同一个 broker。通过 Registry 发现的 Agent 通过 mq9 邮箱进行通信。不需要额外运行独立服务。
