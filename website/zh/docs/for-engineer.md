---
outline: deep
title: 给工程师 — mq9 集成指南
description: mq9 为构建多 Agent 系统的工程师解决什么问题，以及如何集成。
---

你在构建多 Agent 系统。以下是 mq9 为你解决的问题，以及如何集成。

## mq9 为你解决的问题

**你需要 Agent 之间能找到彼此，而不是硬编码地址。**

Agent 动态启动。一个新的翻译 Agent、一个风险评分 Agent、一个摘要 Agent——你的 Orchestrator 怎么知道把任务发给谁？没有注册中心，你只能硬编码地址、维护配置文件，或者自己写目录服务。每个团队都在重复这件事。

mq9 让每个 Agent 在启动时发布自己的能力。其他 Agent 按关键词或自然语言意图搜索。不需要手动管理地址。

**你需要 Agent 离线时消息也不丢失。**

Agent 是任务驱动的——启动、执行、停止。Agent A 给 Agent B 发消息，B 不在线时消息就丢了。HTTP 要求双方同时在线；Redis pub/sub 无持久化；Kafka 需要提前创建 Topic。

mq9 给每个 Agent 一个持久化邮箱。发送消息——它被存储，直到接收方拉取。接收方数小时后上线，按优先级 FETCH、ACK，然后继续。消息不会丢失。

**你需要这两件事在同一个系统里。**

用 etcd 做发现、Kafka 做消息意味着维护两套代码库、处理两种故障模式、监控两套运维平面。mq9 将 Agent 注册和持久消息统一在同一个 broker 中。

---

## 快速开始 — 公共演示服务器

无需本地部署，连接 RobustMQ 演示服务器：

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

这是共享环境——请勿发送敏感数据。

### 注册 Agent

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "mailbox": "agent.translator",
  "payload": "Multilingual translation; EN/ZH/JA/KO"
}'
```

### 按意图发现 Agent

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "translate Chinese to English",
  "limit": 5
}'
# → [{"name":"agent.translator","mailbox":"agent.translator","payload":"..."}]
```

### 创建邮箱并发送消息

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"quickstart.demo","ttl":300}'

nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'
```

### 拉取并 ACK

```bash
nats request '$mq9.AI.MSG.FETCH.quickstart.demo' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'

nats request '$mq9.AI.MSG.ACK.quickstart.demo' '{
  "group_name": "my-worker",
  "mail_address": "quickstart.demo",
  "msg_id": 3
}'
```

---

## 安装 SDK

mq9 提供多语言官方 SDK，封装了 NATS 协议调用：

```bash
pip install mq9           # Python
npm install mq9           # JavaScript / TypeScript
go get github.com/robustmq/mq9/go   # Go
cargo add mq9             # Rust
```

```xml
<!-- Java (Maven) -->
<dependency>
  <groupId>io.mq9</groupId>
  <artifactId>mq9</artifactId>
  <version>0.1.0</version>
</dependency>
```

---

## SDK 示例

### 注册与发现 Agent

```python
# Python — 启动时注册
await client.agent_register({
    "name": "agent.translator",
    "mailbox": "agent.translator",
    "payload": "Multilingual translation; EN/ZH/JA/KO",
})

# 按语义意图发现
agents = await client.agent_discover(semantic="translate Chinese to English", limit=5)

# 发送心跳
await client.agent_report({"name": "agent.translator", "report_info": "running"})

# 关机时注销
await client.agent_unregister("agent.translator")
```

```go
// Go — 注册与发现
client.AgentRegister(ctx, mq9.AgentInfo{
    Name:    "agent.translator",
    Mailbox: "agent.translator",
    Payload: "Multilingual translation; EN/ZH/JA/KO",
})
agents, _ := client.AgentDiscover(ctx, mq9.DiscoverOptions{
    Semantic: "translate Chinese to English",
    Limit:    5,
})
```

### 创建邮箱与发送消息

```python
# Python
from mq9 import Mq9Client
client = await Mq9Client.connect("nats://localhost:4222")
address = await client.mailbox_create(name="agent.inbox", ttl=3600)

msg_id = await client.send(
    "agent.inbox",
    b'{"task":"analyze","data":"..."}',
    priority=Priority.URGENT,
    key="state",    # 去重——同 key 只保留最新一条
    delay=60,       # 60 秒后投递
    ttl=300,        # 消息 300 秒后过期
    tags=["billing"],
)
```

```go
// Go
address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
    Key:      "state",
    Delay:    60,
})
```

```typescript
// TypeScript
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
await client.send(address, { task: "analyze" }, { priority: Priority.URGENT });
```

- `name = ""` — broker 自动生成地址。
- `ttl = 0` — 邮箱永不过期。

### 拉取消息（Pull + ACK）

```python
# Python — 有状态消费
messages = await client.fetch("agent.inbox", group_name="workers", deliver="earliest")
for msg in messages:
    process(msg)
    await client.ack("agent.inbox", "workers", msg.msg_id)
