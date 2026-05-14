# mq9 Demo

All demos connect to the public demo server `nats://demo.robustmq.com:4222`.

Each language has two demos:

| File | Description |
| ---- | ----------- |
| `message_demo` | Mailbox create, send with priority, fetch+ACK, consume loop, key dedup, tags, delay, ttl, query, delete |
| `agent_demo` | Agent register, heartbeat report, discover by text, discover by semantic, send to discovered agent, unregister |

## Run

| Language | Setup | Message demo | Agent demo |
| -------- | ----- | ------------ | ---------- |
| Python | `pip install mq9` | `python python/message_demo.py` | `python python/agent_demo.py` |
| JavaScript | `npm install mq9 tsx` | `npx tsx javascript/message_demo.ts` | `npx tsx javascript/agent_demo.ts` |
| Go | — | `go run go/message_demo.go` | `go run go/agent_demo.go` |
| Rust | — | `cargo run --bin message_demo` | `cargo run --bin agent_demo` |
| Java | add `io.mq9:mq9:0.1.0` | `java MessageDemo` | `java AgentDemo` |
