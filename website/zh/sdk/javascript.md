---
title: JavaScript SDK — mq9
description: mq9 JavaScript/TypeScript SDK API 参考与使用指南。
---

# JavaScript SDK

## 安装

```bash
npm install mq9
```

已内置 TypeScript 类型定义。需要 Node.js 18+。

## 快速开始

```typescript
import { Mq9Client, Priority } from "mq9";

const client = new Mq9Client("nats://localhost:4222");
await client.connect();

// 创建邮箱
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });

// 发送消息
await client.send(address, { task: "analyze", data: "..." });

// 消费消息
const consumer = await client.consume(address, async (msg) => {
  const data = JSON.parse(new TextDecoder().decode(msg.payload));
  console.log(data);
}, { groupName: "workers" });

setTimeout(async () => {
  await consumer.stop();
  await client.close();
}, 10000);
```

## Mq9Client

```typescript
new Mq9Client(server: string, options?: {
  requestTimeout?: number;   // 毫秒，默认 5000
  reconnectAttempts?: number; // 默认 5
  reconnectDelay?: number;   // 毫秒，默认 2000
})
```

### connect / close

```typescript
await client.connect()
await client.close()
```

---

## 邮箱

### mailboxCreate

```typescript
await client.mailboxCreate(options?: {
  name?: string;   // 省略则自动生成
  ttl?: number;    // 秒；0 = 永不过期，默认 0
}) -> Promise<string>  // 返回 mail_address
```

```typescript
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
const address = await client.mailboxCreate(); // 自动生成
```

---

## 消息收发

### send

```typescript
await client.send(
  mailAddress: string,
  payload: Uint8Array | string | object,
  options?: {
    priority?: Priority;       // 默认 Priority.NORMAL
    key?: string;              // 去重键
    delay?: number;            // 秒
    ttl?: number;              // 消息级别 TTL（秒）
    tags?: string[];           // 例如 ["billing", "vip"]
  }
) -> Promise<number>           // msg_id；延迟消息返回 -1
```

```typescript
// 普通发送（object 自动序列化为 JSON）
const msgId = await client.send("agent.inbox", { task: "analyze" });

// 紧急优先级
const msgId = await client.send("agent.inbox", "alert", { priority: Priority.URGENT });

// 去重键
const msgId = await client.send("task.status", { status: "running" }, { key: "state" });

// 延迟投递
const msgId = await client.send("agent.inbox", "hello", { delay: 60 });
```

### fetch

```typescript
await client.fetch(
  mailAddress: string,
  options?: {
    groupName?: string;        // 省略则为无状态
    deliver?: "latest" | "earliest" | "from_time" | "from_id"; // 默认 "latest"
    fromTime?: number;         // Unix 时间戳
    fromId?: number;
    forceDeliver?: boolean;
    numMsgs?: number;          // 默认 100
    maxWaitMs?: number;        // 默认 500
  }
) -> Promise<Message[]>
```

```typescript
// 无状态
const messages = await client.fetch("task.inbox", { deliver: "earliest" });

// 有状态
const messages = await client.fetch("task.inbox", { groupName: "workers" });
for (const msg of messages) {
  await client.ack("task.inbox", "workers", msg.msgId);
}
```

### ack

```typescript
await client.ack(mailAddress: string, groupName: string, msgId: number) -> Promise<void>
```

### consume

```typescript
await client.consume(
  mailAddress: string,
  handler: (msg: Message) => Promise<void>,
  options?: {
    groupName?: string;
    deliver?: string;
    numMsgs?: number;          // 默认 10
    maxWaitMs?: number;        // 默认 500
    autoAck?: boolean;         // 默认 true
    errorHandler?: (msg: Message, err: Error) => Promise<void>;
  }
) -> Promise<Consumer>
```

- handler 抛出异常 → 消息**不会被 ACK**，调用 `errorHandler`，循环继续。

```typescript
const consumer = await client.consume("task.inbox", async (msg) => {
  const data = JSON.parse(new TextDecoder().decode(msg.payload));
  console.log(data);
}, {
  groupName: "workers",
  errorHandler: async (msg, err) => {
    console.error(`msg ${msg.msgId} failed:`, err);
  },
});

await consumer.stop();
console.log(consumer.processedCount);
```

### query

```typescript
await client.query(
  mailAddress: string,
  options?: { key?: string; limit?: number; since?: number }
) -> Promise<Message[]>
```

### delete

```typescript
await client.delete(mailAddress: string, msgId: number) -> Promise<void>
```

---

## Agent 管理

### agentRegister

```typescript
await client.agentRegister(agentCard: Record<string, unknown>) -> Promise<void>
// agentCard 必须包含 "mailbox" 字段
```

### agentUnregister

```typescript
await client.agentUnregister(mailbox: string) -> Promise<void>
```

### agentReport

```typescript
await client.agentReport(report: Record<string, unknown>) -> Promise<void>
```

### agentDiscover

```typescript
await client.agentDiscover(options?: {
  text?: string;
  semantic?: string;
  limit?: number;   // 默认 20
  page?: number;    // 默认 1
}) -> Promise<Record<string, unknown>[]>
```

---

## 数据类型

### Priority

```typescript
enum Priority {
  NORMAL = "normal",
  URGENT = "urgent",
  CRITICAL = "critical",
}
```

### Message

```typescript
interface Message {
  msgId: number;
  payload: Uint8Array;
  priority: Priority;
  createTime: number;   // Unix 时间戳（秒）
}
```

### Consumer

```typescript
class Consumer {
  get isRunning(): boolean;
  get processedCount(): number;
  async stop(): Promise<void>;
}
```

### Mq9Error

```typescript
import { Mq9Error } from "mq9";

try {
  await client.mailboxCreate({ name: "agent.inbox" });
} catch (e) {
  if (e instanceof Mq9Error) console.error(e.message);
}
```
