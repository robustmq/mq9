# mq9 C# Demo

Requires .NET 8+ and a running mq9 broker (or use the public demo server).

```bash
# Message demo — mailbox, send/fetch/ack, priority, dedup, tags, delay, query, delete
dotnet run --project demo.csproj -- message

# Agent demo — register, heartbeat, full-text search, semantic search, send to discovered agent
dotnet run --project demo.csproj -- agent
```

Default server: `nats://demo.robustmq.com:4222`

Override: `MQ9_SERVER=nats://localhost:4222 dotnet run --project demo.csproj -- message`
