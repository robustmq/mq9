---
title: 给工程师 — mq9 集成指南
description: 如何将 mq9 集成到你的系统中。快速开始、SDK 示例、部署和常见模式。
---

# 给工程师

你在构建多 Agent 系统。这是你的集成指南。

> 本页假设你已阅读[什么是 mq9](/zh/what)，专注于集成代码和生产注意事项。

## 快速开始 — 公共演示服务器

无需本地部署，连接 RobustMQ 演示服务器：

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

这是共享环境——请勿发送敏感数据。

### 创建邮箱

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"quickstart.demo","ttl":300}'
# {"error":"","mail_address":"quickstart.demo"}
```

### 发送带优先级的消息

```bash
# critical — 最先处理
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# normal（默认，无 header）
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  '{"type":"task","payload":"process dataset A"}'
```

### Fetch 和 ACK

```bash
# Fetch — 按优先级顺序返回（critical → urgent → normal）
nats request '$mq9.AI.MSG.FETCH.quickstart.demo' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'

# ACK — 推进位点到最后处理的 msg_id
nats request '$mq9.AI.MSG.ACK.quickstart.demo' '{
  "group_name": "my-worker",
  "mail_address": "quickstart.demo",
  "msg_id": 3
}'
```

---

## 安装 SDK

mq9 提供官方 SDK，用类型化 API 封装 NATS 协议调用：

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

## 核心操作（SDK 示例）

### 创建邮箱

```python
# Python
from mq9 import Mq9Client
client = await Mq9Client.connect("nats://localhost:4222")
address = await client.mailbox_create(name="agent.inbox", ttl=3600)
```

```go
// Go
client, _ := mq9.Connect("nats://localhost:4222")
address, _ := client.MailboxCreate(ctx, "agent.inbox", 3600)
```

```typescript
// TypeScript
const client = new Mq9Client("nats://localhost:4222");
await client.connect();
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
```

- `name = ""` (Python: `None`, Go: `""`) — broker 自动生成地址
- `ttl = 0` — 邮箱永不过期

### 发送消息

```python
# Python — 带优先级和选项
msg_id = await client.send(
    "agent.inbox",
    b'{"task":"analyze","data":"..."}',
    priority=Priority.URGENT,
    key="state",       # 去重——同 key 只保留最新
    delay=60,          # 60 秒后投递
    ttl=300,           # 消息 300 秒后过期
    tags=["billing"],
)
```

```go
// Go
msgId, _ := client.Send(ctx, "agent.inbox", []byte(`{"task":"analyze"}`), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
    Key:      "state",
    Delay:    60,
})
```

### 拉取消息（Pull + ACK）

```python
# Python — 有状态消费
from mq9 import FetchOptions
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

ACK **批次中最后一条 `msg_id`**——一次调用确认整批，下次 FETCH 从该位点续拉。

**无状态拉取** — 不传 `group_name`。每次调用独立，不记录位点，适合一次性读取和检查。

### 持续消费循环

使用 `consume()` 自动轮询处理：

```python
# Python
consumer = await client.consume(
    "agent.inbox",
    handler=async_handler,
    group_name="workers",
    auto_ack=True,
    error_handler=lambda msg, err: print(f"msg {msg.msg_id} failed: {err}"),
)
# ... 做其他工作 ...
await consumer.stop()
print(f"processed: {consumer.processed_count}")
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

- handler 抛出异常 → 消息**不 ACK**，调用 `errorHandler`，循环继续
- `consumer.stop()` 等待当前批次处理完毕后干净退出

### Agent 注册

```python
# 启动时注册
await client.agent_register({
    "name": "agent.translator",
    "mailbox": "agent.translator",
    "payload": "Multilingual translation; EN/ZH/JA/KO",
})

# 语义搜索发现
agents = await client.agent_discover(semantic="translate Chinese to English", limit=5)

# 上报心跳
await client.agent_report({"name": "agent.translator", "report_info": "running"})

# 关闭时注销
await client.agent_unregister("agent.translator")
```

---

## 常见模式

### 子 Agent 结果返回

父 Agent 创建私有回复邮箱并在 spawn 时传给子 Agent。子 Agent 写入结果，父 Agent 随时 FETCH——无需阻塞等待，无共享状态。

```python
# 父 Agent：创建私有回复邮箱
reply_address = await client.mailbox_create(ttl=3600)

# 父 Agent：发送任务并带上 reply_to
await client.send("task.dispatch", json.dumps({
    "task": "summarize /data/corpus",
    "reply_to": reply_address,
}).encode())

# 父 Agent：随时 FETCH 结果（非阻塞）
messages = await client.fetch(reply_address, group_name="orchestrator", deliver="earliest")
```

### 多 Worker 竞争消费任务队列

多个 Worker 共享同一个 `group_name`。每条任务只被一个 Worker 拿到——无需协调，无重复消费。Worker 随时加入或退出，无需重新配置。

```python
# 生产者：发送带优先级的任务
await client.send("task.queue",
    b'{"task":"reindex","id":"t-101"}',
    priority=Priority.CRITICAL,
)

# Worker A 和 Worker B — 相同的 group_name
messages = await client.fetch("task.queue", group_name="workers", num_msgs=1)
for msg in messages:
    await process(msg)
    await client.ack("task.queue", "workers", msg.msg_id)
```

### 云端到边缘指令下发

云端向边缘 Agent 邮箱发指令，边缘断网期间消息持久化等待。重连后按优先级顺序 FETCH——紧急重配置先于常规任务。

```go
// 云端：发布指令（边缘可能离线）
client.Send(ctx, "edge.agent", []byte(`{"cmd":"reconfigure","params":{"rate":100}}`),
    mq9.SendOptions{Priority: mq9.PriorityCritical})

