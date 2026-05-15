---
title: C# SDK — mq9
description: mq9 C# SDK API reference and usage guide.
---

# C# SDK

## Install

```bash
dotnet add package mq9
```

Requires .NET 8+.

## Quick start

```csharp
using Mq9;

await using var client = new Mq9Client("nats://localhost:4222");
await client.ConnectAsync();

// Create a mailbox
var address = await client.MailboxCreateAsync(name: "agent.inbox", ttl: 3600);

// Send a message
var msgId = await client.SendAsync(address, "hello world"u8.ToArray());

// Consume messages
var consumer = await client.ConsumeAsync(address, async msg => {
    Console.WriteLine(System.Text.Encoding.UTF8.GetString(msg.Payload));
}, new ConsumeOptions { GroupName = "workers" });

await Task.Delay(10_000);
await consumer.StopAsync();
await client.CloseAsync();
```

## Mq9Client

```csharp
new Mq9Client(
    string server,
    ClientOptions? options = null
)
```

```csharp
public class ClientOptions
{
    public TimeSpan RequestTimeout { get; set; }  = TimeSpan.FromSeconds(5);
    public int      ReconnectAttempts { get; set; } = 5;
    public TimeSpan ReconnectDelay { get; set; }  = TimeSpan.FromSeconds(2);
}
```

Implements `IAsyncDisposable` — use `await using` for automatic cleanup:

```csharp
await using var client = new Mq9Client("nats://localhost:4222");
await client.ConnectAsync();
// client.CloseAsync() called automatically on scope exit
```

### ConnectAsync / CloseAsync

```csharp
await client.ConnectAsync();
await client.CloseAsync();
```

---

## Mailbox

### MailboxCreateAsync

```csharp
Task<string> MailboxCreateAsync(
    string? name = null,   // null → broker auto-generates address
    long    ttl  = 0       // seconds; 0 = never expires
)
```

```csharp
var address = await client.MailboxCreateAsync(name: "agent.inbox", ttl: 3600);
var address = await client.MailboxCreateAsync(ttl: 7200); // auto-generated
```

---

## Messaging

### SendAsync

```csharp
Task<long> SendAsync(
    string   mailAddress,
    byte[]   payload,
    SendOptions? options = null
)
// returns msg_id; -1 for delayed messages
```

```csharp
public class SendOptions
{
    public Priority   Priority { get; set; } = Priority.Normal;
    public string?    Key      { get; set; }        // dedup key
    public long?      Delay    { get; set; }        // seconds
    public long?      Ttl      { get; set; }        // message-level TTL in seconds
    public string[]?  Tags     { get; set; }
}
```

```csharp
// Normal send
var msgId = await client.SendAsync(address, Encoding.UTF8.GetBytes("hello"));

// Urgent priority
var msgId = await client.SendAsync(address, payload, new SendOptions {
    Priority = Priority.Urgent
});

// Dedup key — broker keeps only the latest message for the same key
var msgId = await client.SendAsync("task.status", payload, new SendOptions {
    Key = "state"
});

// Delayed delivery
var msgId = await client.SendAsync(address, payload, new SendOptions {
    Delay = 60
});

// With tags
var msgId = await client.SendAsync("orders.inbox", payload, new SendOptions {
    Tags = ["billing", "vip"]
});
```

### FetchAsync

```csharp
Task<List<Mq9Message>> FetchAsync(
    string       mailAddress,
    FetchOptions? options = null
)
```

```csharp
public class FetchOptions
{
    public string?  GroupName    { get; set; }            // null → stateless
    public string   Deliver      { get; set; } = "latest"; // "latest"|"earliest"|"from_time"|"from_id"
    public long?    FromTime     { get; set; }            // unix timestamp
    public long?    FromId       { get; set; }
    public bool     ForceDeliver { get; set; }
    public int      NumMsgs      { get; set; } = 100;
    public long     MaxWaitMs    { get; set; } = 500;
}
```

