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
from a2a.helpers import new_text_artifact, new_text_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types.a2a_pb2 import (
    AgentCard, AgentCapabilities, AgentSkill,
    TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent,
)
from mq9.a2a import Mq9A2AAgent

agent = Mq9A2AAgent()  # 默认连接公共调试服务

@agent.on_message(group_name="demo.agent.translator.workers", deliver="earliest", num_msgs=10, max_wait_ms=500)
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    # 以下事件推送遵循 A2A 协议规定的标准流程：WORKING → Artifact → COMPLETED

    # A2A 协议：先发 WORKING，告知发送方任务已开始处理
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    ))

    # A2A 协议：Message 由多个 Part 组成，每个 Part 可以是 text/data/file
    # 这里取第一个 text part，即发送方传入的文本内容
    text = context.message.parts[0].text if context.message.parts else ""
    result = my_translate(text)  # 替换为你的翻译逻辑

    # A2A 协议：推送结果 Artifact，可多次调用实现流式输出
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        artifact=new_text_artifact(name="translation", text=result),
    ))
    # A2A 协议：最后发 COMPLETED，标志任务结束
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=context.task_id,
        context_id=context.context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
    ))

card = AgentCard(
    name="demo.agent.translator",
    description="多语言翻译 Agent，支持 EN、ZH、JA、KO。",
    version="1.0.0",
    skills=[AgentSkill(id="translate", name="Translate text")],
    capabilities=AgentCapabilities(streaming=True),
)

async def main():
    await agent.connect()
    mailbox = await agent.create_mailbox(card.name)  # 创建 mailbox，开始接收消息
    await agent.register(card)                       # 发布到注册中心，可被发现
    print("mailbox:", mailbox)
    await asyncio.Event().wait()  # 保持运行，直到 Ctrl+C

asyncio.run(main())
```

### Agent B — 发现 Agent A 并发送任务

```python
import asyncio
from a2a.helpers import new_text_message
from a2a.types.a2a_pb2 import AgentCard, AgentCapabilities, Role, SendMessageRequest
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from mq9.a2a import Mq9A2AAgent

agent_b = Mq9A2AAgent()  # 默认连接公共调试服务

# 所有消息都到这里——包括结果回包和其他 Agent 主动发来的新任务
# 通过 context.task_id 区分：和自己发出的 task_id 对上了就是回包，否则是新任务
@agent_b.on_message(group_name="demo.agent.sender.workers", deliver="earliest", num_msgs=10, max_wait_ms=500)
async def handle_incoming(context: RequestContext, _: EventQueue) -> None:
    text = context.message.parts[0].text if context.message.parts else ""
    print(f"收到消息 task_id={context.task_id}：{text}")
    # 业务层持有 task_id，自己决定这条消息的意义

card_b = AgentCard(
    name="demo.agent.sender",
    description="任务发送方",
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
)

async def main():
    await agent_b.connect()
    b_mailbox = await agent_b.create_mailbox(card_b.name)
    await agent_b.register(card_b)

    results = await agent_b.discover("翻译 agent")
    target = results[0]

    request = SendMessageRequest(
        message=new_text_message("你好，世界", role=Role.ROLE_USER)
    )

    # send_message 返回 msg_id，表示消息已成功入队
    # task_id 由 Agent A 生成，随回包事件到达，从 context.task_id 读取
    msg_id = await agent_b.send_message(target["mailbox"], request, reply_to=b_mailbox)
    print(f"已发送，msg_id={msg_id}")

    # 等待结果通过 @on_message 到达
    await asyncio.sleep(10)

    await agent_b.unregister()
    await agent_b.close()

