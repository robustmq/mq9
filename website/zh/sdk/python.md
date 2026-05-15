---
title: Python SDK — mq9
description: mq9 Python SDK API 参考与使用指南。
---

# Python SDK

## 安装

```bash
pip install mq9
```

需要 Python 3.10+。唯一的运行时依赖是 `nats-py`。

## 快速开始

```python
import asyncio
from mq9 import Mq9Client, Priority

async def main():
    async with Mq9Client("nats://localhost:4222") as client:
        # 创建邮箱
        address = await client.mailbox_create(name="agent.inbox", ttl=3600)

        # 发送消息
        await client.send(address, {"task": "analyze", "data": "..."})

        # 消费消息
        async def handler(msg):
            print(f"Received: {msg.payload}")

        consumer = await client.consume(address, handler, group_name="workers")
        await asyncio.sleep(10)
        await consumer.stop()

asyncio.run(main())
```

## Mq9Client

```python
Mq9Client(
    server: str,
    *,
    request_timeout: float = 5.0,
    reconnect_attempts: int = 5,
    reconnect_delay: float = 2.0,
)
```

支持异步上下文管理器 — `async with Mq9Client(...) as client`。

### connect / close

```python
await client.connect()
await client.close()
```

---

## 邮箱

### mailbox_create

```python
await client.mailbox_create(
    *,
    name: str | None = None,   # 省略则由 broker 自动生成
    ttl: int = 0,              # 秒；0 = 永不过期
) -> str                       # 返回 mail_address
```

```python
address = await client.mailbox_create(name="agent.inbox", ttl=3600)
# 自动生成地址
address = await client.mailbox_create(ttl=7200)
```

---

## 消息收发

### send

```python
await client.send(
    mail_address: str,
    payload: bytes | str | dict,
    *,
    priority: Priority = Priority.NORMAL,
    key: str | None = None,        # 去重键 — broker 对相同 key 只保留最新消息
    delay: int | None = None,      # 延迟投递 N 秒
    ttl: int | None = None,        # 消息级别 TTL（秒）
    tags: list[str] | None = None, # 例如 ["billing", "vip"]
) -> int                           # msg_id；延迟消息返回 -1
```

```python
# 普通发送
msg_id = await client.send("agent.inbox", {"task": "analyze"})

# 紧急优先级
msg_id = await client.send("agent.inbox", b"alert", priority=Priority.URGENT)

# 去重键 — broker 对相同 key 只保留最新消息
msg_id = await client.send("task.status", {"status": "running"}, key="state")

# 延迟投递
msg_id = await client.send("agent.inbox", "hello", delay=60)

# 带标签
msg_id = await client.send("orders.inbox", payload, tags=["billing", "vip"])
```

### fetch

```python
await client.fetch(
    mail_address: str,
    *,
    group_name: str | None = None,   # 省略则为无状态消费
    deliver: str = "latest",         # "latest" | "earliest" | "from_time" | "from_id"
    from_time: int | None = None,    # Unix 时间戳，与 deliver="from_time" 配合使用
    from_id: int | None = None,      # 与 deliver="from_id" 配合使用
    force_deliver: bool = False,     # 重置 offset 并从 deliver 策略重新开始
    num_msgs: int = 100,
    max_wait_ms: int = 500,
) -> list[Message]
```

```python
# 无状态 — 每次调用从头开始
messages = await client.fetch("task.inbox", deliver="earliest")

# 有状态 — broker 按消费组记录 offset
messages = await client.fetch("task.inbox", group_name="workers")

# 处理完成后 ACK 以推进 offset
for msg in messages:
    await client.ack("task.inbox", "workers", msg.msg_id)
```

### ack

```python
await client.ack(
    mail_address: str,
    group_name: str,
    msg_id: int,
) -> None
```

### consume

在后台自动运行 fetch 循环，调用后立即返回。

```python
consumer = await client.consume(
    mail_address: str,
    handler: Callable[[Message], Awaitable[None]],
    *,
    group_name: str | None = None,
    deliver: str = "latest",
    num_msgs: int = 10,
    max_wait_ms: int = 500,
    auto_ack: bool = True,
    error_handler: Callable[[Message, Exception], Awaitable[None]] | None = None,
) -> Consumer
```

- 若 `handler` 抛出异常，消息将**不会被 ACK**（保留以便重试）。
- `error_handler=None` 时记录错误日志并继续循环。

```python
async def handler(msg):
    data = json.loads(msg.payload)
    print(data)

async def on_error(msg, exc):
    print(f"Failed on msg {msg.msg_id}: {exc}")

consumer = await client.consume(
    "task.inbox",
    handler,
    group_name="workers",
    error_handler=on_error,
)

# 稍后停止
await consumer.stop()
print(consumer.processed_count)
```

### query

查看邮箱内容，不影响消费 offset。

```python
await client.query(
    mail_address: str,
    *,
    key: str | None = None,
    limit: int | None = None,
    since: int | None = None,   # Unix 时间戳
) -> list[Message]
```

### delete

```python
await client.delete(mail_address: str, msg_id: int) -> None
```

---

## Agent 管理

### agent_register

```python
await client.agent_register(agent_card: dict) -> None
```

`agent_card` 必须包含 `mailbox` 字段，其余内容为上层协议内容（例如 A2A AgentCard）。

```python
from a2a.types import AgentCard  # a2a python sdk

card = AgentCard(...).model_dump()
card["mailbox"] = f"mq9://broker/{address}"
await client.agent_register(card)
```

### agent_unregister

```python
await client.agent_unregister(mailbox: str) -> None
```

### agent_report

```python
await client.agent_report(report: dict) -> None
# report 必须包含 "mailbox" 字段
```

### agent_discover

```python
await client.agent_discover(
    *,
    text: str | None = None,       # 全文关键词搜索
    semantic: str | None = None,   # 语义搜索（优先级高于 text）
    limit: int = 20,
    page: int = 1,
) -> list[dict]
```

```python
# 搜索支付相关 Agent
agents = await client.agent_discover(text="payment invoice")

# 语义搜索
agents = await client.agent_discover(semantic="process a refund request")

# 列出全部
agents = await client.agent_discover()
```

---

## 数据类型

### Priority

```python
class Priority(str, Enum):
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"
```

相同优先级的消息遵循 FIFO 顺序。跨优先级：`CRITICAL > URGENT > NORMAL`。

### Message

```python
@dataclass
class Message:
    msg_id: int
    payload: bytes
    priority: Priority
    create_time: int    # Unix 时间戳（秒）
```

### Consumer

```python
class Consumer:
    is_running: bool
    processed_count: int
    async def stop(self) -> None
```

### Mq9Error

当 broker 返回非空错误字段，或客户端未连接时抛出。

```python
from mq9 import Mq9Error

try:
    await client.mailbox_create(name="agent.inbox")
except Mq9Error as e:
    print(e)  # "mailbox agent.inbox already exists"
```
