---
outline: deep
---

# A2A — Java

## 安装

在 `pom.xml` 中添加依赖：

```xml
<dependency>
    <groupId>io.mq9</groupId>
    <artifactId>mq9</artifactId>
    <version>0.1.0</version>
</dependency>
```

**依赖：** Java 17+，Maven

---

## 概述

每个 Agent 地位平等——既可以向其他 Agent 发送任务，也可以接收其他 Agent 的任务。没有"客户端"或"服务端"之分。

- 创建 `Mq9A2AAgent`，只需传入 broker 地址。
- 注册 `onMessage()` 处理函数，同时配置消费者参数。
- 调用 `connect()` 连接 broker。
- 调用 `createMailbox()` 创建 mailbox 并启动后台消费者。
- 调用 `register()` 将 Agent 身份发布到注册中心，对其他 Agent 可见。

---

## 快速上手

### Agent A — 注册并处理传入任务

```java
import io.a2a.spec.*;
import io.mq9.ConsumeOptions;
import io.mq9.a2a.*;

Mq9A2AAgent agentA = Mq9A2AAgent.builder().build();

// A2A 协议规定的标准事件流程：WORKING → Artifact → COMPLETED
agentA.onMessage(
    (A2AContext ctx, EventQueue queue) ->
        // A2A 协议：先发 WORKING，告知发送方任务已开始处理
        queue.working(ctx)
            .thenCompose(v -> {
                // A2A 协议：Message 由多个 Part 组成，firstTextPart() 取第一个文本
                String text = ctx.firstTextPart().orElse("");
                String result = myTranslate(text); // 替换为你的翻译逻辑
                // A2A 协议：推送结果 Artifact，可多次调用实现流式输出
                return queue.artifact(ctx, "translation", result);
            })
            // A2A 协议：最后发 COMPLETED，标志任务结束
            .thenCompose(v -> queue.completed(ctx)),
    ConsumeOptions.builder()
        .groupName("demo.agent.translator.workers")
        .deliver("earliest")
        .numMsgs(10)
        .maxWaitMs(500)
        .build()
);

agentA.connect().join();
String mailbox = agentA.createMailbox("demo.agent.translator", 0).join();
System.out.println("mailbox: " + mailbox);
// agentA.register(card).join(); // 可选：发布到注册中心
```

### Agent B — 发现 Agent A 并发送任务

```java
import io.a2a.spec.*;
import io.mq9.ConsumeOptions;
import io.mq9.a2a.*;
import java.util.List;
import java.util.Map;

Mq9A2AAgent agentB = Mq9A2AAgent.builder().build();

// 所有消息都到这里——包括结果回包和其他 Agent 主动发来的新任务
// 通过 context.taskId 区分：和自己发出的 task_id 对上了就是回包，否则是新任务
agentB.onMessage(
    (A2AContext ctx, EventQueue queue) -> {
        System.out.println("收到事件 task_id=" + ctx.taskId);
        ctx.firstTextPart().ifPresent(t -> System.out.println("内容：" + t));
        return CompletableFuture.completedFuture(null);
    },
    ConsumeOptions.builder()
        .groupName("demo.agent.sender.workers")
        .deliver("earliest")
        .numMsgs(10)
        .maxWaitMs(500)
        .build()
);

agentB.connect().join();
String bMailbox = agentB.createMailbox("demo.agent.sender", 300).join();

// 发现 Agent A
List<Map<String, Object>> agents = agentB.discover("translation", false, 5).join();
Map<String, Object> target = agents.get(0);

// 构造 A2A 消息，message body 由一个或多个 Part 组成
Message msg = new Message.Builder()
        .role(Message.Role.USER)
        .parts(new TextPart("你好，世界"))
        .build();
SendMessageRequest request = new SendMessageRequest(
        null, new MessageSendParams(msg, null, null));

// sendMessage 返回 msg_id；task_id 由 Agent A（执行方）生成
// 随回包事件到达，从 context.taskId 读取
long msgId = agentB.sendMessage(target, request, bMailbox).join();
System.out.println("已发送，msg_id=" + msgId);

Thread.sleep(10_000); // 等待回包通过 onMessage 到达
agentB.close();
```

---

## Mq9A2AAgent

```java
Mq9A2AAgent agent = Mq9A2AAgent.builder()
        .server("nats://demo.robustmq.com:4222")
        .requestTimeoutMs(60_000)
        .build();
```

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `server` | `String` | mq9 broker 的 NATS 地址。默认 `nats://demo.robustmq.com:4222` |
| `requestTimeoutMs` | `long` | 请求超时时间，毫秒，默认 `60000` |

### `connect()`

