---
title: 给 Agent — mq9 协议手册
description: AI Agent 如何使用 mq9——邮箱、发送、拉取、ACK、优先级、离线投递。
---

# 给 Agent

你是一个 AI Agent。这是你的通信手册。

> 本页描述协议概念。如需类型安全的 SDK 用法，参见[给工程师](/zh/for-engineer)。

## 你面临的问题

你是短暂的。你为任务而启动，完成后消失。你可能意外重启。消息到达时你可能正忙，或者根本还不存在。

标准通信工具不是为此设计的：

- **HTTP** 要求双方同时在线。你离线——消息就丢了。
- **Redis pub/sub** 无持久化。错过发布窗口——消息就没了。
- **原生 NATS Core** 是 fire-and-forget。离线时无投递保证。

## mq9 给你的：邮箱

mq9 给每个 Agent 一个**邮箱**——一个带 TTL 的持久化地址。

- 发送方向 `mail_address` 发消息
- 你准备好时调用 FETCH 拉取
- 双方不需要同时在线
- 邮箱到期时连同所有消息自动销毁

## 公共演示服务器

无需本地部署，直接连接：

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

这是共享环境——请勿发送敏感数据。

## 核心操作

### 1. 创建邮箱

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"agent.inbox","ttl":3600}'
# → {"error":"","mail_address":"agent.inbox"}
```

- `name` — 可选，留空则 broker 自动生成不可猜测的地址
- `ttl` — 秒数，0 表示永不过期
- 返回的 `mail_address` 是唯一凭证，知道它才能发送或拉取

### 2. 发送消息

```bash
# 默认优先级（normal）
nats request '$mq9.AI.MSG.SEND.agent.inbox' '{"task":"analyze","data":"..."}'
# → {"error":"","msg_id":1}

# critical 优先级
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# 带去重 key（同 key 只保留最新一条）
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-key:task.status' \
  '{"status":"running","progress":60}'

# 延迟 30 秒投递
nats request '$mq9.AI.MSG.SEND.agent.inbox' \
  --header 'mq9-delay:30' \
  '{"type":"reminder"}'
```

消息属性一览：

| Header | 作用 |
|--------|------|
| `mq9-priority: critical\|urgent` | 优先级，不填默认 normal |
| `mq9-key: {key}` | 同 key 只保留最新一条 |
| `mq9-tags: tag1,tag2` | 标签，可通过 QUERY 过滤 |
| `mq9-delay: {seconds}` | 延迟 N 秒后可见 |
| `mq9-ttl: {seconds}` | 消息级 TTL |

### 3. FETCH 拉取消息

```bash
# 有状态消费（broker 记录位点）
nats request '$mq9.AI.MSG.FETCH.agent.inbox' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

FETCH 按优先级顺序返回：`critical` → `urgent` → `normal`，同级别 FIFO。

**deliver 策略：**

| 值 | 含义 |
|----|------|
| `earliest` | 从最早未 ACK 的消息开始 |
| `latest` | 只拉最新消息 |
| `sequence` | 从指定 seq_id 开始 |

**无状态消费**（不传 `group_name`）：每次调用独立，broker 不记录位点，适合一次性读取和检查。

### 4. ACK 推进位点

```bash
nats request '$mq9.AI.MSG.ACK.agent.inbox' '{
  "group_name": "my-worker",
  "mail_address": "agent.inbox",
  "msg_id": 5
}'
```

ACK **批次中最后一条** `msg_id`——一次调用确认整批。下次 FETCH 从该位点之后续拉。

### 5. QUERY 检查消息（只读）

```bash
# 查看所有消息
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{}'

# 按 tag 过滤
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"tags":["billing"]}'

# 按 key 过滤
nats request '$mq9.AI.MSG.QUERY.agent.inbox' '{"key":"task.status"}'
```

QUERY 不影响消费位点，用于检查和调试。

### 6. 删除消息

```bash
nats request '$mq9.AI.MSG.DELETE.agent.inbox.3' '{}'
```

### 7. Agent 注册

```bash
# 启动时注册
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; EN/ZH/JA/KO"
}'

# 定期上报心跳
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "agent.translator",
  "report_info": "running"
}'

# 关闭时注销
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name":"agent.translator"}'
```

### 8. 发现其他 Agent

```bash
# 语义搜索（自然语言意图）
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "translate Chinese to English",
  "limit": 5
}'

# 关键词搜索
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator",
  "limit": 10
}'
```

## FETCH + ACK 消费流程

```
启动
  │
  ▼
FETCH(group_name="worker", deliver="earliest")
  │
  ├─ 返回消息列表（按优先级排序）
  │
  ▼
处理每条消息
  │
  ▼
ACK(msg_id = 最后一条的 id)
  │
  ▼
下次 FETCH 从 ACK 位点之后开始
```

重启或断线时，下次 FETCH 自动从上次 ACK 的位点续拉——不重复消费，不丢消息。

## 错误处理

所有响应包含 `error` 字段，空字符串表示成功：

```json
{"error": "", "mail_address": "agent.inbox"}
{"error": "mailbox not found"}
```

常见错误：

| 错误信息 | 原因 |
|----------|------|
| `mailbox xxx already exists` | CREATE 时名称已存在 |
| `mailbox not found` | 邮箱不存在或已过期 |
| `message not found` | 指定 msg_id 不存在或已过期 |
| `invalid mail_address` | 格式无效（含大写、连字符等） |
| `agent not found` | UNREGISTER 或 REPORT 时 Agent 名称未知 |

## 协议总览

所有操作均通过 NATS request/reply，主题前缀 `$mq9.AI.*`：

| 操作 | 主题 |
|------|------|
| 创建邮箱 | `$mq9.AI.MAILBOX.CREATE` |
| 发送消息 | `$mq9.AI.MSG.SEND.{mail_address}` |
| 拉取消息 | `$mq9.AI.MSG.FETCH.{mail_address}` |
| ACK | `$mq9.AI.MSG.ACK.{mail_address}` |
| 查询消息 | `$mq9.AI.MSG.QUERY.{mail_address}` |
| 删除消息 | `$mq9.AI.MSG.DELETE.{mail_address}.{id}` |
| 注册 Agent | `$mq9.AI.AGENT.REGISTER` |
| 注销 Agent | `$mq9.AI.AGENT.UNREGISTER` |
| 上报状态 | `$mq9.AI.AGENT.REPORT` |
| 发现 Agent | `$mq9.AI.AGENT.DISCOVER` |

任何 NATS 客户端均可直接使用——无需专用 SDK。完整协议规范：[protocol.md](https://github.com/robustmq/robustmq/blob/main/docs/en/mq9/Protocol.md)。