asyncio.run(main())
```

`send_message` 带 `reply_to` 时返回 `(msg_id, task_id)`。框架把 `task_id` 透传到每条回包的 `context.task_id`，所有消息统一进 `@on_message`，业务层用 `task_id` 自行区分回包和新任务。

---

## Mq9A2AAgent

```python
Mq9A2AAgent(*, server: str = "nats://demo.robustmq.com:4222", request_timeout: float = 60)
```

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `server` | `str` | mq9 broker 的 NATS 地址。默认连接公共调试服务 `nats://demo.robustmq.com:4222`，可不填 |
| `request_timeout` | `float` | 对外发送请求的默认超时时间，秒 |

### `agent.connect`

连接 broker，所有操作前必须先调用。

### `agent.close`

停止消费消息并断开 broker 连接。积压消息处理完毕后调用。

### `@agent.on_message`

装饰器，注册消息处理函数，同时可配置消费者参数：

```python
# 不带参数
@agent.on_message
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    ...

# 带消费者参数
@agent.on_message(group_name="my-group", num_msgs=20)
async def handle(context: RequestContext, event_queue: EventQueue) -> None:
    ...
```

| 参数 | 说明 |
| --- | --- |
| `group_name` | 消费组名称。不填时自动使用 `{mailbox名}.workers`，保证重启后从断点续消费 |
| `deliver` | 消费起点：`"earliest"`（默认）从最早未消费处开始，`"latest"` 只消费新消息 |
| `num_msgs` | 每次 fetch 批量拉取的消息数，默认 `10` |
| `max_wait_ms` | 每次 fetch 无消息时的最长等待时间，毫秒，默认 `500` |

### `agent.create_mailbox`

创建 mailbox 并在后台启动消费者，**立即返回** mailbox 地址字符串。

| 参数 | 说明 |
| --- | --- |
| `name` | mailbox 名称，即 `AgentCard.name` |
| `ttl` | Mailbox 存活时间，秒（`0` 表示永久，默认） |

返回值：`str`，mailbox 地址。创建后即可接收消息，无需注册到注册中心。

### `agent.register`

将 Agent 身份发布到注册中心，其他 Agent 可通过 `discover()` 找到此 Agent。

参数：`agent_card` — `AgentCard`（来自 `a2a.types.a2a_pb2`）。

必须在 `create_mailbox()` 之后调用。

### `agent.unregister`

从注册中心注销，其他 Agent 将无法再发现此 Agent。连接和消费者保持运行，积压消息仍可继续处理。处理完毕后调用 `close()` 彻底停止。

### `agent.discover`

按自然语言描述在注册中心发现其他 Agent。

| 参数 | 说明 |
| --- | --- |
| `query` | 自然语言查询字符串；传 `None` 列出全部 |
| `semantic` | `True`（默认）向量语义搜索；`False` 关键词匹配 |
| `limit` | 返回结果数上限，默认 `10` |

返回 `list[dict]`，每项包含 `name`、`mailbox`、`agent_card` 等字段。

### `agent.send_message`

向另一个 Agent 发送消息。

| 参数 | 说明 |
| --- | --- |
| `mail_address` | `discover()` 返回的 Agent 信息字典（需含 `mailbox`），或直接传 mailbox 地址字符串 |
| `request` | `SendMessageRequest`（来自 `a2a.types.a2a_pb2`） |
| `reply_to` | 自己的 mailbox 地址。设置后框架自动生成 `task_id`，每条回包的 `context.task_id` 都会带上该值，业务层用它区分不同任务的回包 |

返回 `int`，broker 分配的 `msg_id`，表示消息已成功入队。`task_id` 由执行方（接收任务的 Agent）生成，随回包事件到达，从 `context.task_id` 读取。

### `agent.get_task`

查询另一个 Agent 上指定任务的当前状态。

参数：`mail_address`、`task_id: str`。返回 `Task | None`。

### `agent.list_tasks`

列出另一个 Agent 存储的所有任务。

参数：`mail_address`、`page_size: int = 100`。返回 `list[Task]`。

### `agent.cancel_task`

请求取消另一个 Agent 上正在运行的任务。

参数：`mail_address`、`task_id: str`。返回更新后的 `Task | None`。

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
