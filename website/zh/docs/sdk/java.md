---
title: Java SDK — mq9
description: mq9 Java SDK API 参考与使用指南。
---

# Java SDK

## 安装

**Maven：**

```xml
<dependency>
  <groupId>io.mq9</groupId>
  <artifactId>mq9</artifactId>
  <version>0.1.0</version>
</dependency>
```

**Gradle：**

```groovy
implementation 'io.mq9:mq9:0.1.0'
```

需要 Java 17+。

## 快速开始

```java
import io.mq9.*;
import java.util.concurrent.CompletableFuture;

public class Example {
    public static void main(String[] args) throws Exception {
        Mq9Client client = Mq9Client.connect("nats://localhost:4222").get();

        // 创建邮箱
        String address = client.mailboxCreate("agent.inbox", 3600).get();

        // 发送消息
        long msgId = client.send(address, "hello world".getBytes(),
            SendOptions.builder().build()).get();
        System.out.println("sent: " + msgId);

        // 消费消息
        Consumer consumer = client.consume(address, msg -> {
            System.out.println("received: " + new String(msg.payload));
            return CompletableFuture.completedFuture(null);
        }, ConsumeOptions.builder().groupName("workers").build()).get();

        Thread.sleep(10000);
        consumer.stop().get();
        client.close();
    }
}
```

## Mq9Client

```java
// 静态工厂方法 — 返回 CompletableFuture<Mq9Client>
Mq9Client.connect(String server)
Mq9Client.connect(String server, ClientOptions options)
```

```java
ClientOptions options = ClientOptions.builder()
    .requestTimeout(Duration.ofSeconds(10))
    .build();
Mq9Client client = Mq9Client.connect("nats://localhost:4222", options).get();
```

实现了 `AutoCloseable`：

```java
try (Mq9Client client = Mq9Client.connect("nats://localhost:4222").get()) {
    // ...
}
```

---

## 邮箱

### mailboxCreate

```java
CompletableFuture<String> mailboxCreate(String name, long ttl)
```

- `name = null` — broker 自动生成地址。
- `ttl = 0` — 永不过期。

```java
String address = client.mailboxCreate("agent.inbox", 3600).get();
String address = client.mailboxCreate(null, 7200).get(); // 自动生成
```

---

## 消息收发

### send

```java
CompletableFuture<Long> send(String mailAddress, byte[] payload, SendOptions options)
```

```java
SendOptions options = SendOptions.builder()
    .priority(Priority.URGENT)
    .key("state")          // 去重键
    .delay(60L)            // 延迟秒数
    .ttl(300L)             // 消息 TTL 秒数
    .tags(List.of("billing", "vip"))
    .build();
```

```java
// 普通发送
long msgId = client.send("agent.inbox", "hello".getBytes(),
    SendOptions.builder().build()).get();

// 紧急优先级
long msgId = client.send("agent.inbox", "alert".getBytes(),
    SendOptions.builder().priority(Priority.URGENT).build()).get();

// 去重键
long msgId = client.send("task.status", payload,
    SendOptions.builder().key("state").build()).get();
```

### fetch

```java
CompletableFuture<List<Message>> fetch(String mailAddress, FetchOptions options)
```

```java
FetchOptions options = FetchOptions.builder()
    .groupName("workers")      // 省略则为无状态
    .deliver("earliest")       // "latest"|"earliest"|"from_time"|"from_id"
    .numMsgs(50)
    .maxWaitMs(1000L)
    .forceDeliver(false)
    .build();
```

```java
// 无状态
List<Message> messages = client.fetch("task.inbox",
    FetchOptions.builder().deliver("earliest").build()).get();

// 有状态
List<Message> messages = client.fetch("task.inbox",
    FetchOptions.builder().groupName("workers").build()).get();
for (Message msg : messages) {
    client.ack("task.inbox", "workers", msg.msgId).get();
}
```

### ack

```java
CompletableFuture<Void> ack(String mailAddress, String groupName, long msgId)
```

### consume

```java
CompletableFuture<Consumer> consume(
    String mailAddress,
    Function<Message, CompletableFuture<Void>> handler,
    ConsumeOptions options
)
```

```java
ConsumeOptions options = ConsumeOptions.builder()
    .groupName("workers")
    .autoAck(true)
    .numMsgs(10)
    .errorHandler((msg, throwable) -> {
        System.err.println("msg " + msg.msgId + " failed: " + throwable.getMessage());
    })
    .build();
```

- handler 抛出异常或以异常完成 → 消息**不会被 ACK**，调用 `errorHandler`，循环继续。

```java
Consumer consumer = client.consume("task.inbox", msg -> {
    System.out.println(new String(msg.payload));
    return CompletableFuture.completedFuture(null);
}, ConsumeOptions.builder().groupName("workers").autoAck(true).build()).get();

Thread.sleep(30000);
consumer.stop().get();
System.out.println("processed: " + consumer.getProcessedCount());
```

### query

```java
CompletableFuture<List<Message>> query(String mailAddress, String key, Long limit, Long since)
// key=null、limit=null、since=null → 不传入请求
```

### delete

```java
CompletableFuture<Void> delete(String mailAddress, long msgId)
```

---

## Agent 管理

### agentRegister

```java
CompletableFuture<Void> agentRegister(Map<String, Object> agentCard)
// agentCard 必须包含 "mailbox" 键
```

### agentUnregister

```java
CompletableFuture<Void> agentUnregister(String mailbox)
```

### agentReport

```java
CompletableFuture<Void> agentReport(Map<String, Object> report)
```

### agentDiscover

```java
CompletableFuture<List<Map<String, Object>>> agentDiscover(
    String text, String semantic, Integer limit, Integer page
)
// text=null、semantic=null → 省略；limit=null → 默认 20；page=null → 默认 1
```

---

## 数据类型

### Priority

```java
public enum Priority {
    NORMAL("normal"),
    URGENT("urgent"),
    CRITICAL("critical");
}
```

### Message

```java
public class Message {
    public final long msgId;
    public final byte[] payload;
    public final Priority priority;
    public final long createTime;   // Unix 时间戳（秒）
}
```

### Consumer

```java
public class Consumer {
    public boolean isRunning();
    public long getProcessedCount();
    public CompletableFuture<Void> stop();
}
```

### Mq9Error

```java
// 非受检异常
public class Mq9Error extends RuntimeException {
    public Mq9Error(String message) { super(message); }
}
```

```java
try {
    client.mailboxCreate("agent.inbox", 3600).get();
} catch (ExecutionException e) {
    if (e.getCause() instanceof Mq9Error err) {
        System.err.println(err.getMessage());
    }
}
```
