---
outline: deep
title: 给 Agent — mq9 协议手册
description: mq9 为 AI Agent 解决什么问题——注册、发现、邮箱、发送、拉取、ACK、优先级、离线投递。
---

你是一个 AI Agent。以下是 mq9 为你解决的问题，以及如何使用。

## mq9 为你解决的问题

**其他 Agent 找不到你。**

你拥有能力——翻译、摘要、风险评分——但其他 Agent 不知道你的存在，也不知道如何联系你。没有注册中心，每个 Orchestrator 都要硬编码地址，你对那些从未被显式连接过的 Agent 来说是不可见的。

mq9 让你在启动时发布自己的能力。任何 Agent 都可以按关键词或自然语言意图搜索到你。你无需事先让任何人知道你的地址，就能被发现。

**你不在线时消息会丢失。**

你是短暂的。你为任务而启动，然后消失。你可能意外重启。另一个 Agent 向你发送消息时，你可能不在线——标准传输会丢消息：

- **HTTP** 要求双方同时在线。
- **Redis pub/sub** 无持久化——错过发布窗口，消息就没了。
- **NATS Core** 是即发即弃——离线时无投递保证。

mq9 给你一个**邮箱**——一个持久化地址，消息在此保存，直到你准备好拉取。数小时后重新上线，按优先级 FETCH、处理、ACK。消息不会丢失。

**你需要这两件事在同一个地方。**

注册和通信本质上是同一个问题——找到 Agent，然后联系它。mq9 在同一个 broker 中用同一套协议解决这两件事。

---

## 注册自己

启动时调用 REGISTER，用自然语言描述你的能力——mq9 同时建立关键词索引和语义向量索引。

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; supports EN/ZH/JA/KO; returns results in real time"
}'
```

定期发送心跳，保持在注册表中可见：

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "agent.translator",
  "report_info": "running, processed: 512 tasks"
}'
```

关机时注销：

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name":"agent.translator"}'
```

---

## 发现其他 Agent

无需提前知道地址，按能力找 Agent：

```bash
# 语义搜索——自然语言意图
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "find an agent that can translate Chinese text into English",
  "limit": 5
}'

# 关键词搜索
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator",
  "limit": 10
}'
```

找到匹配 Agent 的 `mailbox` 后，直接发送——即使对方现在不在线。

---

## 获取邮箱

在其他 Agent 能联系你之前，你需要一个持久化地址。

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.inbox","ttl":3600}'
# → {"error": "", "mail_address": "agent.inbox"}
```

- `mail_address` — 你的地址，分享给需要联系你的 Agent。
- `ttl` — 邮箱在 3600 秒后自动过期，连同所有消息一起销毁。
- `ttl: 0` — 邮箱永不过期。

**地址格式：** 仅小写字母、数字和点，1–128 个字符。例如：`agent.inbox`、`task.queue.v2`。

**不可猜测性是你的安全边界。** 知道你 `mail_address` 的人都可以向它发送或拉取消息。请保管好私有邮箱的地址。

---

## 发送消息

你知道另一个 Agent 的 `mail_address`，向它发送。对方可能不在线——mq9 会存储消息直到对方拉取。

```bash
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  '{"from":"sender.mailbox","type":"task","reply_to":"sender.mailbox","payload":{"task":"analyze","data":"..."}}'
```

**通过 header 设置优先级：**

```bash
# critical——中止信号、紧急命令、安全事件
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# urgent——审批请求、时间敏感通知
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-priority:urgent' \
  '{"type":"interrupt","task_id":"t-002"}'

# normal（默认，不加 header）——任务分发、结果投递
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  '{"type":"task","payload":"process dataset A"}'
```

**可选消息属性（通过 header）：**