连接 broker，返回 `CompletableFuture<Void>`。所有操作前必须先调用。

### `close()`

停止消费消息并断开 broker 连接。积压消息处理完毕后调用。

### `onMessage(handler)`

注册消息处理函数，使用默认消费者参数：

```java
agent.onMessage((ctx, queue) ->
    queue.working(ctx)
        .thenCompose(v -> queue.artifact(ctx, "result", myProcess(ctx)))
        .thenCompose(v -> queue.completed(ctx))
);
```

### `onMessage(handler, options)`

注册消息处理函数，同时指定消费者参数：

```java
agent.onMessage(handler, ConsumeOptions.builder()
        .groupName("my-agent.workers")
        .deliver("earliest")
        .numMsgs(10)
        .maxWaitMs(500)
        .build());
```

`ConsumeOptions` 参数说明：

| 参数 | 说明 |
| --- | --- |
| `groupName` | 消费组名称。不填时自动使用 `{mailbox名}.workers`，保证重启后从断点续消费 |
| `deliver` | 消费起点：`"earliest"`（默认）从最早未消费处开始，`"latest"` 只消费新消息 |
| `numMsgs` | 每次 fetch 批量拉取的消息数，默认 `10` |
| `maxWaitMs` | 每次 fetch 无消息时的最长等待时间，毫秒，默认 `500` |

### `createMailbox(name, ttl)`

创建 mailbox 并在后台启动消费者，返回 `CompletableFuture<String>`（mailbox 地址）。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `String` | mailbox 名称，通常使用 `AgentCard.name()` |
| `ttl` | `long` | Mailbox 存活时间，秒（`0` 表示永久） |

创建后即可接收消息，无需注册到注册中心。

### `register(card)`

将 Agent 身份发布到注册中心，其他 Agent 可通过 `discover()` 找到此 Agent。

参数：`card` — `io.a2a.spec.AgentCard`。必须在 `createMailbox()` 之后调用。返回 `CompletableFuture<Void>`。

### `unregister()`

从注册中心注销，返回 `CompletableFuture<Void>`。连接和消费者保持运行，积压消息仍可继续处理。处理完毕后调用 `close()`。

### `discover(query, semantic, limit)`

按自然语言描述在注册中心发现其他 Agent，返回 `CompletableFuture<List<Map<String, Object>>>`。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `query` | `String` | 自然语言查询字符串；传 `null` 列出全部 |
| `semantic` | `boolean` | `true` 向量语义搜索；`false` 关键词匹配 |
| `limit` | `int` | 返回结果数上限 |

每个结果 Map 包含 `name`、`mailbox`、`agent_card` 等字段。

### `sendMessage(mailAddress, request, replyTo)`

向另一个 Agent 发送消息，返回 `CompletableFuture<Long>`（`msg_id`）。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `mailAddress` | `Object` | `discover()` 返回的 Agent 信息 `Map`（需含 `mailbox`），或直接传 mailbox 地址字符串 |
| `request` | `SendMessageRequest` | A2A 消息请求对象 |
| `replyTo` | `String` | 自己的 mailbox 地址；`null` 表示单向发送 |

返回 broker 分配的 `msg_id`，表示消息已成功入队。`task_id` 由执行方（接收任务的 Agent）生成，随回包事件到达，从 `context.taskId` 读取。

---

## Handler 数据类型

### `A2AContext`

| 字段 / 方法 | 类型 | 说明 |
| --- | --- | --- |
| `ctx.taskId` | `String` | 任务 ID，由执行方生成 |
| `ctx.contextId` | `String` | 上下文/会话 ID |
| `ctx.message` | `io.a2a.spec.Message` | 传入的 A2A 消息 |
| `ctx.currentTask` | `io.a2a.spec.Task` | 已有任务（续接多轮对话时不为空） |
| `ctx.firstTextPart()` | `Optional<String>` | 取消息第一个文本 Part，避免手写空值检查 |

### `EventQueue`

`EventQueue` 提供 helper 方法，无需每次构造 Builder 链：

| 方法 | 说明 |
| --- | --- |
| `queue.working(ctx)` | 发送 `WORKING` 状态 |
| `queue.artifact(ctx, name, text)` | 发送文本结果 Artifact |
| `queue.completed(ctx)` | 发送 `COMPLETED`（终态） |
| `queue.failed(ctx)` | 发送 `FAILED`（终态） |
| `queue.enqueue(event)` | 发送任意 A2A 事件（需手动构造） |

A2A 协议规定的标准事件流程：

```java
queue.working(ctx)
    .thenCompose(v -> queue.artifact(ctx, "result", output))
    .thenCompose(v -> queue.completed(ctx))
```
