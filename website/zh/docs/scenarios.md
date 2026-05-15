---
title: 应用场景
---

# 应用场景

mq9 围绕 Agent 注册发现和异步消息两个核心能力，覆盖八类典型通信模式。场景按使用顺序排列：先是依赖注册发现的模式，再是纯消息通信模式。

---

## 1. 基于 capability 的 Agent 路由

**模式：** Discover → Send。编排者不硬编码目标 Agent 地址，而是通过能力描述动态发现合适的 Agent，再向其发消息。Agent 能力更新、替换、扩容时，调用方无需任何改动。

```bash
# 步骤 1：能力 Agent 启动时注册自身
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "agent.translator",
  "payload": "多语言翻译 Agent，支持中英日韩互译，实时返回翻译结果，低延迟"
}'

# 步骤 2：调用方按语义意图发现 Agent
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "把这段中文翻译成英文",
  "limit": 3
}'
# 响应中包含 mail_address: "agent.translator"

# 步骤 3：直接向发现的 Agent 邮箱发送任务
nats request '$mq9.AI.MSG.SEND.agent.translator' '{
  "text": "人工智能正在改变世界",
  "target_lang": "en",
  "reply_to": "reply.task001"
}'

# 步骤 4：能力 Agent 拉取任务并处理
nats request '$mq9.AI.MSG.FETCH.agent.translator' \
  '{"group_name": "translator-workers", "deliver": "earliest"}'

# 步骤 5：将结果写入调用方回复邮箱
nats request '$mq9.AI.MSG.SEND.reply.task001' \
  '{"result": "Artificial intelligence is changing the world"}'

nats request '$mq9.AI.MSG.ACK.agent.translator' \
  '{"group_name": "translator-workers", "mail_address": "agent.translator", "msg_id": 1}'
```

**核心功能：** 语义向量检索、Agent 注册、私有回复邮箱、FETCH+ACK。

---

## 2. 子 Agent 结果返回

**模式：** 编排者启动子 Agent 执行耗时任务，通过私有邮箱异步接收结果。子 Agent 完成后写入结果，编排者在准备好时主动取，双方无需同时在线。

```bash
# 编排者：创建私有回复邮箱（TTL 覆盖预期最长任务时间）
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl": 3600}'
# 响应: {"mail_address": "d7a5072lko83"}

# 编排者：向任务分发邮箱发任务，携带 reply_to
nats request '$mq9.AI.MSG.SEND.task.dispatch' \
  '{"task": "summarize /data/corpus", "reply_to": "d7a5072lko83"}'

# 子 Agent：完成后将结果写入编排者邮箱
nats request '$mq9.AI.MSG.SEND.d7a5072lko83' \
  '{"status": "ok", "summary": "数据集包含 12 万条记录，主题集中于..."}'

# 编排者：准备好时拉取结果（即使此时才上线，结果仍在存储中）
nats request '$mq9.AI.MSG.FETCH.d7a5072lko83' \
  '{"group_name": "orchestrator", "deliver": "earliest"}'

# 编排者：确认处理
nats request '$mq9.AI.MSG.ACK.d7a5072lko83' \
  '{"group_name": "orchestrator", "mail_address": "d7a5072lko83", "msg_id": 1}'
```

**核心功能：** 私有邮箱作回复地址、离线持久化、FETCH+ACK 异步结果取回。

---

## 3. 多 Worker 竞争消费任务队列

**模式：** 生产者将任务发送到共享邮箱，多个 Worker 用同一 `group_name` 竞争拉取——每条任务只被处理一次。Worker 可随时加入或退出，无需重新配置。高优先级任务（如中止、重配置）在积压中优先出队。

```bash
# 创建共享任务队列邮箱
nats request '$mq9.AI.MAILBOX.CREATE' '{
  "name": "task.queue",
  "ttl": 86400
}'

# 生产者：发布不同优先级的任务
nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:critical' \
  '{"task": "emergency_reindex", "id": "t-101"}'

nats request '$mq9.AI.MSG.SEND.task.queue' \
  --header 'mq9-priority:urgent' \
  '{"task": "user_export", "id": "t-102"}'

nats request '$mq9.AI.MSG.SEND.task.queue' \
  '{"task": "batch_summarize", "id": "t-103"}'

# Worker A 和 Worker B 用相同的 group_name 竞争拉取
# Worker A：每次只取 1 条，处理完再取下一条
nats request '$mq9.AI.MSG.FETCH.task.queue' \
  '{"group_name": "workers", "deliver": "earliest", "config": {"num_msgs": 1}}'

# Worker A：处理完毕后 ACK（推进共享位点）
nats request '$mq9.AI.MSG.ACK.task.queue' \
  '{"group_name": "workers", "mail_address": "task.queue", "msg_id": 1}'

# Worker B：继续拉取下一条（位点已由 A 推进到 msg_id: 1 之后）
nats request '$mq9.AI.MSG.FETCH.task.queue' \
  '{"group_name": "workers", "deliver": "earliest", "config": {"num_msgs": 1}}'
```