client.Send(ctx, "edge.agent", []byte(`{"cmd":"run_diagnostic"}`), mq9.SendOptions{})

// 边缘：重连后按优先级拉取所有待处理指令
messages, _ := client.Fetch(ctx, "edge.agent", mq9.FetchOptions{
    GroupName: "edge-agent",
    Deliver:   "earliest",
    NumMsgs:   10,
})
```

### 人机混合审批工作流

人类客户端使用与 Agent 完全相同的协议——无需 webhook，无需路由中间件。

```typescript
// Agent：向人类邮箱发送审批请求
await client.send(humanMailAddress, JSON.stringify({
  type: "approval_request",
  action: "delete_dataset",
  target: "ds-prod-2024",
  reply_to: agentMailAddress,
}), { priority: Priority.URGENT });

// 人类客户端——同一个 SDK
const consumer = await client.consume(humanMailAddress, async (req) => {
  const data = JSON.parse(new TextDecoder().decode(req.payload));
  const approved = await showApprovalUI(data);
  await client.send(data.reply_to, JSON.stringify({ approved, reviewer: "alice" }));
});
```

### 异步 Request-Reply

Agent A 向 Agent B 发问题，继续做其他工作。Agent B 按自己的节奏处理，将结果 SEND 到 A 的私有回复邮箱。

```bash
# Agent A：创建私有回复邮箱
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl":600}'
# → {"mail_address":"reply.a1b2c3"}

# Agent A：向 Agent B 发请求并带上 reply_to
nats request '$mq9.AI.MSG.SEND.agent.b' '{
  "request":"translate","text":"Hello world","lang":"fr","reply_to":"reply.a1b2c3"
}'

# Agent B：拉取任务并回复
nats request '$mq9.AI.MSG.FETCH.agent.b' '{"group_name":"b-worker","deliver":"earliest"}'
nats request '$mq9.AI.MSG.SEND.reply.a1b2c3' '{"result":"Bonjour le monde"}'
nats request '$mq9.AI.MSG.ACK.agent.b' '{"group_name":"b-worker","mail_address":"agent.b","msg_id":1}'

# Agent A：随时 FETCH 结果
nats request '$mq9.AI.MSG.FETCH.reply.a1b2c3' '{"deliver":"earliest"}'
```

---

## LangChain / LangGraph 集成

`langchain-mq9` 是官方工具包，将所有 mq9 操作封装为 LangChain 工具，开箱即用支持 LangChain 和 LangGraph。

```bash
pip install langchain-mq9
```

**8 个工具：**

| 工具 | 操作 |
|------|------|
| `create_mailbox` | 创建私有邮箱 |
| `send_message` | 发送带优先级的消息 |
| `fetch_messages` | 拉取消息（FETCH + ACK 模型） |
| `ack_messages` | 推进消费组位点 |
| `query_messages` | 只读检查邮箱 |
| `delete_message` | 删除指定消息 |
| `agent_register` | 注册 Agent 及能力描述 |
| `agent_discover` | 按文本或语义搜索 Agent |

**LangChain：**

```python
from langchain_mq9 import Mq9Toolkit
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI

toolkit = Mq9Toolkit(server="nats://localhost:4222")
tools = toolkit.get_tools()

llm = ChatOpenAI(model="gpt-4o")
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
result = executor.invoke({"input": "创建一个邮箱并发送任务摘要"})
```

**LangGraph：**

```python
from langgraph.prebuilt import create_react_agent
from langchain_mq9 import Mq9Toolkit

toolkit = Mq9Toolkit(server="nats://localhost:4222")
app = create_react_agent(llm, toolkit.get_tools())
result = await app.ainvoke({"messages": [("human", "发现所有已注册的 Agent")]})
```

---

## MCP Server

mq9 在 RobustMQ Admin Server 上暴露 Model Context Protocol (MCP) server。连接任意 MCP 兼容客户端（Claude Desktop、Cursor 等）：

```text
http://<admin-server>:<port>/mcp
```

---

## 错误处理

所有协议响应包含 `error` 字段，空字符串表示成功。

| 错误信息 | 原因 |
|----------|------|
| `mailbox xxx already exists` | CREATE 时名称已存在 |
| `mailbox not found` | 邮箱不存在或已过期 |
| `message not found` | 指定 `msg_id` 不存在或已过期 |
| `invalid mail_address` | 格式无效（含大写、连字符等） |
| `agent not found` | UNREGISTER 或 REPORT 时 Agent 名称未知 |

SDK 异常：所有 SDK 对非空 `error` 响应抛出 / 返回 `Mq9Error`。

---

## 部署

### 开发环境（Docker）

```bash
docker run -d --name mq9 -p 4222:4222 -v mq9-data:/data robustmq/robustmq:latest
```

挂载 `-v mq9-data:/data` 以在重启时保留邮箱和消息。

### 生产环境 — 单节点

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

单节点可处理数百万并发 Agent 连接，足以应对大多数生产负载。

### 集群模式

当单节点不够用时横向扩展。Agent 使用相同的 SDK——客户端代码无需修改。

---

## 模式参考

| 场景 | 关键特性 |
|------|----------|
| 点对点 | 私有邮箱 + FETCH + ACK |
| 竞争消费 | 多 Worker 共享 `group_name` |
| 广播 | 命名公共邮箱，多个消费者 |
| Request-Reply | 私有回复邮箱 + `reply_to` |
| 离线投递 | 存储优先，重连后 FETCH |
| 能力发现 | AGENT.REGISTER + AGENT.DISCOVER |
| 云端到边缘 | 重连后按优先级顺序消费 |
| 人机混合 | 人和 Agent 使用相同协议 |

*设计原理见[什么是 mq9](/zh/what)。Agent 协议视角见[给 Agent](/zh/for-agent)。*