```

```go
// Go
messages, _ := client.Fetch(ctx, "agent.inbox", mq9.FetchOptions{
    GroupName: "workers",
    Deliver:   "earliest",
})
for _, msg := range messages {
    process(msg)
    client.Ack(ctx, "agent.inbox", "workers", msg.MsgID)
}
```

ACK **批次中最后一条消息的 `msg_id`**——一次调用确认整个批次。下次 FETCH 从此处续拉。

**无状态拉取**——省略 `group_name`。每次调用独立，不记录位点。

### 持续消费循环

```python
# Python
consumer = await client.consume(
    "agent.inbox",
    handler=async_handler,
    group_name="workers",
    auto_ack=True,
    error_handler=lambda msg, err: print(f"msg {msg.msg_id} failed: {err}"),
)
await consumer.stop()
```

```typescript
// TypeScript
const consumer = await client.consume("task.inbox", async (msg) => {
  const data = JSON.parse(new TextDecoder().decode(msg.payload));
  console.log(data);
}, {
  groupName: "workers",
  autoAck: true,
  errorHandler: async (msg, err) => console.error(`msg ${msg.msgId} failed:`, err),
});
await consumer.stop();
```

- Handler 抛出异常 → 消息不 ACK，调用 `errorHandler`，循环继续。
- `consumer.stop()` 处理完当前批次后干净退出。

---

## 常见模式

### 基于能力的路由

Orchestrator 在运行时动态发现 Agent，按意图路由任务，而不是硬编码地址。

```python
agents = await client.agent_discover(semantic="summarize PDF documents", limit=3)
if agents:
    await client.send(agents[0]["mailbox"], task_payload)
```

### 子 Agent 结果投递

父 Agent 创建私有回复邮箱并传给子 Agent。无需轮询，无需共享状态，无需配置 webhook。

```python
# 父 Agent：创建私有回复邮箱
reply_address = await client.mailbox_create(ttl=3600)

# 父 Agent：发送任务，附带 reply_to
await client.send("task.dispatch", json.dumps({
    "task": "summarize /data/corpus",
    "reply_to": reply_address,
}).encode())

# 父 Agent：随时 FETCH 结果
messages = await client.fetch(reply_address, group_name="orchestrator", deliver="earliest")
```

### 多 Worker 任务队列

多个 Worker 共享同一 `group_name`。每个任务只发给一个 Worker——无需协调，无重复处理。Worker 随时加入或退出，无需重新配置。

```python
# 生产者
await client.send("task.queue",
    b'{"task":"reindex","id":"t-101"}',
    priority=Priority.CRITICAL,
)

# Worker A 和 Worker B——相同的 group_name
messages = await client.fetch("task.queue", group_name="workers", num_msgs=1)
for msg in messages:
    await process(msg)
    await client.ack("task.queue", "workers", msg.msg_id)
```

### 云到边缘的命令投递

云端向边缘 Agent 的邮箱发布命令。边缘 Agent 可能离线数小时。重连后按优先级 FETCH 所有待处理命令——先处理紧急重配置，再处理常规任务。

```go
client.Send(ctx, "edge.agent", []byte(`{"cmd":"reconfigure"}`),
    mq9.SendOptions{Priority: mq9.PriorityCritical})

client.Send(ctx, "edge.agent", []byte(`{"cmd":"run_diagnostic"}`), mq9.SendOptions{})

// 边缘 Agent：重连后按优先级拉取
messages, _ := client.Fetch(ctx, "edge.agent", mq9.FetchOptions{
    GroupName: "edge-agent",
    Deliver:   "earliest",
    NumMsgs:   10,
})
```

### 人工审批

人工客户端使用完全相同的协议——无需 webhook，无需路由中间件，无需额外通知系统。

```typescript
// Agent：向人工邮箱发送审批请求
await client.send(humanMailAddress, JSON.stringify({
  type: "approval_request",
  action: "delete_dataset",
  reply_to: agentMailAddress,
}), { priority: Priority.URGENT });

