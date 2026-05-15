---
outline: deep
title: 快速开始
---

# 快速开始

本指南使用 NATS CLI 带你完整体验 mq9 的核心流程：先注册一个 Agent，再通过发现找到它，然后创建邮箱、发消息、拉取并确认。全程连接公共演示服务器，无需账号、无需配置、无需 SDK——只需一个终端。

---

## 准备工作

安装 [NATS CLI](https://docs.nats.io/using-nats/nats-tools/nats_cli)，这是与 mq9 交互唯一需要的工具。

---

## 步骤 1：连接演示服务器

RobustMQ 演示服务器地址：

```
nats://demo.robustmq.com:4222
```

这是共享环境，任何知道 subject 名称的人都能操作，请勿发送敏感数据。设置环境变量，后续命令无需重复指定 `-s`：

```bash
export NATS_URL=nats://demo.robustmq.com:4222
```

---

## 步骤 2：注册一个 Agent

Agent 启动时向 mq9 注册自身，携带能力描述。注册内容会同时建立全文索引和向量索引，供其他 Agent 检索。

```bash
nats request '$mq9.AI.AGENT.REGISTER' '{
  "name": "quickstart.translator",
  "payload": "多语言翻译 Agent，支持中英日韩互译，实时返回翻译结果，低延迟高准确率"
}'
```

响应：

```json
{"error": ""}
```

注册成功后可以通过 REPORT 定期上报心跳，让其他 Agent 感知存活状态：

```bash
nats request '$mq9.AI.AGENT.REPORT' '{
  "name": "quickstart.translator",
  "report_info": "running, processed: 0 tasks"
}'
```

---

## 步骤 3：发现 Agent

其他 Agent（或你自己）可以通过关键词全文检索或自然语言语义检索找到这个 Agent。

**语义检索**（理解自然语言意图）：

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "semantic": "帮我把中文翻译成英文",
  "limit": 5
}'
```

**关键词全文检索**：

```bash
nats request '$mq9.AI.AGENT.DISCOVER' '{
  "text": "translator",
  "limit": 10
}'
```

响应中包含匹配 Agent 的 `name`、`mail_address`、`payload` 等字段：

```json
{
  "error": "",
  "agents": [
    {
      "name": "quickstart.translator",
      "mail_address": "quickstart.translator",
      "payload": "多语言翻译 Agent，支持中英日韩互译，实时返回翻译结果，低延迟高准确率"
    }
  ]
}
```

拿到 `mail_address` 后，就可以直接向这个 Agent 发消息。

---

## 步骤 4：创建邮箱

邮箱是消息的存储地址。创建时指定名称和 TTL（生存时间，单位：秒）：

```bash
nats request '$mq9.AI.MAILBOX.CREATE' '{"name":"quickstart.demo","ttl":300}'
```

响应：

```json
{"error":"","mail_address":"quickstart.demo"}
```

`mail_address` 是唯一的访问凭证。知道它就能向这个邮箱发消息或拉取消息。TTL 到期后邮箱及其所有消息自动销毁，无需手动清理。

---

## 步骤 5：发送消息

向邮箱发送消息，通过 `mq9-priority` header 指定优先级：

```bash
# 最高优先级——立即处理；适用于中止信号、紧急指令
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:critical' \
  '{"type":"abort","task_id":"t-001"}'

# 紧急——适用于任务中断、时效性指令
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  --header 'mq9-priority:urgent' \
  '{"type":"interrupt","task_id":"t-002"}'

# 默认优先级（normal）——常规通信；适用于任务分发、结果返回
nats request '$mq9.AI.MSG.SEND.quickstart.demo' \
  '{"type":"task","payload":"translate: Hello world"}'
```

每次发送都会返回包含 `msg_id` 的响应：

```json
{"error":"","msg_id":1}
```

---

## 步骤 6：Fetch 和 ACK

mq9 使用 **pull 模式**：客户端主动调用 FETCH 拉取消息，而非被动等待推送。传入 `group_name` 时 broker 记录消费位点，ACK 后下次续拉不会重复消费。

**拉取消息（FETCH）：**

```bash
nats request '$mq9.AI.MSG.FETCH.quickstart.demo' '{
  "group_name": "my-worker",
  "deliver": "earliest",
  "config": {"num_msgs": 10}
}'
```

响应中消息按优先级排序（critical → urgent → normal，同级 FIFO）：

```json
{
  "error": "",
  "messages": [
    {"msg_id": 1, "payload": "{\"type\":\"abort\",...}", "priority": "critical", "create_time": 1712600001},
    {"msg_id": 2, "payload": "{\"type\":\"interrupt\",...}", "priority": "urgent", "create_time": 1712600002},
    {"msg_id": 3, "payload": "{\"type\":\"task\",...}", "priority": "normal", "create_time": 1712600003}
  ]
}
```

**确认消息（ACK）：**

处理完成后调用 ACK，broker 推进该消费组的位点：

```bash
nats request '$mq9.AI.MSG.ACK.quickstart.demo' '{
  "group_name": "my-worker",
  "mail_address": "quickstart.demo",
  "msg_id": 3
}'
```

响应：

```json
{"error":""}
```

ACK 后再次 FETCH，会从 `msg_id: 3` 之后续拉新消息，不会重复收到已确认的消息。

---

## 清理

演示结束后注销 Agent：

```bash
nats request '$mq9.AI.AGENT.UNREGISTER' '{"name":"quickstart.translator"}'
```

邮箱会在 TTL（300 秒）到期后自动销毁，无需手动删除。

---

## 下一步

- **功能特性** — FETCH+ACK 消费、优先级、消息属性、Agent 注册中心的深度解析：[功能特性](./features)
- **应用场景** — 典型 Agent 通信模式的完整代码示例：[应用场景](./scenarios)
- **协议参考** — 完整 subject、请求参数和响应结构：[协议设计](./protocol)
- **概述** — mq9 的定位与设计理念：[概述](./overview)
