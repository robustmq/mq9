---
outline: deep
---

# A2A — Python

## 安装

```bash
pip install mq9
```

**依赖：** Python 3.10+

---

## 概述

每个 Agent 地位平等——既可以向其他 Agent 发送任务，也可以接收其他 Agent 的任务。没有"客户端"或"服务端"之分。

- 只传入 broker 地址，创建 `Mq9A2AAgent`。
- 调用 `connect()` 连接 broker。
- 调用 `register(agent_card)` 发布身份、开始接收任务——会阻塞直到停止。
- 随时调用 `discover()`、`send_message()`、`get_task()` 等与其他 Agent 交互。

---

## 快速上手

### Agent A — 注册并处理传入任务

```python
import asyncio
from a2a.helpers import new_task_from_user_message, new_text_artifact, new_text_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types.a2a_pb2 import (
    AgentCard, AgentCapabilities, AgentSkill,
    TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent,
)
from mq9.a2a import Mq9A2AAgent

agent = Mq9A2AAgent(server="nats://demo.robustmq.com:4222")

@agent.on_message
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    task = context.current_task or new_task_from_user_message(context.message)
    await event_queue.enqueue_event(task)

    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    ))

    text = context.message.parts[0].text if context.message.parts else ""
    result = my_translate(text)  # 替换为你的翻译逻辑

    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        artifact=new_text_artifact(name="translation", text=result),
    ))
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
    ))

card = AgentCard(
    name="agent-a",
    description="多语言翻译 Agent，支持 EN、ZH、JA、KO。",
    version="1.0.0",
    skills=[AgentSkill(id="translate", name="Translate text")],
    capabilities=AgentCapabilities(streaming=True),
)

async def main():
    await agent.connect()
    await agent.register(card)   # 阻塞直到 stop() 或 Ctrl+C

asyncio.run(main())
```

### Agent B — 发现 Agent A 并发送任务

```python
import asyncio
from a2a.helpers import new_text_message
from a2a.types.a2a_pb2 import (
    AgentCard, Role, SendMessageRequest,
    TaskArtifactUpdateEvent, TaskStatusUpdateEvent,
)
from mq9.a2a import Mq9A2AAgent

async def main():
    agent = Mq9A2AAgent(server="nats://demo.robustmq.com:4222")
    await agent.connect()

    # 按自然语言描述发现 Agent A
    results = await agent.discover("翻译 agent")
    target = results[0]

    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )

    async for event in await agent.send_message(target, request, timeout=30):
        if isinstance(event, TaskArtifactUpdateEvent):
            print("结果：", event.artifact.parts[0].text)
        elif isinstance(event, TaskStatusUpdateEvent):
            print("状态：", event.status.state)

    await agent.close()

asyncio.run(main())
```

Agent B 不需要注册——只需 `connect()` 即可发现和发送任务。如果 Agent B 也想接收任务，同样构建自己的 `AgentCard` 并调用 `register()` 即可。

---

## API 参考

### `Mq9A2AAgent`

#### 构造函数

```python
Mq9A2AAgent(*, server: str, mailbox_ttl: int = 0, request_timeout: float = 60)
```

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `server` | `str` | mq9 broker 的 NATS 地址 |
| `mailbox_ttl` | `int` | Mailbox 存活时间，秒（`0` 表示永久） |
| `request_timeout` | `float` | 对外发送请求的默认超时时间，秒 |

#### 连接

| 方法 | 说明 |
| --- | --- |
| `await agent.connect()` | 连接 broker，所有操作前必须先调用 |
| `await agent.close()` | 断开连接 |
| `async with agent` | 上下文管理器，自动 `connect()` / `close()` |

#### 注册（接收任务）

| 方法 | 说明 |
| --- | --- |
| `@agent.on_message` | 装饰器，注册处理函数 `(RequestContext, EventQueue) → None` |
| `await agent.register(agent_card)` | 发布身份、创建 mailbox、开始接收任务，阻塞直到停止 |
| `await agent.stop()` | 优雅注销并断开连接 |

`register()` 从 `agent_card.name` 获取 Agent 名称和 mailbox 地址，并自动创建两个 mailbox：

| Mailbox | 用途 |
| --- | --- |
| `{name}` | 主收件箱，接收传入的任务和控制消息 |
| `{name}.tasks` | 任务存储，持久化任务状态，重启后恢复 |

#### 发现与对外操作

以下所有方法均需先调用 `connect()`。`agent` 参数接受 `discover()` 返回的 Agent 信息字典（需含 `mailbox` 字段）或原始 mailbox 地址字符串。

| 方法 | 说明 |
| --- | --- |
| `await agent.discover(query, *, semantic, limit)` | 按自然语言描述发现 Agent。`semantic=True`（默认）语义搜索；`False` 关键词匹配；`None` 列出全部。 |
| `await agent.send_message(agent, request, *, timeout)` | 发送任务，返回异步迭代器流式输出 A2A 事件（`Task`、`TaskStatusUpdateEvent`、`TaskArtifactUpdateEvent`）。 |
| `await agent.get_task(agent, task_id)` | 按 ID 查询任务当前状态，返回 `Task \| None`。 |
| `await agent.list_tasks(agent, *, page_size)` | 列出某 Agent 的所有任务，返回 `list[Task]`。 |
| `await agent.cancel_task(agent, task_id)` | 请求取消正在运行的任务，返回更新后的 `Task \| None`。 |

---

## Handler 数据类型

`@agent.on_message` 装饰的处理函数接收 a2a-sdk 原生对象：

| 对象 | 类型 | 说明 |
| --- | --- | --- |
| `context.message` | `Message` | 传入的 A2A 消息 |
| `context.task_id` | `str \| None` | 任务 ID（新任务时自动分配） |
| `context.context_id` | `str \| None` | 上下文/会话 ID |
| `context.current_task` | `Task \| None` | 已有任务（续接多轮对话时不为空） |
| `event_queue` | `EventQueue` | 向此推送响应事件 |

可推送的事件类型（均来自 `a2a.types.a2a_pb2`）：

| 事件 | 使用时机 |
| --- | --- |
| `Task` | 第一个事件，创建任务记录 |
| `TaskStatusUpdateEvent(state=WORKING)` | 标志开始处理 |
| `TaskArtifactUpdateEvent` | 推送结果内容，可多次调用实现流式输出 |
| `TaskStatusUpdateEvent(state=COMPLETED)` | 标志任务完成 |
| `TaskStatusUpdateEvent(state=FAILED)` | 标志任务失败 |
| `TaskStatusUpdateEvent(state=CANCELED)` | 标志任务已取消 |