**核心功能：** 共享邮箱、有状态消费（group_name 共享位点）、三级优先级排序。

---

## 4. Agent 注册与健康感知

**模式：** Agent 启动注册、定期心跳、关闭注销。编排者通过 DISCOVER 获取当前在线 Agent 列表，通过心跳时间感知存活状态，实现轻量级服务发现，无需独立的健康检查基础设施。

```bash
# Worker 启动：注册到 Agent 注册中心
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "worker.image-42",
  "payload": "图像处理 Worker，支持 JPEG/PNG/WebP 格式，GPU 加速，单机 QPS 200"
}'

# Worker 运行中：每隔 30 秒上报心跳
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "worker.image-42",
  "report_info": "running, gpu_util: 72%, processed: 1024 tasks, queue_depth: 3"
}'

# 编排者：发现所有图像处理 Worker
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "image",
  "limit": 50
}'

# 编排者：按语义查找有 GPU 加速能力的 Worker
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "GPU 加速的图像处理",
  "limit": 10
}'

# Worker 正常关闭：注销
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name": "worker.image-42"}'
```

**核心功能：** REGISTER/UNREGISTER 生命周期管理、REPORT 心跳上报、DISCOVER 列出在线 Agent。

---

## 5. 云端到边缘指令下发

**模式：** 云端编排者向可能因间歇性网络而离线数小时的边缘 Agent 下发指令。边缘 Agent 重连后主动 FETCH，按优先级顺序获取所有待处理指令——紧急重配置先于常规任务。

```bash
# 云端：为边缘 Agent 创建专属邮箱（长 TTL）
nats request '$mq9.AI.MAILBOX.CREATE' '{
  "name": "edge.agent.001",
  "ttl": 604800
}'

# 云端：下发紧急重配置指令（critical 优先级）
nats request '$mq9.AI.MSG.SEND.edge.agent.001' \
  --header 'mq9-priority:critical' \
  '{"cmd": "reconfigure", "params": {"sampling_rate": 100, "mode": "high_accuracy"}}'

# 云端：下发例行诊断任务（normal 优先级）
nats request '$mq9.AI.MSG.SEND.edge.agent.001' \
  '{"cmd": "run_diagnostic", "target": "sensor-bank-2"}'

# 云端：下发定时任务，30 分钟后才生效（delay 延迟投递）
nats request '$mq9.AI.MSG.SEND.edge.agent.001' \
  --header 'mq9-delay:1800' \
  '{"cmd": "collect_metrics", "interval": 60}'

# 边缘 Agent：重连后拉取所有待处理指令（critical 先返回）
nats request '$mq9.AI.MSG.FETCH.edge.agent.001' \
  '{"group_name": "edge-agent", "deliver": "earliest", "config": {"num_msgs": 10}}'

# 边缘 Agent：处理完毕后 ACK
nats request '$mq9.AI.MSG.ACK.edge.agent.001' \
  '{"group_name": "edge-agent", "mail_address": "edge.agent.001", "msg_id": 2}'
```

**核心功能：** 离线持久化、重连后按优先级顺序拉取、delay 延迟投递、私有邮箱。

---

## 6. 人机混合审批工作流

**模式：** Agent 生成需要人工审查的决策（修改生产数据、代表用户发送通信等），将审批请求发送到共享邮箱。人类使用与 Agent 完全相同的 mq9 协议进行交互——从协议层看没有区别。

```python
import nats
import asyncio, json

async def run():
    nc = await nats.connect("nats://demo.robustmq.com:4222")

    # Agent：创建私有回复邮箱，等待审批结果（TTL 2 小时）
    reply = await nc.request("$mq9.AI.MAILBOX.CREATE", b'{"ttl": 7200}')
    reply_id = json.loads(reply.data)["mail_address"]

    # Agent：将决策发送到共享审批邮箱，携带 reply_to 和 urgent 优先级
    await nc.request(
        "$mq9.AI.MSG.SEND.approvals",
        json.dumps({
            "action": "delete_dataset",
            "target": "ds-prod-2024",
            "reason": "数据保留期到期",
            "reply_to": reply_id
        }).encode(),
        headers={"mq9-priority": "urgent"}
    )

    # 人工审批者（通过任意 NATS 客户端）拉取审批队列：
    # nats request '$mq9.AI.MSG.FETCH.approvals' '{"deliver": "earliest"}'
    # 审查后写入决策：
    # nats request '$mq9.AI.MSG.SEND.<reply_id>' '{"approved": true, "reviewer": "alice"}'

    # Agent：在准备好时拉取审批结果（结果已持久化，随时可取）
    reply_resp = await nc.request(
        f"$mq9.AI.MSG.FETCH.{reply_id}",
        json.dumps({"deliver": "earliest"}).encode()
    )
    messages = json.loads(reply_resp.data).get("messages", [])
    if messages:
        decision = json.loads(messages[0]["payload"])
        print("审批决策:", decision)
        # ACK 确认
        await nc.request(
            f"$mq9.AI.MSG.ACK.{reply_id}",
            json.dumps({
                "mail_address": reply_id,
                "msg_id": messages[0]["msg_id"]
            }).encode()
        )

asyncio.run(run())
```

