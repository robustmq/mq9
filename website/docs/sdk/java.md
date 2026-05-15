---
title: Java SDK — mq9
description: mq9 Java SDK API reference and usage guide.
---

# Java SDK

## Install

**Maven:**

```xml
<dependency>
  <groupId>io.mq9</groupId>
  <artifactId>mq9</artifactId>
  <version>0.1.0</version>
</dependency>
```

**Gradle:**

```groovy
implementation 'io.mq9:mq9:0.1.0'
```

Requires Java 17+.

## Quick start

```java
import io.mq9.*;
import java.util.concurrent.CompletableFuture;

public class Example {
    public static void main(String[] args) throws Exception {
        Mq9Client client = Mq9Client.connect("nats://localhost:4222").get();

        // Create a mailbox
        String address = client.mailboxCreate("agent.inbox", 3600).get();

        // Send a message
        long msgId = client.send(address, "hello world".getBytes(),
            SendOptions.builder().build()).get();
        System.out.println("sent: " + msgId);

        // Consume messages
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
// Static factory — returns CompletableFuture<Mq9Client>
Mq9Client.connect(String server)
Mq9Client.connect(String server, ClientOptions options)
```

```java
ClientOptions options = ClientOptions.builder()
    .requestTimeout(Duration.ofSeconds(10))
    .build();
Mq9Client client = Mq9Client.connect("nats://localhost:4222", options).get();
```

Implements `AutoCloseable`:

```java
try (Mq9Client client = Mq9Client.connect("nats://localhost:4222").get()) {
    // ...
}
```

---

## Mailbox

### mailboxCreate

```java
CompletableFuture<String> mailboxCreate(String name, long ttl)
```

- `name = null` — broker auto-generates the address.
- `ttl = 0` — never expires.

```java
String address = client.mailboxCreate("agent.inbox", 3600).get();
String address = client.mailboxCreate(null, 7200).get(); // auto-generated
```

---

## Messaging

### send

```java
CompletableFuture<Long> send(String mailAddress, byte[] payload, SendOptions options)
```

```java
SendOptions options = SendOptions.builder()
    .priority(Priority.URGENT)
    .key("state")          // dedup key
    .delay(60L)            // delay seconds
    .ttl(300L)             // message TTL seconds
    .tags(List.of("billing", "vip"))
    .build();
```

```java
// Normal send
long msgId = client.send("agent.inbox", "hello".getBytes(),
    SendOptions.builder().build()).get();

// Urgent priority
long msgId = client.send("agent.inbox", "alert".getBytes(),
    SendOptions.builder().priority(Priority.URGENT).build()).get();

// Dedup key
long msgId = client.send("task.status", payload,
    SendOptions.builder().key("state").build()).get();
```

### fetch

```java
CompletableFuture<List<Message>> fetch(String mailAddress, FetchOptions options)
```

```java
FetchOptions options = FetchOptions.builder()
    .groupName("workers")      // omit for stateless
    .deliver("earliest")       // "latest"|"earliest"|"from_time"|"from_id"
    .numMsgs(50)
    .maxWaitMs(1000L)
    .forceDeliver(false)
    .build();
```

```java
// Stateless
List<Message> messages = client.fetch("task.inbox",
    FetchOptions.builder().deliver("earliest").build()).get();

// Stateful
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

- Handler throws / completes exceptionally → message **not ACKed**, `errorHandler` called, loop continues.

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
// key=null, limit=null, since=null → omitted from request
```

### delete

```java
CompletableFuture<Void> delete(String mailAddress, long msgId)
```

---

## Agent management

### agentRegister

```java
CompletableFuture<Void> agentRegister(Map<String, Object> agentCard)
// agentCard must contain "mailbox" key
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
// text=null, semantic=null → omitted; limit=null → default 20; page=null → default 1
```

---

## Data types

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
    public final long createTime;   // unix timestamp (seconds)
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
// Unchecked exception
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
