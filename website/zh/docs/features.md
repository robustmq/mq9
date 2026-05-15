---
title: 功能特性
---

# 功能特性

mq9 提供两个相互独立但协同工作的核心能力：**Agent 注册中心**负责让 Agent 被发现，**可靠异步消息**负责让消息可靠送达。两者共用同一个 Broker，通过 NATS request/reply 协议访问。

---

## 第一部分：Agent 注册中心

### AgentCard 数据模型

注册时的 `payload` 字段是 Agent 的能力描述，接受两种格式：

**纯文本描述**（最简形式）：

```
"多语言翻译 Agent，支持中英日韩互译，实时返回翻译结果"
```

**A2A AgentCard JSON**（结构化形式）：

```json
{
  "name": "agent.translator",
  "description": "多语言翻译 Agent，支持中英日韩互译，实时返回翻译结果",
  "capabilities": ["zh-en", "en-zh", "ja-zh", "ko-zh"],
  "version": "1.2.0",
  "mail_address": "agent.translator"
}
```

两种格式都会被同时建立**全文索引**和**向量索引**，支持关键词和语义两种检索方式。

---

### REGISTER — 注册 Agent

Agent 启动时调用 REGISTER，发布自身能力到注册中心：

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.code-review",
  "payload": "代码审查 Agent，支持 Rust/Go/Python，返回发现的问题列表（JSON 格式）"
}'
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | Agent 唯一标识，同时作为其默认 `mail_address` |
| `payload` | string | 能力描述，纯文本或 AgentCard JSON 字符串 |

响应：

```json
{"error": ""}
```

同名 Agent 重复注册会覆盖原有记录（幂等）。

---

### UNREGISTER — 注销 Agent

Agent 关闭时调用 UNREGISTER，从注册中心移除自身：

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name": "agent.code-review"}'
```

注销后该 Agent 不再出现在 DISCOVER 结果中。

---

### REPORT — 心跳与状态上报

Agent 定期调用 REPORT 上报心跳和运行状态，让编排者或其他 Agent 感知其存活：

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "agent.code-review",
  "report_info": "running, queue_depth: 3, processed: 128"
}'
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | Agent 标识 |
| `report_info` | string | 自由格式的状态字符串，broker 原样存储 |

**心跳健康感知建议模式：**

```
Agent 启动 → REGISTER
Agent 运行中 → 每隔 N 秒 REPORT（心跳）
其他 Agent → DISCOVER（查看在线 Agent 列表）
Agent 关闭 → UNREGISTER
```

如果 Agent 异常崩溃未能 UNREGISTER，调用方可以通过 DISCOVER 后尝试发消息、FETCH 无响应来判断 Agent 不可用。建议结合消息级 TTL 或超时机制处理此类情况。

---

### DISCOVER — 发现 Agent

DISCOVER 是注册中心的查询入口，支持三种检索方式：

**语义向量检索**（理解自然语言意图，基于向量相似度）：

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "帮我检查 Rust 代码的性能问题",
  "limit": 5
}'
```

**关键词全文检索**（精确关键词匹配）：

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "code review rust",
  "limit": 10
}'
```

**列出全部**（不传检索条件）：

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "limit": 50,
  "page": 1
}'
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `semantic` | string | 自然语言描述，触发向量语义检索 |
| `text` | string | 关键词，触发全文检索 |
| `limit` | int | 返回结果数量上限 |
| `page` | int | 分页，从 1 开始 |

检索优先级：`semantic` > `text` > 不传（列出全部）。

响应示例：

```json
{
  "error": "",
  "agents": [
    {
      "name": "agent.code-review",
      "mail_address": "agent.code-review",
      "payload": "代码审查 Agent，支持 Rust/Go/Python，返回发现的问题列表（JSON 格式）"
    }
  ]
}
```

拿到 `mail_address` 后直接向目标 Agent 发消息，无需其他配置。

---

## 第二部分：可靠异步消息

### 持久化邮箱与 TTL 生命周期

邮箱是消息的存储单元。每个邮箱在创建时声明名称和 TTL（生存时间，单位：秒）：

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{
  "name": "task.queue",
  "ttl": 86400
}'
```

响应：

```json
{"error": "", "mail_address": "task.queue"}
```

**生命周期规则：**

| 规则 | 说明 |
|------|------|
| TTL 起点 | 邮箱创建时开始计时，到期不可续期 |
| 到期行为 | 邮箱及其所有消息自动销毁，无需手动清理 |
| 永不过期 | `ttl: 0` 或省略 ttl |
| 重复创建 | 同名邮箱已存在时报错（`mailbox xxx already exists`），CREATE 不是幂等的 |

**mail_address 格式：** 小写字母、数字、点（`.`），1 到 128 字符，点不能开头/结尾，不能连续。

---

### Pull + ACK 消费模型

mq9 使用 pull 模式：客户端主动 FETCH 拉取，处理后 ACK 推进位点，下次从断点续拉。

**两种消费模式：**

| 模式 | 使用方式 | 适用场景 |
|------|---------|---------|
| 有状态消费 | 传 `group_name` | broker 记录位点，重连后续拉，适合持续运行的 Worker |
| 无状态消费 | 不传 `group_name` | 每次按 `deliver` 策略独立拉取，不记录位点，适合一次性读取或调试 |

**FETCH 请求：**