**核心功能：** 人与 Agent 使用相同协议、私有回复邮箱、异步拉取、urgent 优先级。

---

## 7. 异步 Request-Reply

**模式：** Agent A 需要 Agent B 的处理结果，但不能阻塞等待。A 创建私有回复邮箱，在请求中嵌入 `reply_to` 字段，然后继续其他工作。B 处理完后写入结果，A 在准备消费时主动 FETCH——结果已经在那里等待。

```bash
# Agent A：创建私有回复邮箱
nats request '$mq9.AI.MAILBOX.CREATE' '{"ttl": 600}'
# 响应: {"mail_address": "reply.a1b2c3"}

# Agent A：向 Agent B 发请求，嵌入 reply_to
nats request '$mq9.AI.MSG.SEND.agent.b' '{
  "request": "translate",
  "text": "Hello world",
  "target_lang": "zh",
  "reply_to": "reply.a1b2c3"
}'

# Agent A：继续处理其他工作，不阻塞等待...

# Agent B：拉取自己邮箱中的请求
nats request '$mq9.AI.MSG.FETCH.agent.b' \
  '{"group_name": "b-workers", "deliver": "earliest"}'

# Agent B：处理完后将结果写入 A 的回复邮箱
nats request '$mq9.AI.MSG.SEND.reply.a1b2c3' '{"result": "你好，世界"}'

# Agent B：ACK 自己的消费位点
nats request '$mq9.AI.MSG.ACK.agent.b' \
  '{"group_name": "b-workers", "mail_address": "agent.b", "msg_id": 1}'

# Agent A：准备好时拉取回复——结果已持久化在那里
nats request '$mq9.AI.MSG.FETCH.reply.a1b2c3' \
  '{"deliver": "earliest"}'
```

**核心功能：** 私有邮箱作回复地址、非阻塞异步模式、FETCH+ACK pull 消费。

---

## 8. 告警广播

**模式：** 任何 Agent 检测到异常即向共享告警邮箱发布 critical 消息。多个处理器用同一 `group_name` 竞争消费，每条告警只被处理一次。即使所有处理器临时离线，告警也已落存储，重连后按优先级追赶积压。

```bash
# 告警邮箱（长期存在，不设 TTL）
nats request '$mq9.AI.MAILBOX.CREATE' '{"name": "alerts"}'

# 任意 Agent：检测到异常后发布 critical 告警
nats request '$mq9.AI.MSG.SEND.alerts' \
  --header 'mq9-priority:critical' \
  '{
    "type": "anomaly",
    "source": "monitor-7",
    "detail": "CPU > 95% 持续 5 分钟",
    "ts": 1712600100
  }'

# 发布系统级告警（同样 critical）
nats request '$mq9.AI.MSG.SEND.alerts' \
  --header 'mq9-priority:critical' \
  '{
    "type": "disk_full",
    "source": "storage-node-3",
    "detail": "磁盘使用率 99%",
    "ts": 1712600200
  }'

# 发布低优先级告警通知
nats request '$mq9.AI.MSG.SEND.alerts' \
  --header 'mq9-priority:urgent' \
  '{
    "type": "latency_spike",
    "source": "api-gateway",
    "detail": "P99 延迟超过 2s",
    "ts": 1712600300
  }'

# 处理器（多个实例使用同一 group_name 竞争消费）
nats request '$mq9.AI.MSG.FETCH.alerts' \
  '{"group_name": "alert-handlers", "deliver": "earliest", "config": {"num_msgs": 5}}'

# 处理完毕后 ACK（critical 消息先被取出并处理）
nats request '$mq9.AI.MSG.ACK.alerts' \
  '{"group_name": "alert-handlers", "mail_address": "alerts", "msg_id": 2}'

# 查询当前未处理的 critical 告警（不影响消费位点）
nats request '$mq9.AI.MSG.QUERY.alerts' '{}'
```

**核心功能：** 消息持久化（处理器离线仍可后续拉取）、critical 优先级、多处理器竞争消费、FETCH+ACK。