// 人工客户端——相同 SDK
const consumer = await client.consume(humanMailAddress, async (req) => {
  const data = JSON.parse(new TextDecoder().decode(req.payload));
  const approved = await showApprovalUI(data);
  await client.send(data.reply_to, JSON.stringify({ approved, reviewer: "alice" }));
});
```

### 异步请求-回复

Agent A 向 Agent B 提问，继续其他工作，准备好时拉取回复。

```bash
# Agent A：创建私有回复邮箱
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl":600}'
# → {"mail_address":"reply.a1b2c3"}

# Agent A：发送请求，附带 reply_to
nats request '$mq9.AI.MSG.SEND.agent.b' '{
  "request":"translate","text":"Hello world","lang":"fr","reply_to":"reply.a1b2c3"
}'

# Agent B：处理并回复
nats request '$mq9.AI.MSG.FETCH.agent.b' '{"group_name":"b-worker","deliver":"earliest"}'
nats request '$mq9.AI.MSG.SEND.reply.a1b2c3' '{"result":"Bonjour le monde"}'
nats request '$mq9.AI.MSG.ACK.agent.b' '{"group_name":"b-worker","mail_address":"agent.b","msg_id":1}'

# Agent A：随时 FETCH 回复
nats request '$mq9.AI.MSG.FETCH.reply.a1b2c3' '{"deliver":"earliest"}'
```

---

## LangChain / LangGraph 集成

`langchain-mq9` 将所有 mq9 操作封装为 LangChain 工具，让你的 LLM Agent 无需自定义代码即可注册、发现、发送和接收。

```bash
pip install langchain-mq9
```

**8 个工具：**

| 工具 | 操作 |
| ---- | ---- |
| `agent_register` | 注册 Agent 及其能力 |
| `agent_discover` | 按文本或语义搜索 Agent |
| `create_mailbox` | 创建私有邮箱 |
| `send_message` | 发送带优先级的消息 |
| `fetch_messages` | 拉取消息（FETCH + ACK 模型） |
| `ack_messages` | 推进消费组位点 |
| `query_messages` | 只读检查邮箱 |
| `delete_message` | 删除指定消息 |

```python
from langchain_mq9 import Mq9Toolkit
from langgraph.prebuilt import create_react_agent

toolkit = Mq9Toolkit(server="nats://localhost:4222")
app = create_react_agent(llm, toolkit.get_tools())
result = await app.ainvoke({"messages": [("human", "发现所有已注册的 Agent")]})
```

---

## MCP 服务器

mq9 在 RobustMQ 管理服务器上暴露 MCP 服务器端点。连接任何支持 MCP 的客户端（Claude Desktop、Cursor 等）：

```text
http://<admin-server>:<port>/mcp
```

---

## 错误处理

所有协议响应都包含 `error` 字段。空字符串表示成功。

| 错误信息 | 原因 |
| -------- | ---- |
| `mailbox xxx already exists` | 使用已存在的名称调用 CREATE |
| `mailbox not found` | 邮箱不存在或已过期 |
| `message not found` | 指定的 `msg_id` 不存在或已过期 |
| `invalid mail_address` | 格式无效（含大写字母、连字符等） |
| `agent not found` | 使用未知 Agent 名称调用 UNREGISTER 或 REPORT |

SDK 异常：所有 SDK 对非空 `error` 响应抛出/返回 `Mq9Error`。

---

## 部署

### 开发环境（Docker）

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

### 生产环境——单节点

```bash
docker run -d \
  --name mq9 \
  -p 4222:4222 \
  -p 9090:9090 \
  -v /data/mq9:/data \
  --restart unless-stopped \
  robustmq/robustmq:latest
```

- 端口 `4222` — mq9/NATS 协议（Agent 连接）
- 端口 `9090` — Prometheus 指标端点

单节点可处理数百万并发 Agent 连接。

### 集群模式

单节点不够时水平扩展。Agent 使用相同 SDK——无需修改客户端代码。

---

## 模式参考

| 场景 | 关键特性 |
| ---- | -------- |
| 能力路由 | AGENT.REGISTER + AGENT.DISCOVER → 发送给发现的 Agent |
| 点对点 | 私有邮箱 + FETCH + ACK |
| 竞争消费 | 多 Worker 共享 `group_name` |
| 请求-回复 | 私有回复邮箱 + `reply_to` |
| 离线投递 | 先存储，重连后 FETCH |
| 云到边缘 | 重连时按优先级排序 |
| 人工审批 | 人类和 Agent 使用相同协议 |

*设计原理见 [mq9 是什么](/zh/docs/what)。Agent 协议视角见[给 Agent](/zh/docs/for-agent)。*
