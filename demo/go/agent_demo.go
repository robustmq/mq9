// mq9 Go SDK — Agent Demo
//
// Demonstrates:
//  1. Agent registers its capabilities
//  2. Agent sends heartbeat via report
//  3. Discover by full-text search
//  4. Discover by semantic search
//  5. Send a task to discovered agent's mailbox
//  6. Agent unregisters at shutdown
//
// Run: go run agent_demo.go

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

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

	// ── 1. Create mailbox for the agent ─────────────────────────────────
	address, err := client.MailboxCreate(ctx, "demo.go.translator", 300)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("[mailbox] agent mailbox: %s\n", address)

	// ── 2. Register agent ────────────────────────────────────────────────
	err = client.AgentRegister(ctx, map[string]any{
		"name":    "demo.go.translator",
		"mailbox": address,
		"payload": "Multilingual translation agent. Supports EN, ZH, JA, KO. Input: text + target language. Output: translated text.",
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("[register] agent registered: demo.go.translator")

	// ── 3. Send heartbeat ────────────────────────────────────────────────
	client.AgentReport(ctx, map[string]any{
		"name":        "demo.go.translator",
		"mailbox":     address,
		"report_info": "running, processed: 256 tasks, avg latency: 280ms",
	})
	fmt.Println("[report] heartbeat sent")

	// ── 4. Discover by full-text search ──────────────────────────────────
	byText, _ := client.AgentDiscover(ctx, "translator", "", 5, 1)
	fmt.Printf("\n[discover] text='translator' → %d result(s):\n", len(byText))
	for _, a := range byText {
		fmt.Printf("  name=%v  mailbox=%v\n", a["name"], a["mailbox"])
	}

	// ── 5. Discover by semantic search ───────────────────────────────────
	bySemantic, _ := client.AgentDiscover(ctx, "", "I need to translate Chinese text into English", 5, 1)
	fmt.Printf("\n[discover] semantic='translate Chinese to English' → %d result(s):\n", len(bySemantic))
	for _, a := range bySemantic {
		fmt.Printf("  name=%v  mailbox=%v\n", a["name"], a["mailbox"])
	}

	// ── 6. Send a task to discovered agent ───────────────────────────────
	if len(bySemantic) > 0 {
		target, _ := bySemantic[0]["mailbox"].(string)
		if target != "" {
			replyAddress, _ := client.MailboxCreate(ctx, "", 60)
			payload, _ := json.Marshal(map[string]any{
				"text":        "你好，世界",
				"target_lang": "en",
				"reply_to":    replyAddress,
			})
			msgID, _ := client.Send(ctx, target, payload, mq9.SendOptions{})
			fmt.Printf("\n[send] task sent to %s  msg_id=%d\n", target, msgID)
			fmt.Printf("[send] reply_to=%s\n", replyAddress)
		}
	}

	// ── 7. List all agents ────────────────────────────────────────────────
	all, _ := client.AgentDiscover(ctx, "", "", 20, 1)
	fmt.Printf("\n[discover] all agents → %d registered\n", len(all))

	// ── 8. Unregister ─────────────────────────────────────────────────────
	client.AgentUnregister(ctx, address)
	fmt.Printf("\n[unregister] agent %s unregistered\n", address)
}
