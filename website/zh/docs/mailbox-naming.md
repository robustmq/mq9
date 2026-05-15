---
title: 邮箱命名规范
description: mq9 邮箱地址的推荐命名规范——结构、类型、多租户与 A2A 映射。
outline: deep
---

# 邮箱命名规范

本文档定义 mq9 邮箱地址的推荐命名规范。邮箱地址是 mq9 在 Agent 之间进行可靠异步通信的核心寻址原语。

这些约定是推荐规范，不是协议层的强制要求。mq9 SDK 默认遵守这些约定，我们鼓励更广泛的 A2A 生态系统采用它们以实现互操作性。

## 为什么需要命名规范

在 mq9 中，所有可靠的异步通信都通过邮箱流转。Agent 与邮箱的关系是多对多的：

- 一个 Agent 可以拥有多个邮箱（按能力、按任务、按租户上下文等）
- 一个邮箱可以由多个 Agent 服务（Worker 池、主从架构、广播组）

没有统一的命名约定，每个团队各自发明命名方案，导致 Agent 生态碎片化。统一的约定带来：

- **可读性** — 开发者看到邮箱地址就能推断其用途，无需查阅文档
- **互操作性** — 不同团队或组织的 Agent 无需协商命名方案即可协作
- **工具支持** — 监控、审计和管理工具可以依赖结构化模式
- **可迁移性** — Agent 在不同 mq9 部署之间迁移时无需重命名基础设施

## 基本结构

邮箱地址由点（`.`）分隔的段组成：

```
{namespace}.{type}.{identifier}[.{sub-identifier}]
```

- `namespace` — 可选的租户或组织前缀
- `type` — 标准邮箱类型（`agent`、`task`、`pool`、`group`、`session`）
- `identifier` — 主标识符（Agent 名称、任务 ID、能力标识等）
- `sub-identifier` — 可选的进一步限定（能力、版本、子通道等）

示例：

```
agent.translator                         # 名为 "translator" 的 Agent 的默认邮箱
agent.translator.en2zh                   # 特定能力邮箱
task.7d3f-a1b2-c3d4                      # 特定长任务的邮箱
pool.translators                         # 翻译 Agent 的 Worker 池
group.alerts                             # 广播组
acme.agent.translator                    # 租户隔离邮箱
```

## 字符集与长度

**每段允许的字符：**

- 小写字母：`a-z`
- 数字：`0-9`
- 连字符：`-`

段之间用点（`.`）分隔。以下字符保留，不得出现在任何段中：

| 字符 | 保留用途 |
| ---- | -------- |
| `.` | 段分隔符 |
| `*` | 单段通配符（仅用于订阅） |
| `>` | 多段通配符（仅用于订阅） |
| `$` | 保留命名空间前缀 |

**长度限制：**

- 每段：1–64 个字符
- 总地址长度：最多 256 个字符
- 最少 2 段

## 保留命名空间

以下顶级前缀保留，应用代码不得使用：

| 前缀 | 保留用途 |
| ---- | -------- |
| `$mq9.*` | mq9 系统邮箱（broker 控制、内部协调） |
| `$a2a.*` | A2A 协议专用邮箱 |
| `$mcp.*` | MCP 协议专用邮箱 |

保留命名空间以 `$` 开头，与应用级名称视觉上明显区分。

## 标准邮箱类型

### agent.* — Agent 级邮箱

用于发送给特定 Agent 的消息。

```
agent.{agent-name}                       # 默认收件箱
agent.{agent-name}.{capability}          # 特定能力收件箱
agent.{agent-name}.v{version}            # 特定版本收件箱
agent.{agent-name}.{capability}.v{version}
```

示例：

```
agent.translator                         # 默认
agent.translator.en2zh                   # 英文翻中文
agent.translator.zh2en                   # 中文翻英文
agent.code-reviewer.python               # 审查 Python 代码
agent.code-reviewer.v2                   # 版本 2
agent.translator.en2zh.v3               # 能力 + 版本
```

`{agent-name}` 应与 Agent 的 AgentCard 中的 `name` 字段一致，便于从 Agent 身份直接映射到邮箱地址。

### task.* — 任务级邮箱

用于长任务协调。任务邮箱通常是临时的，任务完成后清理。

```
task.{task-id}                           # 任务主收件箱
task.{task-id}.req                       # 入站请求
task.{task-id}.resp                      # 出站响应
task.{task-id}.events                    # 生命周期事件（submitted / working / completed）
```

示例：

```
task.7d3f-a1b2-c3d4
task.7d3f-a1b2-c3d4.req
task.7d3f-a1b2-c3d4.resp
task.7d3f-a1b2-c3d4.events
```

任务 ID 应全局唯一，推荐使用 UUID 或 A2A 风格的任务标识符。

### pool.* — Worker 池邮箱

用于多个 Agent 实例共享同一能力的场景。mq9 将每条消息精确投递给池中的一个消费者。

```
pool.{capability}                        # 按能力命名的池
pool.{pool-name}                         # 命名池
```

示例：

```
pool.translate-en2zh                     # 所有英中翻译 Agent 共担负载
pool.code-reviewers
pool.urgent-handlers
```

