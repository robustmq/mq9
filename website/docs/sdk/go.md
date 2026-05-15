---
title: Go SDK — mq9
description: mq9 Go SDK API reference and usage guide.
---

# Go SDK

## Install

```bash
go get github.com/robustmq/mq9/go
```

Requires Go 1.21+.

## Quick start

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

    // Create a mailbox
    address, err := client.MailboxCreate(ctx, "agent.inbox", 3600)
    if err != nil {
        log.Fatal(err)
    }

    // Send a message
    msgId, err := client.Send(ctx, address, []byte(`{"task":"analyze"}`), mq9.SendOptions{})
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println("sent:", msgId)

    // Consume messages
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

**Options:**

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

## Mailbox

### MailboxCreate

```go
client.MailboxCreate(ctx context.Context, name string, ttl int64) (string, error)
```

- `name = ""` — broker auto-generates the address.
- `ttl = 0` — never expires.

```go
address, err := client.MailboxCreate(ctx, "agent.inbox", 3600)
address, err := client.MailboxCreate(ctx, "", 7200) // auto-generated
```

---

## Messaging

### Send

```go
client.Send(ctx context.Context, mailAddress string, payload []byte, opts mq9.SendOptions) (int64, error)
```

```go
type SendOptions struct {
    Priority Priority  // default PriorityNormal
    Key      string    // dedup key; empty = no dedup
    Delay    int64     // seconds; 0 = no delay
    TTL      int64     // message-level TTL; 0 = no TTL
    Tags     []string
}
```

```go
// Normal send
msgId, err := client.Send(ctx, "agent.inbox", []byte(`{"task":"analyze"}`), mq9.SendOptions{})

// Urgent priority
msgId, err := client.Send(ctx, "agent.inbox", []byte("alert"), mq9.SendOptions{
    Priority: mq9.PriorityUrgent,
})

// Dedup key
msgId, err := client.Send(ctx, "task.status", payload, mq9.SendOptions{Key: "state"})

// Delayed delivery
msgId, err := client.Send(ctx, "agent.inbox", payload, mq9.SendOptions{Delay: 60})
```

### Fetch

```go
client.Fetch(ctx context.Context, mailAddress string, opts mq9.FetchOptions) ([]mq9.Message, error)
```

```go
type FetchOptions struct {
    GroupName    string   // omit for stateless
    Deliver      string   // "latest"|"earliest"|"from_time"|"from_id"; default "latest"
    FromTime     int64    // unix timestamp
    FromID       int64
    ForceDeliver bool
    NumMsgs      int      // default 100
    MaxWaitMs    int64    // default 500
}
```

```go
// Stateless
messages, err := client.Fetch(ctx, "task.inbox", mq9.FetchOptions{Deliver: "earliest"})

// Stateful
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

- Handler returns non-nil error → message **not ACKed**, `ErrorHandler` called, loop continues.

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
// key="", limit=0, since=0 → omitted from request
```

### Delete

```go
client.Delete(ctx context.Context, mailAddress string, msgID int64) error
```

---

## Agent management

### AgentRegister

```go
client.AgentRegister(ctx context.Context, agentCard map[string]any) error
// agentCard must contain "mailbox" key
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
// text="", semantic="" → omitted; limit=0 → default 20; page=0 → default 1
```

---

## Data types

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
    CreateTime int64    // unix timestamp (seconds)
}
```

### Consumer

```go
func (c *Consumer) IsRunning() bool
func (c *Consumer) ProcessedCount() int64
func (c *Consumer) Stop()  // blocks until the loop exits
```

### Mq9Error

```go
type Mq9Error struct {
    Message string
}
func (e *Mq9Error) Error() string
```
