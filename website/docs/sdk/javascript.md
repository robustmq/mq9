---
title: JavaScript SDK — mq9
description: mq9 JavaScript/TypeScript SDK API reference and usage guide.
---

# JavaScript SDK

## Install

```bash
npm install mq9
```

TypeScript types are included. Requires Node.js 18+.

## Quick start

```typescript
import { Mq9Client, Priority } from "mq9";

const client = new Mq9Client("nats://localhost:4222");
await client.connect();

// Create a mailbox
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });

// Send a message
await client.send(address, { task: "analyze", data: "..." });

// Consume messages
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
  requestTimeout?: number;   // ms, default 5000
  reconnectAttempts?: number; // default 5
  reconnectDelay?: number;   // ms, default 2000
})
```

### connect / close

```typescript
await client.connect()
await client.close()
```

---

## Mailbox

### mailboxCreate

```typescript
await client.mailboxCreate(options?: {
  name?: string;   // omit to auto-generate
  ttl?: number;    // seconds; 0 = never expires, default 0
}) -> Promise<string>  // returns mail_address
```

```typescript
const address = await client.mailboxCreate({ name: "agent.inbox", ttl: 3600 });
const address = await client.mailboxCreate(); // auto-generated
```

---

## Messaging

### send

```typescript
await client.send(
  mailAddress: string,
  payload: Uint8Array | string | object,
  options?: {
    priority?: Priority;       // default Priority.NORMAL
    key?: string;              // dedup key
    delay?: number;            // seconds
    ttl?: number;              // message-level TTL in seconds
    tags?: string[];           // e.g. ["billing", "vip"]
  }
) -> Promise<number>           // msg_id; -1 for delayed messages
```

```typescript
// Normal send (object auto-serialized to JSON)
const msgId = await client.send("agent.inbox", { task: "analyze" });

// Urgent priority
const msgId = await client.send("agent.inbox", "alert", { priority: Priority.URGENT });

// Dedup key
const msgId = await client.send("task.status", { status: "running" }, { key: "state" });

// Delayed delivery
const msgId = await client.send("agent.inbox", "hello", { delay: 60 });
```

### fetch

```typescript
await client.fetch(
  mailAddress: string,
  options?: {
    groupName?: string;        // omit for stateless
    deliver?: "latest" | "earliest" | "from_time" | "from_id"; // default "latest"
    fromTime?: number;         // unix timestamp
    fromId?: number;
    forceDeliver?: boolean;
    numMsgs?: number;          // default 100
    maxWaitMs?: number;        // default 500
  }
) -> Promise<Message[]>
```

```typescript
// Stateless
const messages = await client.fetch("task.inbox", { deliver: "earliest" });

// Stateful
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
    numMsgs?: number;          // default 10
    maxWaitMs?: number;        // default 500
    autoAck?: boolean;         // default true
    errorHandler?: (msg: Message, err: Error) => Promise<void>;
  }
) -> Promise<Consumer>
```

- Handler throws → message **not ACKed**, `errorHandler` called, loop continues.

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

## Agent management

### agentRegister

```typescript
await client.agentRegister(agentCard: Record<string, unknown>) -> Promise<void>
// agentCard must contain a "mailbox" field
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
  limit?: number;   // default 20
  page?: number;    // default 1
}) -> Promise<Record<string, unknown>[]>
```

---

## Data types

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
  createTime: number;   // unix timestamp (seconds)
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