Agent 通过订阅相同的邮箱地址来加入池。

### group.* — 广播组邮箱

发布到广播组邮箱的每条消息都会投递给所有订阅者。

```
group.{group-name}
group.{group-name}.{channel}             # 组内子通道
```

示例：

```
group.workers                            # 广播给所有 Worker Agent
group.alerts
group.alerts.security                    # 安全告警子通道
group.config-updates
```

### session.* — 会话级邮箱

用于 Agent 之间有状态的多轮对话。

```
session.{session-id}
session.{session-id}.history             # 完整消息历史（用于回放）
```

示例：

```
session.abc-123-def-456
session.abc-123-def-456.history
```

会话 ID 应全局唯一。会话在多轮交互开始时创建，对话结束后销毁。

## 多租户寻址

租户前缀为多个组织共享同一 broker 时提供隔离：

```
{tenant-id}.{standard-mailbox-address}
```

示例：

```
acme.agent.translator                    # ACME 的翻译 Agent
beta.agent.translator                    # Beta 的翻译 Agent（同名，隔离）
acme.task.7d3f-a1b2
team.eng.pool.deployers
```

不同租户命名空间的邮箱通过 broker 层的访问控制规则隔离。

## 与 A2A AgentCard 的映射

mq9 推荐将 A2A AgentCard 字段直接映射为邮箱地址：

| AgentCard 字段 | 邮箱地址 |
| -------------- | -------- |
| `name` | `agent.{name}` |
| `name` + `skills[].id` | `agent.{name}.{skill-id}` |
| `name` + `version` | `agent.{name}.v{version}` |
| `name` + `skills[].id` + `version` | `agent.{name}.{skill-id}.v{version}` |

给定以下 AgentCard：

```json
{
  "name": "translator",
  "version": "2.0",
  "skills": [
    { "id": "en2zh", "name": "英文到中文" },
    { "id": "zh2en", "name": "中文到英文" }
  ]
}
```

推荐的邮箱地址为：

```
agent.translator
agent.translator.v2
agent.translator.en2zh
agent.translator.zh2en
agent.translator.en2zh.v2
agent.translator.zh2en.v2
```

mq9 SDK 在 Agent 使用 AgentCard 注册时自动生成这些地址。

## 订阅中的通配符

mq9 在订阅模式中支持两种通配符：

| 通配符 | 匹配范围 | 示例 |
| ------ | -------- | ---- |
| `*` | 精确匹配一段 | `agent.translator.*` — translator 的所有能力 |
| `>` | 匹配一段或多段（只能在末尾） | `agent.translator.>` — translator 下的所有内容 |

更多示例：

```
agent.*.en2zh                            # 所有具有 en2zh 能力的 Agent
task.7d3f-a1b2-c3d4.>                    # 特定任务的所有子通道
group.alerts.>                           # 所有告警子通道
```

通配符仅用于订阅模式，不能用于发布消息。

## 场景示例

### Agent 间调用

```python
# 客户端发送到翻译 Agent 的特定能力邮箱
client.send("agent.translator.en2zh", {"text": "Hello world"})

# 翻译 Agent 从同一地址拉取
messages = await agent.fetch("agent.translator.en2zh", group_name="workers")
```

### Worker 池负载分担

```python
# 三个实例订阅相同的池地址，mq9 每条消息只投递给其中一个
agent_1.subscribe("pool.translators")
agent_2.subscribe("pool.translators")
agent_3.subscribe("pool.translators")

client.send("pool.translators", {"text": "Hello world"})
```

### 带状态更新的长任务

```python
task_id = "doc-analysis-7d3f"

# 客户端提交任务并订阅事件
client.send(f"task.{task_id}.req", {"document": doc_content})
client.subscribe(f"task.{task_id}.events")

# Agent 发布进度
agent.publish(f"task.{task_id}.events", {"status": "working"})
agent.publish(f"task.{task_id}.resp",   {"result": analysis})
agent.publish(f"task.{task_id}.events", {"status": "completed"})
```

### 广播通知

```python
# 所有 Worker 订阅；每条消息全部收到
worker_1.subscribe("group.alerts")
worker_2.subscribe("group.alerts")

monitor.publish("group.alerts", {"severity": "high", "message": "..."})
```

### 多租户部署

```python
# ACME 和 Beta 在同一 broker 上运行同类 Agent，通过前缀隔离
acme_agent.subscribe("acme.agent.translator")
beta_agent.subscribe("beta.agent.translator")

acme_client.send("acme.agent.translator", message)
beta_client.send("beta.agent.translator", message)
```

## 兼容性

**NATS** — mq9 邮箱地址是合法的 NATS subject。mq9 部署可在传输层与 NATS 客户端互操作。

**A2A** — 这些约定为 A2A 友好设计。A2A 兼容 Agent 发布的 AgentCard 可直接映射为 mq9 邮箱地址。约定不修改 A2A 协议本身，只定义 A2A Agent 在 mq9 部署中如何被寻址。

**其他协议** — 约定为 MCP（`$mcp.*`）等新兴 Agent 协议预留了命名空间，相关映射指南将随协议成熟后发布。