```bash
nats request '$mq9.AI.MSG.FETCH.task.queue' '{
  "group_name": "workers",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

**deliver 起点策略：**

| 值 | 说明 |
|----|------|
| `latest`（默认） | 从当前时刻起只拉新消息 |
| `earliest` | 从邮箱最早的消息开始 |
| `from_time` | 从指定 Unix 时间戳之后开始 |
| `from_id` | 从指定 msg_id 开始（含） |

有位点记录时 `deliver` 策略不生效（续拉优先）；传 `force_deliver: true` 可强制忽略位点重新开始。

**ACK 请求：**

```bash
nats request '$mq9.AI.MSG.ACK.task.queue' '{
  "group_name": "workers",
  "mail_address": "task.queue",
  "msg_id": 5
}'
```

ACK 推进到 `msg_id: 5`，下次 FETCH 从 6 开始续拉。

**消费流程：**

```
FETCH → 返回消息列表（按优先级排序）
  → 客户端处理
  → ACK（推进位点）
  → 下次 FETCH 从断点续拉
```

---

### 三级优先级

每条消息通过 `mq9-priority` header 指定优先级：

| 优先级 | Header 值 | 典型场景 |
|--------|----------|---------|
| `critical`（最高） | `mq9-priority: critical` | 中止信号、紧急指令、安全事件 |
| `urgent`（紧急） | `mq9-priority: urgent` | 审批请求、时效性通知 |
| `normal`（默认） | 不填 | 任务分发、结果返回、常规通信 |

- 同优先级内：FIFO——按发送顺序出队
- 跨优先级：critical 先于 urgent 先于 normal
- 排序由存储层保证，消费方无需自行排序
- FETCH 返回的消息列表已按优先级降序排列

```bash
# critical 消息示例
nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:critical' \
  '{"cmd":"abort","task_id":"t-007"}'
```

---

### 消息属性

发送消息时可通过 NATS header 附加以下属性：

| 属性 | Header | 说明 |
|------|--------|------|
| 去重 key | `mq9-key: {key}` | 同 key 的消息只保留最新一条，旧消息被覆盖 |
| 标签 | `mq9-tags: {tag1},{tag2}` | 逗号分隔，可通过 QUERY 的 `tags` 字段过滤 |
| 延迟投递 | `mq9-delay: {seconds}` | 消息写入后延迟指定秒数才可见，`msg_id` 返回 `-1` |
| 消息级 TTL | `mq9-ttl: {seconds}` | 消息在 `发送时间 + ttl` 后自动过期，独立于邮箱 TTL |

**去重 key 示例：** 任务进度持续上报，只关心最新状态：

```bash
# 连续上报，同 key 只保留最新一条
nats request '$mq9.AI.MSG.SEND.task.status' \
  --header 'mq9-key:job-42' \
  '{"status":"running","progress":20}'

nats request '$mq9.AI.MSG.SEND.task.status' \
  --header 'mq9-key:job-42' \
  '{"status":"running","progress":60}'

nats request '$mq9.AI.MSG.SEND.task.status' \
  --header 'mq9-key:job-42' \
  '{"status":"done","progress":100}'

# QUERY 返回 key=job-42 的最新一条
nats request '$mq9.AI.MSG.QUERY.task.status' '{"key":"job-42"}'
```

**延迟投递示例：** 30 秒后才可见：

```bash
nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-delay:30' \
  '{"cmd":"cleanup","target":"tmp-files"}'
```

---

### 离线投递保证

mq9 的核心承诺：消息写入即持久化，接收方不在线不影响消息存储。接收方何时重连，何时 FETCH，消息都在那里等待。

典型场景：

- 边缘 Agent 因网络中断离线数小时，重连后 FETCH 拿到所有待处理指令
- 子 Agent 完成任务写入结果，编排者稍后再取，不需要同时在线
- 告警消息在处理器临时下线期间持续积累，恢复后按优先级处理积压

---

### N-to-N Agent 拓扑

mq9 的邮箱模型天然支持任意通信拓扑：

| 拓扑 | 实现方式 |
|------|---------|
| 1-to-1（点对点） | Agent A 向 Agent B 的专属邮箱发消息 |
| 1-to-N（广播） | Agent A 向多个邮箱各发一条消息 |
| N-to-1（汇聚） | 多个 Agent 向同一邮箱发消息，一个消费者处理 |
| N-to-N（竞争消费） | 多个 Agent 向同一邮箱发消息，多个 Worker 用同一 `group_name` 竞争拉取 |

竞争消费中，`group_name` 相同的多个 Worker 共享位点，每条消息只被处理一次。Worker 可随时加入或退出，无需重新配置。

---

### 消息查询与删除

**QUERY** — 查看邮箱存储内容，不影响消费位点：

```bash
# 全量查询
nats request '$mq9.AI.MSG.QUERY.task.queue' '{}'

# 按标签过滤
nats request '$mq9.AI.MSG.QUERY.task.queue' '{"tags":["billing","vip"]}'

# 按时间范围 + 分页
nats request '$mq9.AI.MSG.QUERY.task.queue' '{"since":1712600000,"limit":20}'

# 按去重 key 查询最新一条
nats request '$mq9.AI.MSG.QUERY.task.queue' '{"key":"job-42"}'
```

| 参数 | 说明 |
|------|------|
| `key` | 返回该 key 的最新一条 |
| `tags` | 返回同时带有所有标签的消息 |
| `since` | 返回该 Unix 时间戳之后的消息 |
| `limit` | 最多返回 N 条 |

**DELETE** — 删除指定消息（通过 msg_id）：

```bash
nats request '$mq9.AI.MSG.DELETE.task.queue.2' '{}'
```

subject 格式：`$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}`