| Header | 作用 |
| ------ | ---- |
| `mq9-key: state` | 去重——同 key 只保留最新一条 |
| `mq9-tags: a,b` | 逗号分隔标签；可通过 QUERY 过滤 |
| `mq9-delay: 60` | 延迟 60 秒投递 |
| `mq9-ttl: 300` | 消息 300 秒后过期，独立于邮箱 TTL |

**消息体字段（推荐约定，非协议强制）：**

| 字段 | 作用 |
| ---- | ---- |
| `from` | 发送方的 `mail_address` |
| `type` | 消息类型：`task`、`result`、`question`、`approval_request` |
| `correlation_id` | 将消息与其回复关联 |
| `reply_to` | 你希望对方回复的 `mail_address` |
| `payload` | 实际内容——mq9 不检查或校验消息体 |

---

## 拉取消息

mq9 使用**拉取模式**。你在准备好时主动 FETCH——不需要 push 订阅。

```bash
nats request '$mq9.AI.MSG.FETCH.agent.inbox' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

响应——按优先级排序（`critical` → `urgent` → `normal`，同级内 FIFO）：

```json
{
  "error": "",
  "messages": [
    {"msg_id": 1, "payload": "...", "priority": "critical", "create_time": 1712600001},
    {"msg_id": 3, "payload": "...", "priority": "normal",   "create_time": 1712600003}
  ]
}
```

**`group_name`** 启用有状态消费：broker 记录你的位点。ACK 后，下次 FETCH 从断点续拉，不会重复投递。省略则进行无状态的一次性读取。

**`deliver` 起始策略：**

| 值 | 说明 |
| -- | ---- |
| `latest` | 仅从此刻起的新消息 |
| `earliest` | 从邮箱中最早的消息开始 |
| `from_time` | 从某个 Unix 时间戳之后开始 |
| `from_id` | 从指定的 `msg_id` 开始 |

处理完成后 ACK 推进位点：

```bash
nats request '$mq9.AI.MSG.ACK.agent.inbox' '{
  "group_name": "my-worker",
  "mail_address": "agent.inbox",
  "msg_id": 3
}'
```

传入**批次中最后一条消息的 `msg_id`**——一次 ACK 确认整个批次。

---

## 回复消息

如果发送方设置了 `reply_to`，将结果发送到那个 `mail_address`：

```bash
nats request '$mq9.AI.MSG.SEND.sender.mailbox' '{
  "from": "agent.inbox",
  "type": "task_result",
  "correlation_id": "req-001",
  "payload": {"result": "done"}
}'
```

---

## 检查消息（不影响位点）

QUERY 返回存储的消息，**不影响消费位点**。用于调试或状态检查：

```bash
# 所有消息
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{}'

# 最新的 key 为 "status" 的消息
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"key":"status"}'

# 按时间范围
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"since":1712600000,"limit":20}'
```

---

## 删除消息

```bash
nats request '$mq9.AI.MSG.DELETE.agent.inbox.5' '{}'
```

Subject 格式：`$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}`

---

## 协议总览

| 操作 | Subject |
| ---- | ------- |
| 注册 | `$mq9.AI.AGENT.REGISTER` |
| 注销 | `$mq9.AI.AGENT.UNREGISTER` |
| 心跳 | `$mq9.AI.AGENT.REPORT` |
| 发现 Agent | `$mq9.AI.AGENT.DISCOVER` |
| 创建邮箱 | `$mq9.AI.MAILBOX.CREATE` |
| 发送消息 | `$mq9.AI.MSG.SEND.{mail_address}` |
| 拉取消息 | `$mq9.AI.MSG.FETCH.{mail_address}` |
| ACK | `$mq9.AI.MSG.ACK.{mail_address}` |
| 检查（不消费） | `$mq9.AI.MSG.QUERY.{mail_address}` |
| 删除消息 | `$mq9.AI.MSG.DELETE.{mail_address}.{msg_id}` |

*SDK 用法（Python、Go、JavaScript、Rust、Java）参见[给工程师](/zh/docs/for-engineer)。*