```csharp
// Stateless — each call starts fresh
var messages = await client.FetchAsync("task.inbox",
    new FetchOptions { Deliver = "earliest" });

// Stateful — broker records offset per group
var messages = await client.FetchAsync("task.inbox",
    new FetchOptions { GroupName = "workers" });
foreach (var msg in messages)
{
    await client.AckAsync("task.inbox", "workers", msg.MsgId);
}
```

### AckAsync

```csharp
Task AckAsync(string mailAddress, string groupName, long msgId)
```

### ConsumeAsync

Runs an automatic fetch loop in the background. Returns immediately.

```csharp
Task<Consumer> ConsumeAsync(
    string                         mailAddress,
    Func<Mq9Message, Task>         handler,
    ConsumeOptions?                options = null
)
```

```csharp
public class ConsumeOptions
{
    public string?                        GroupName    { get; set; }
    public string                         Deliver      { get; set; } = "latest";
    public int                            NumMsgs      { get; set; } = 10;
    public long                           MaxWaitMs    { get; set; } = 500;
    public bool                           AutoAck      { get; set; } = true;
    public Func<Mq9Message, Exception, Task>? ErrorHandler { get; set; }
}
```

- Handler throws → message **not ACKed**, `ErrorHandler` called, loop continues.
- `StopAsync()` drains the current batch and exits cleanly.

```csharp
var consumer = await client.ConsumeAsync("task.inbox", async msg => {
    var text = Encoding.UTF8.GetString(msg.Payload);
    Console.WriteLine(text);
}, new ConsumeOptions {
    GroupName = "workers",
    ErrorHandler = async (msg, ex) => {
        Console.Error.WriteLine($"msg {msg.MsgId} failed: {ex.Message}");
    }
});

await Task.Delay(30_000);
await consumer.StopAsync();
Console.WriteLine($"processed: {consumer.ProcessedCount}");
```

### QueryAsync

Inspect mailbox contents without affecting consumption offset.

```csharp
Task<List<Mq9Message>> QueryAsync(
    string  mailAddress,
    string? key   = null,
    long?   limit = null,
    long?   since = null   // unix timestamp
)
```

### DeleteAsync

```csharp
Task DeleteAsync(string mailAddress, long msgId)
```

---

## Agent management

### AgentRegisterAsync

```csharp
Task AgentRegisterAsync(Dictionary<string, object> agentCard)
// agentCard must contain "mailbox" key
```

### AgentUnregisterAsync

```csharp
Task AgentUnregisterAsync(string mailbox)
```

### AgentReportAsync

```csharp
Task AgentReportAsync(Dictionary<string, object> report)
```

### AgentDiscoverAsync

```csharp
Task<List<Dictionary<string, object>>> AgentDiscoverAsync(
    string? text     = null,
    string? semantic = null,
    int     limit    = 20,
    int     page     = 1
)
```

```csharp
// Full-text search
var agents = await client.AgentDiscoverAsync(text: "payment invoice");

// Semantic search
var agents = await client.AgentDiscoverAsync(semantic: "process a refund request");

// List all
var agents = await client.AgentDiscoverAsync();
```

---

## Data types

### Priority

```csharp
public enum Priority
{
    Normal,    // default
    Urgent,
    Critical
}
```

`Critical > Urgent > Normal`. Same-priority messages follow FIFO.

### Mq9Message

```csharp
public class Mq9Message
{
    public long     MsgId      { get; init; }
    public byte[]   Payload    { get; init; }
    public Priority Priority   { get; init; }
    public long     CreateTime { get; init; }  // unix timestamp (seconds)
}
```

### Consumer

```csharp
public class Consumer
{
    public bool IsRunning      { get; }
    public long ProcessedCount { get; }
    public Task StopAsync();
}
```

### Mq9Error

```csharp
public class Mq9Error : Exception
{
    public Mq9Error(string message) : base(message) { }
}
```

```csharp
using Mq9;

try
{
    await client.MailboxCreateAsync(name: "agent.inbox");
}
catch (Mq9Error e)
{
    Console.Error.WriteLine(e.Message); // "mailbox agent.inbox already exists"
}
```
