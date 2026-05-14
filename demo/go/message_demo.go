// mq9 Go SDK — Message Demo
//
// Demonstrates:
//  1. Create a mailbox
//  2. Send messages with different priorities
//  3. Fetch + ACK (stateful consumption)
//  4. Consume loop (auto poll)
//  5. Message attributes: key dedup, tags, delay, ttl
//  6. Query without affecting offset
//  7. Delete a message
//
// Run: go run message_demo.go

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	mq9 "github.com/robustmq/mq9/go"
)

const server = "nats://demo.robustmq.com:4222"

func main() {
	client, err := mq9.Connect(server)
	if err != nil {
		log.Fatal(err)
	}
	defer client.Close()

	ctx := context.Background()

	// ── 1. Create a mailbox ──────────────────────────────────────────────
	address, err := client.MailboxCreate(ctx, "demo.go.message", 300)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("[mailbox] created: %s\n", address)

	// ── 2. Send messages with different priorities ───────────────────────
	mid1, _ := client.Send(ctx, address, jsonBytes(map[string]any{"type": "task", "id": 1}), mq9.SendOptions{})
	fmt.Printf("[send] normal    msg_id=%d\n", mid1)

	mid2, _ := client.Send(ctx, address, jsonBytes(map[string]any{"type": "interrupt", "id": 2}), mq9.SendOptions{
		Priority: mq9.PriorityUrgent,
	})
	fmt.Printf("[send] urgent    msg_id=%d\n", mid2)

	mid3, _ := client.Send(ctx, address, jsonBytes(map[string]any{"type": "abort", "id": 3}), mq9.SendOptions{
		Priority: mq9.PriorityCritical,
	})
	fmt.Printf("[send] critical  msg_id=%d\n", mid3)

	// ── 3. Message attributes ────────────────────────────────────────────
	// Key dedup: only the latest message with key="status" is kept
	client.Send(ctx, address, jsonBytes(map[string]any{"status": "running"}), mq9.SendOptions{Key: "status"})
	client.Send(ctx, address, jsonBytes(map[string]any{"status": "60%"}),     mq9.SendOptions{Key: "status"})
	midStatus, _ := client.Send(ctx, address, jsonBytes(map[string]any{"status": "done"}), mq9.SendOptions{Key: "status"})
	fmt.Printf("[send] dedup key=status, latest msg_id=%d\n", midStatus)

	// Tags
	client.Send(ctx, address, jsonBytes(map[string]any{"order": "o-001"}), mq9.SendOptions{
		Tags: []string{"billing", "vip"},
	})
	fmt.Println("[send] with tags billing,vip")

	// Per-message TTL
	client.Send(ctx, address, jsonBytes(map[string]any{"temp": true}), mq9.SendOptions{TTL: 10})
	fmt.Println("[send] with message ttl=10s")

	// Delayed delivery
	delayedID, _ := client.Send(ctx, address, jsonBytes(map[string]any{"delayed": true}), mq9.SendOptions{Delay: 5})
	fmt.Printf("[send] delay=5s  msg_id=%d (returns -1 for delayed)\n", delayedID)

	// ── 4. Fetch + ACK (stateful) ────────────────────────────────────────
	messages, err := client.Fetch(ctx, address, mq9.FetchOptions{
		GroupName: "workers",
		Deliver:   "earliest",
		NumMsgs:   10,
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("\n[fetch] got %d messages (priority order):\n", len(messages))
	for _, msg := range messages {
		fmt.Printf("  msg_id=%d  priority=%s  payload=%s\n", msg.MsgID, msg.Priority, msg.Payload)
	}

	if len(messages) > 0 {
		last := messages[len(messages)-1]
		client.Ack(ctx, address, "workers", last.MsgID)
		fmt.Printf("[ack]   advanced offset to msg_id=%d\n", last.MsgID)
	}

	// ── 5. Query without affecting offset ────────────────────────────────
	results, _ := client.Query(ctx, address, "status", 0, 0)
	fmt.Printf("\n[query] key=status → %d message(s)\n", len(results))
	for _, msg := range results {
		fmt.Printf("  msg_id=%d  payload=%s\n", msg.MsgID, msg.Payload)
	}

	// ── 6. Consume loop ──────────────────────────────────────────────────
	fmt.Println("\n[consume] starting loop for 3 s …")

	consumer, err := client.Consume(ctx, address, func(msg mq9.Message) error {
		fmt.Printf("  [handler] msg_id=%d  priority=%s  payload=%s\n", msg.MsgID, msg.Priority, msg.Payload)
		return nil
	}, mq9.ConsumeOptions{
		GroupName: "consume-workers",
		Deliver:   "earliest",
		AutoAck:   true,
		ErrorHandler: func(msg mq9.Message, err error) {
			fmt.Printf("  [error]   msg_id=%d  error=%v\n", msg.MsgID, err)
		},
	})
	if err != nil {
		log.Fatal(err)
	}

	time.Sleep(3 * time.Second)
	consumer.Stop()
	fmt.Printf("[consume] stopped. processed=%d\n", consumer.ProcessedCount())

	// ── 7. Delete a message ──────────────────────────────────────────────
	client.Delete(ctx, address, mid1)
	fmt.Printf("\n[delete] msg_id=%d deleted\n", mid1)
}

func jsonBytes(v any) []byte {
	b, _ := json.Marshal(v)
	return b
}
