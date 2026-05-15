---
title: Go SDK — mq9
description: mq9 Go SDK API 参考与使用指南。
---

# Go SDK

## 安装

```bash
go get github.com/robustmq/mq9/go
```

需要 Go 1.21+。

## 快速开始

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    mq9 "github.com/robustmq/mq9/go"
)

func main() {
    client, err := mq9.Connect("nats://localhost:4222")
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    ctx := context.Background()

    // 创建邮箱
    address, err := client.MailboxCreate(ctx, "agent.inbox", 3600)
    if err != nil {
        log.Fatal(err)
    }

    // 发送消息
    msgId, err := client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{})
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println("sent:", msgId)

    // 消费消息
    consumer, err := client.Consume(ctx, address, func(msg mq9.Message) error {
        fmt.Printf("received: %s\n", msg.Payload)
        return nil
    }, mq9.ConsumeOptions{GroupName: "workers", AutoAck: true})
    if err != nil {
        log.Fatal(err)
    }

    time.Sleep(10 * time.Second)
    consumer.Stop()
}
```

## Connect

```go
client, err := mq9.Connect(server string, opts ...mq9.Option) (*mq9.Client, error)
```

**选项：**

```go
mq9.WithRequestTimeout(5 * time.Second)
mq9.WithReconnectDelay(2 * time.Second)
```

```go
client, err := mq9.Connect("nats://localhost:4222",
    mq9.WithRequestTimeout(10*time.Second),
)
```

### Close

```go
client.Close() error
```

---

## 邮箱

### MailboxCreate

```go
client.MailboxCreate(ctx context.Context, name string, ttl int64) (string, error)
```

- `name = ""` — broker 自动生成地址。
- `ttl = 0` — 永不过期。

```go
address, err := client.MailboxCreate(ctx, "agent.inbox", 3600)
address, err := client.MailboxCreate(ctx, "", 7200) // 自动生成
```

---

## 消息收发

### Send

```go
client.Send(ctx context.Context, mailAddress string, payload []byte, opts mq9.SendOptions) (int64, error)
```

```go
type SendOptions struct {
    Priority Priority  // 默认 PriorityNormal
    Key      string    // 去重键；空字符串表示不去重
    Delay    int64     // 秒；0 = 不延迟
    TTL      int64     // 消息级别 TTL；0 = 无 TTL
    Tags     []string
}
```

```go
// 普通发送
msgId, err := client.Send(ctx, "agent.inbox", []byte(`{"task":"analyze"}`), mq9.SendOptions{})

// 紧急优先级
msgId, err := client.Send(ctx, "agent.inbox", []byte("alert"), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
})

// 去重键
msgId, err := client.Send(ctx, "task.status", payload, mq9.SendOptions{Key: "state"})

// 延迟投递
msgId, err := client.Send(ctx, "agent.inbox", payload, mq9.SendOptions{Delay: 60})
```

### Fetch

```go
client.Fetch(ctx context.Context, mailAddress string, opts mq9.FetchOptions) ([]mq9.Message, error)
```

```go
type FetchOptions struct {
    GroupName    string   // 省略则为无状态
    Deliver      string   // "latest"|"earliest"|"from_time"|"from_id"；默认 "latest"
    FromTime     int64    // Unix 时间戳
    FromID       int64
    ForceDeliver bool
    NumMsgs      int      // 默认 100
    MaxWaitMs    int64    // 默认 500
}
```

```go
// 无状态
messages, err := client.Fetch(ctx, "task.inbox", mq9.FetchOptions{Deliver: "earliest"})

// 有状态
messages, err := client.Fetch(ctx, "task.inbox", mq9.FetchOptions{GroupName: "workers"})
for _, msg := range messages {
    client.Ack(ctx, "task.inbox", "workers", msg.MsgID)
}
```

### Ack

```go
client.Ack(ctx context.Context, mailAddress string, groupName string, msgID int64) error
```

### Consume

```go
client.Consume(
    ctx context.Context,
    mailAddress string,
    handler func(mq9.Message) error,
    opts mq9.ConsumeOptions,
) (*mq9.Consumer, error)
```

```go
type ConsumeOptions struct {
    GroupName    string
    Deliver      string
    NumMsgs      int
    MaxWaitMs    int64
    AutoAck      bool
    ErrorHandler func(msg Message, err error)
}
```

- handler 返回非 nil 错误 → 消息**不会被 ACK**，调用 `ErrorHandler`，循环继续。

```go
consumer, err := client.Consume(ctx, "task.inbox", func(msg mq9.Message) error {
    fmt.Println(string(msg.Payload))
    return nil
}, mq9.ConsumeOptions{
    GroupName: "workers",
    AutoAck:   true,
    ErrorHandler: func(msg mq9.Message, err error) {
        log.Printf("msg %d failed: %v", msg.MsgID, err)
    },
})

time.Sleep(30 * time.Second)
consumer.Stop()
fmt.Println(consumer.ProcessedCount())
```

### Query

```go
client.Query(ctx context.Context, mailAddress string, key string, limit int64, since int64) ([]mq9.Message, error)
// key=""、limit=0、since=0 → 不传入请求
```

### Delete

```go
client.Delete(ctx context.Context, mailAddress string, msgID int64) error
```

---

## Agent 管理

### AgentRegister

```go
client.AgentRegister(ctx context.Context, agentCard map[string]any) error
// agentCard 必须包含 "mailbox" 键
```

### AgentUnregister

```go
client.AgentUnregister(ctx context.Context, mailbox string) error
```

### AgentReport

```go
client.AgentReport(ctx context.Context, report map[string]any) error
```

### AgentDiscover

```go
client.AgentDiscover(ctx context.Context, text string, semantic string, limit int, page int) ([]map[string]any, error)
// text=""、semantic="" → 省略；limit=0 → 默认 20；page=0 → 默认 1
```

---

## 数据类型

### Priority

```go
type Priority string

const (
    PriorityNormal   Priority = "normal"
    PriorityUrgent   Priority = "urgent"
    PriorityCritical Priority = "critical"
)
```

### Message

```go
type Message struct {
    MsgID      int64
    Payload    []byte
    Priority   Priority
    CreateTime int64    // Unix 时间戳（秒）
}
```

### Consumer

```go
func (c *Consumer) IsRunning() bool
func (c *Consumer) ProcessedCount() int64
func (c *Consumer) Stop()  // 阻塞直到循环退出
```

### Mq9Error

```go
type Mq9Error struct {
    Message string
}
func (e *Mq9Error) Error() string
```
