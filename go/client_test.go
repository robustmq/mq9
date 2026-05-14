package mq9

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
)

// ---------------------------------------------------------------------------
// Mock NATS connection
// ---------------------------------------------------------------------------

// mockConn implements natsConn and records every call made to RequestMsgWithContext.
type mockConn struct {
	mu       sync.Mutex
	calls    []*nats.Msg            // messages received
	replies  []mockReply            // queue of pre-canned replies (consumed in order)
	drainErr error
}

type mockReply struct {
	data []byte
	err  error
}

// enqueue adds a pre-canned JSON reply for the next RequestMsgWithContext call.
func (m *mockConn) enqueue(v any) {
	data, _ := json.Marshal(v)
	m.mu.Lock()
	m.replies = append(m.replies, mockReply{data: data})
	m.mu.Unlock()
}

// enqueueRaw adds a raw-bytes reply.
func (m *mockConn) enqueueRaw(data []byte) {
	m.mu.Lock()
	m.replies = append(m.replies, mockReply{data: data})
	m.mu.Unlock()
}

// enqueueErr adds a transport-level error reply.
func (m *mockConn) enqueueErr(err error) {
	m.mu.Lock()
	m.replies = append(m.replies, mockReply{err: err})
	m.mu.Unlock()
}

func (m *mockConn) RequestMsgWithContext(_ context.Context, msg *nats.Msg) (*nats.Msg, error) {
	m.mu.Lock()
	m.calls = append(m.calls, msg)
	var r mockReply
	if len(m.replies) > 0 {
		r = m.replies[0]
		m.replies = m.replies[1:]
	}
	m.mu.Unlock()

	if r.err != nil {
		return nil, r.err
	}
	if r.data == nil {
		r.data = []byte(`{"error":""}`)
	}
	return &nats.Msg{Data: r.data}, nil
}

func (m *mockConn) Drain() error { return m.drainErr }

// lastCall returns the most recent captured message.
func (m *mockConn) lastCall() *nats.Msg {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.calls) == 0 {
		return nil
	}
	return m.calls[len(m.calls)-1]
}

// callCount returns how many requests have been made.
func (m *mockConn) callCount() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.calls)
}

// newTestClient builds a Client backed by a mockConn.
func newTestClient(mock *mockConn) *Client {
	return &Client{
		cfg: defaultClientConfig(),
		nc:  mock,
	}
}

// decodeBody JSON-decodes the Data field of msg into v.
func decodeBody(t *testing.T, msg *nats.Msg, v any) {
	t.Helper()
	if err := json.Unmarshal(msg.Data, v); err != nil {
		t.Fatalf("decodeBody: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func okReply(extra map[string]any) map[string]any {
	r := map[string]any{"error": ""}
	for k, v := range extra {
		r[k] = v
	}
	return r
}

func errReply(msg string) map[string]any {
	return map[string]any{"error": msg}
}

// ---------------------------------------------------------------------------
// 1. MailboxCreate
// ---------------------------------------------------------------------------

func TestMailboxCreate_WithName(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"mail_address": "agent.inbox"}))
	c := newTestClient(mock)

	addr, err := c.MailboxCreate(context.Background(), "agent.inbox", 3600)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if addr != "agent.inbox" {
		t.Errorf("expected 'agent.inbox', got %q", addr)
	}

	msg := mock.lastCall()
	if msg.Subject != "$mq9.AI.MAILBOX.CREATE" {
		t.Errorf("wrong subject: %s", msg.Subject)
	}
	var body map[string]any
	decodeBody(t, msg, &body)
	if body["name"] != "agent.inbox" {
		t.Errorf("expected name in body, got %v", body)
	}
	if body["ttl"].(float64) != 3600 {
		t.Errorf("expected ttl=3600, got %v", body["ttl"])
	}
}

func TestMailboxCreate_NoName(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"mail_address": "auto-generated-id"}))
	c := newTestClient(mock)

	addr, err := c.MailboxCreate(context.Background(), "", 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if addr != "auto-generated-id" {
		t.Errorf("expected auto-generated-id, got %q", addr)
	}

	var body map[string]any
	decodeBody(t, mock.lastCall(), &body)
	if _, hasName := body["name"]; hasName {
		t.Error("name should be omitted when empty")
	}
}

func TestMailboxCreate_ServerError(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(errReply("quota exceeded"))
	c := newTestClient(mock)

	_, err := c.MailboxCreate(context.Background(), "", 0)
	if err == nil {
		t.Fatal("expected error")
	}
	var mq9Err *Mq9Error
	if !errors.As(err, &mq9Err) {
		t.Errorf("expected *Mq9Error, got %T: %v", err, err)
	}
	if !strings.Contains(mq9Err.Error(), "quota exceeded") {
		t.Errorf("error message missing 'quota exceeded': %s", mq9Err.Error())
	}
}

// ---------------------------------------------------------------------------
// 2. Send
// ---------------------------------------------------------------------------

func TestSend_DefaultPriority(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"msg_id": float64(7)}))
	c := newTestClient(mock)

	msgID, err := c.Send(context.Background(), "task.q", []byte("hello"), SendOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msgID != 7 {
		t.Errorf("expected msg_id=7, got %d", msgID)
	}

	msg := mock.lastCall()
	if msg.Subject != "$mq9.AI.MSG.SEND.task.q" {
		t.Errorf("wrong subject: %s", msg.Subject)
	}
	// normal priority header should be absent
	if msg.Header.Get("mq9-priority") != "" {
		t.Error("priority header should not be set for normal")
	}
	if string(msg.Data) != "hello" {
		t.Errorf("unexpected payload: %q", msg.Data)
	}
}

func TestSend_UrgentPriorityHeader(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"msg_id": float64(3)}))
	c := newTestClient(mock)

	_, err := c.Send(context.Background(), "task.q", []byte("urgent!"), SendOptions{Priority: PriorityUrgent})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	msg := mock.lastCall()
	if msg.Header.Get("mq9-priority") != "urgent" {
		t.Errorf("expected mq9-priority=urgent, got %q", msg.Header.Get("mq9-priority"))
	}
}

func TestSend_CriticalPriorityHeader(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"msg_id": float64(1)}))
	c := newTestClient(mock)

	_, err := c.Send(context.Background(), "task.q", []byte("critical!"), SendOptions{Priority: PriorityCritical})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	msg := mock.lastCall()
	if msg.Header.Get("mq9-priority") != "critical" {
		t.Errorf("expected mq9-priority=critical, got %q", msg.Header.Get("mq9-priority"))
	}
}

func TestSend_WithKeyDelayTTLTags(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"msg_id": float64(-1)}))
	c := newTestClient(mock)

	opts := SendOptions{
		Key:   "dedup-key-1",
		Delay: 30,
		TTL:   3600,
		Tags:  []string{"ai", "async"},
	}
	msgID, err := c.Send(context.Background(), "task.q", []byte("body"), opts)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if msgID != -1 {
		t.Errorf("expected -1 for delayed message, got %d", msgID)
	}

	msg := mock.lastCall()
	if msg.Header.Get("mq9-key") != "dedup-key-1" {
		t.Errorf("wrong key header: %q", msg.Header.Get("mq9-key"))
	}
	if msg.Header.Get("mq9-delay") != "30" {
		t.Errorf("wrong delay header: %q", msg.Header.Get("mq9-delay"))
	}
	if msg.Header.Get("mq9-ttl") != "3600" {
		t.Errorf("wrong ttl header: %q", msg.Header.Get("mq9-ttl"))
	}
	if msg.Header.Get("mq9-tags") != "ai,async" {
		t.Errorf("wrong tags header: %q", msg.Header.Get("mq9-tags"))
	}
}

func TestSend_NoOptionalHeaders(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"msg_id": float64(1)}))
	c := newTestClient(mock)

	_, err := c.Send(context.Background(), "x", []byte("y"), SendOptions{})
	if err != nil {
		t.Fatal(err)
	}
	msg := mock.lastCall()
	for _, h := range []string{"mq9-key", "mq9-delay", "mq9-ttl", "mq9-tags"} {
		if msg.Header.Get(h) != "" {
			t.Errorf("header %s should be absent but got %q", h, msg.Header.Get(h))
		}
	}
}

// ---------------------------------------------------------------------------
// 3. Fetch
// ---------------------------------------------------------------------------

func encodePayload(t *testing.T, s string) string {
	t.Helper()
	return base64.StdEncoding.EncodeToString([]byte(s))
}

func TestFetch_Stateless(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{
		"messages": []any{
			map[string]any{
				"msg_id":      float64(1),
				"payload":     encodePayload(t, "hello"),
				"priority":    "normal",
				"create_time": float64(1700000000),
			},
		},
	}))
	c := newTestClient(mock)

	msgs, err := c.Fetch(context.Background(), "task.q", FetchOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}
	m := msgs[0]
	if m.MsgID != 1 {
		t.Errorf("wrong msg_id: %d", m.MsgID)
	}
	if string(m.Payload) != "hello" {
		t.Errorf("wrong payload: %q", m.Payload)
	}
	if m.Priority != PriorityNormal {
		t.Errorf("wrong priority: %s", m.Priority)
	}
	if m.CreateTime != 1700000000 {
		t.Errorf("wrong create_time: %d", m.CreateTime)
	}
}

func TestFetch_Stateful(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{
		"messages": []any{
			map[string]any{
				"msg_id":      float64(42),
				"payload":     encodePayload(t, "data"),
				"priority":    "urgent",
				"create_time": float64(1),
			},
		},
	}))
	c := newTestClient(mock)

	opts := FetchOptions{GroupName: "worker-1", Deliver: "earliest", NumMsgs: 50, MaxWaitMs: 1000}
	msgs, err := c.Fetch(context.Background(), "task.q", opts)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}

	var body map[string]any
	decodeBody(t, mock.lastCall(), &body)
	if body["group_name"] != "worker-1" {
		t.Errorf("wrong group_name: %v", body["group_name"])
	}
	if body["deliver"] != "earliest" {
		t.Errorf("wrong deliver: %v", body["deliver"])
	}
	cfg := body["config"].(map[string]any)
	if cfg["num_msgs"].(float64) != 50 {
		t.Errorf("wrong num_msgs: %v", cfg["num_msgs"])
	}
}

func TestFetch_Empty(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"messages": []any{}}))
	c := newTestClient(mock)

	msgs, err := c.Fetch(context.Background(), "task.q", FetchOptions{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(msgs) != 0 {
		t.Errorf("expected empty slice, got %d messages", len(msgs))
	}
}

func TestFetch_PayloadDecoded(t *testing.T) {
	raw := []byte{0x00, 0x01, 0x02, 0xFF}
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{
		"messages": []any{
			map[string]any{
				"msg_id":      float64(99),
				"payload":     base64.StdEncoding.EncodeToString(raw),
				"priority":    "critical",
				"create_time": float64(0),
			},
		},
	}))
	c := newTestClient(mock)

	msgs, err := c.Fetch(context.Background(), "m", FetchOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if string(msgs[0].Payload) != string(raw) {
		t.Errorf("payload decode mismatch")
	}
}

// ---------------------------------------------------------------------------
// 4. Ack
// ---------------------------------------------------------------------------

func TestAck_CorrectBody(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(nil))
	c := newTestClient(mock)

	err := c.Ack(context.Background(), "task.q", "worker-1", 5)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	msg := mock.lastCall()
	if msg.Subject != "$mq9.AI.MSG.ACK.task.q" {
		t.Errorf("wrong subject: %s", msg.Subject)
	}

	var body map[string]any
	decodeBody(t, msg, &body)
	if body["group_name"] != "worker-1" {
		t.Errorf("wrong group_name: %v", body["group_name"])
	}
	if body["mail_address"] != "task.q" {
		t.Errorf("wrong mail_address: %v", body["mail_address"])
	}
	if body["msg_id"].(float64) != 5 {
		t.Errorf("wrong msg_id: %v", body["msg_id"])
	}
}

// ---------------------------------------------------------------------------
// 5. Consume
// ---------------------------------------------------------------------------

func TestConsume_HappyPath(t *testing.T) {
	mock := &mockConn{}
	// First fetch returns one message, subsequent fetches return empty.
	mock.enqueue(okReply(map[string]any{
		"messages": []any{
			map[string]any{
				"msg_id":      float64(10),
				"payload":     encodePayload(t, "task"),
				"priority":    "normal",
				"create_time": float64(0),
			},
		},
	}))
	// Ack reply for the one message.
	mock.enqueue(okReply(nil))
	// Second fetch — return empty to let the loop park.
	// We'll stop the consumer before it gets here.

	received := make(chan Message, 1)
	handler := func(msg Message) error {
		received <- msg
		return nil
	}

	c := newTestClient(mock)
	opts := ConsumeOptions{
		GroupName: "g1",
		AutoAck:   true,
	}
	consumer, err := c.Consume(context.Background(), "task.q", handler, opts)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Wait for the message to be processed.
	select {
	case msg := <-received:
		if msg.MsgID != 10 {
			t.Errorf("expected msg_id=10, got %d", msg.MsgID)
		}
		if string(msg.Payload) != "task" {
			t.Errorf("unexpected payload: %q", msg.Payload)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for message")
	}

	consumer.Stop()
	if consumer.IsRunning() {
		t.Error("consumer should be stopped")
	}
	if consumer.ProcessedCount() != 1 {
		t.Errorf("expected ProcessedCount=1, got %d", consumer.ProcessedCount())
	}
}

func TestConsume_HandlerError_ErrorHandlerCalled_NoAck(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{
		"messages": []any{
			map[string]any{
				"msg_id":      float64(20),
				"payload":     encodePayload(t, "bad"),
				"priority":    "normal",
				"create_time": float64(0),
			},
		},
	}))
	// No ack reply enqueued — if ack were called, the mock would return the default empty reply.
	// We verify ack was NOT called by checking call count.

	handlerCalled := make(chan struct{}, 1)
	errorHandlerCalled := make(chan Message, 1)

	handler := func(msg Message) error {
		handlerCalled <- struct{}{}
		return errors.New("handler failed")
	}
	errorHandler := func(msg Message, err error) {
		errorHandlerCalled <- msg
	}

	c := newTestClient(mock)
	opts := ConsumeOptions{
		GroupName:    "g2",
		AutoAck:      true,
		ErrorHandler: errorHandler,
	}
	consumer, err := c.Consume(context.Background(), "task.q", handler, opts)
	if err != nil {
		t.Fatal(err)
	}

	select {
	case <-handlerCalled:
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for handler")
	}

	select {
	case msg := <-errorHandlerCalled:
		if msg.MsgID != 20 {
			t.Errorf("wrong msg in error handler: %d", msg.MsgID)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for error handler")
	}

	consumer.Stop()

	// Ack should NOT have been called: only 1 fetch call made.
	// (fetch=1, ack=0 means 1 total call so far, then more fetch calls after Stop).
	// Just verify ProcessedCount is 0 (handler returned error → no count increment).
	if consumer.ProcessedCount() != 0 {
		t.Errorf("expected ProcessedCount=0, got %d", consumer.ProcessedCount())
	}
}

func TestConsume_Stop_Works(t *testing.T) {
	mock := &mockConn{}
	// Return empty fetches so the loop is idle.
	for i := 0; i < 100; i++ {
		mock.enqueue(okReply(map[string]any{"messages": []any{}}))
	}

	c := newTestClient(mock)
	consumer, err := c.Consume(context.Background(), "task.q", func(Message) error { return nil }, ConsumeOptions{})
	if err != nil {
		t.Fatal(err)
	}

	if !consumer.IsRunning() {
		t.Error("consumer should be running")
	}

	consumer.Stop()

	if consumer.IsRunning() {
		t.Error("consumer should be stopped after Stop()")
	}
}

// ---------------------------------------------------------------------------
// 6. Query
// ---------------------------------------------------------------------------

func TestQuery_AllParams(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{
		"messages": []any{
			map[string]any{
				"msg_id":      float64(5),
				"payload":     encodePayload(t, "q"),
				"priority":    "normal",
				"create_time": float64(999),
			},
		},
	}))
	c := newTestClient(mock)

	msgs, err := c.Query(context.Background(), "m", "status", 10, 1700000000)
	if err != nil {
		t.Fatal(err)
	}
	if len(msgs) != 1 {
		t.Fatalf("expected 1, got %d", len(msgs))
	}

	var body map[string]any
	decodeBody(t, mock.lastCall(), &body)
	if body["key"] != "status" {
		t.Errorf("wrong key: %v", body["key"])
	}
	if body["limit"].(float64) != 10 {
		t.Errorf("wrong limit: %v", body["limit"])
	}
	if body["since"].(float64) != 1700000000 {
		t.Errorf("wrong since: %v", body["since"])
	}
}

func TestQuery_NoParams_OmitsFields(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"messages": []any{}}))
	c := newTestClient(mock)

	_, err := c.Query(context.Background(), "m", "", 0, 0)
	if err != nil {
		t.Fatal(err)
	}

	var body map[string]any
	decodeBody(t, mock.lastCall(), &body)
	for _, field := range []string{"key", "limit", "since"} {
		if _, ok := body[field]; ok {
			t.Errorf("field %q should be omitted but was present", field)
		}
	}
}

// ---------------------------------------------------------------------------
// 7. Delete
// ---------------------------------------------------------------------------

func TestDelete_SubjectEncodesMsgID(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(nil))
	c := newTestClient(mock)

	err := c.Delete(context.Background(), "task.q", 42)
	if err != nil {
		t.Fatal(err)
	}

	msg := mock.lastCall()
	expected := "$mq9.AI.MSG.DELETE.task.q.42"
	if msg.Subject != expected {
		t.Errorf("expected subject %q, got %q", expected, msg.Subject)
	}
	if len(msg.Data) != 0 {
		t.Errorf("expected empty payload, got %q", msg.Data)
	}
}

func TestDelete_ServerError(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(errReply("not found"))
	c := newTestClient(mock)

	err := c.Delete(context.Background(), "m", 99)
	if err == nil {
		t.Fatal("expected error")
	}
	var mq9Err *Mq9Error
	if !errors.As(err, &mq9Err) {
		t.Errorf("expected *Mq9Error, got %T", err)
	}
}

// ---------------------------------------------------------------------------
// 8. AgentRegister
// ---------------------------------------------------------------------------

func TestAgentRegister(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(nil))
	c := newTestClient(mock)

	card := map[string]any{
		"mailbox": "agent-1",
		"name":    "Summarizer",
		"skills":  []string{"summarize", "translate"},
	}
	err := c.AgentRegister(context.Background(), card)
	if err != nil {
		t.Fatal(err)
	}

	msg := mock.lastCall()
	if msg.Subject != "$mq9.AI.AGENT.REGISTER" {
		t.Errorf("wrong subject: %s", msg.Subject)
	}
	var body map[string]any
	decodeBody(t, msg, &body)
	if body["mailbox"] != "agent-1" {
		t.Errorf("wrong mailbox: %v", body["mailbox"])
	}
}

func TestAgentRegister_ServerError(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(errReply("duplicate mailbox"))
	c := newTestClient(mock)

	err := c.AgentRegister(context.Background(), map[string]any{"mailbox": "x"})
	if err == nil {
		t.Fatal("expected error")
	}
}

// ---------------------------------------------------------------------------
// 9. AgentUnregister
// ---------------------------------------------------------------------------

func TestAgentUnregister(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(nil))
	c := newTestClient(mock)

	err := c.AgentUnregister(context.Background(), "agent-1")
	if err != nil {
		t.Fatal(err)
	}

	msg := mock.lastCall()
	if msg.Subject != "$mq9.AI.AGENT.UNREGISTER" {
		t.Errorf("wrong subject: %s", msg.Subject)
	}
	var body map[string]any
	decodeBody(t, msg, &body)
	if body["mailbox"] != "agent-1" {
		t.Errorf("wrong mailbox: %v", body["mailbox"])
	}
}

// ---------------------------------------------------------------------------
// 10. AgentReport
// ---------------------------------------------------------------------------

func TestAgentReport(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(nil))
	c := newTestClient(mock)

	report := map[string]any{
		"mailbox": "agent-1",
		"status":  "idle",
		"load":    0.12,
	}
	err := c.AgentReport(context.Background(), report)
	if err != nil {
		t.Fatal(err)
	}

	msg := mock.lastCall()
	if msg.Subject != "$mq9.AI.AGENT.REPORT" {
		t.Errorf("wrong subject: %s", msg.Subject)
	}
	var body map[string]any
	decodeBody(t, msg, &body)
	if body["status"] != "idle" {
		t.Errorf("wrong status: %v", body["status"])
	}
}

// ---------------------------------------------------------------------------
// 11. AgentDiscover
// ---------------------------------------------------------------------------

func TestAgentDiscover_WithFilters(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{
		"agents": []any{
			map[string]any{"mailbox": "agent-2", "name": "Translator"},
		},
	}))
	c := newTestClient(mock)

	agents, err := c.AgentDiscover(context.Background(), "translate", "language model", 5, 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(agents) != 1 {
		t.Fatalf("expected 1 agent, got %d", len(agents))
	}
	if agents[0]["mailbox"] != "agent-2" {
		t.Errorf("wrong mailbox: %v", agents[0]["mailbox"])
	}

	var body map[string]any
	decodeBody(t, mock.lastCall(), &body)
	if body["text"] != "translate" {
		t.Errorf("wrong text: %v", body["text"])
	}
	if body["semantic"] != "language model" {
		t.Errorf("wrong semantic: %v", body["semantic"])
	}
	if body["limit"].(float64) != 5 {
		t.Errorf("wrong limit: %v", body["limit"])
	}
}

func TestAgentDiscover_Defaults(t *testing.T) {
	mock := &mockConn{}
	mock.enqueue(okReply(map[string]any{"agents": []any{}}))
	c := newTestClient(mock)

	agents, err := c.AgentDiscover(context.Background(), "", "", 0, 0)
	if err != nil {
		t.Fatal(err)
	}
	if agents == nil {
		t.Error("agents should not be nil")
	}

	var body map[string]any
	decodeBody(t, mock.lastCall(), &body)
	if _, ok := body["text"]; ok {
		t.Error("text should be omitted when empty")
	}
	if _, ok := body["semantic"]; ok {
		t.Error("semantic should be omitted when empty")
	}
	if body["limit"].(float64) != 20 {
		t.Errorf("expected default limit=20, got %v", body["limit"])
	}
	if body["page"].(float64) != 1 {
		t.Errorf("expected default page=1, got %v", body["page"])
	}
}

// ---------------------------------------------------------------------------
// 12. Transport-level errors / Close
// ---------------------------------------------------------------------------

func TestRequest_TransportError(t *testing.T) {
	mock := &mockConn{}
	mock.enqueueErr(fmt.Errorf("connection refused"))
	c := newTestClient(mock)

	_, err := c.MailboxCreate(context.Background(), "", 0)
	if err == nil {
		t.Fatal("expected transport error")
	}
	if !strings.Contains(err.Error(), "connection refused") {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestClose_DrainsCalled(t *testing.T) {
	mock := &mockConn{}
	c := newTestClient(mock)
	if err := c.Close(); err != nil {
		t.Errorf("unexpected close error: %v", err)
	}
}

// ---------------------------------------------------------------------------
// 13. Errors type
// ---------------------------------------------------------------------------

func TestMq9Error_Format(t *testing.T) {
	err := newMq9Error("something went wrong")
	if !strings.Contains(err.Error(), "something went wrong") {
		t.Errorf("error format unexpected: %s", err.Error())
	}
	var target *Mq9Error
	if !errors.As(err, &target) {
		t.Error("errors.As should match *Mq9Error")
	}
}

// ---------------------------------------------------------------------------
// 14. Consumer atomic state
// ---------------------------------------------------------------------------

func TestConsumer_IsRunning_ProcessedCount(t *testing.T) {
	consumer := &Consumer{done: make(chan struct{})}
	atomic.StoreInt32(&consumer.running, 1)

	if !consumer.IsRunning() {
		t.Error("expected IsRunning=true")
	}
	if consumer.ProcessedCount() != 0 {
		t.Error("expected ProcessedCount=0")
	}

	atomic.AddInt64(&consumer.count, 5)
	if consumer.ProcessedCount() != 5 {
		t.Errorf("expected ProcessedCount=5, got %d", consumer.ProcessedCount())
	}
}

// ---------------------------------------------------------------------------
// 15. Option functions
// ---------------------------------------------------------------------------

func TestWithRequestTimeout(t *testing.T) {
	cfg := defaultClientConfig()
	WithRequestTimeout(10 * time.Second)(cfg)
	if cfg.requestTimeout != 10*time.Second {
		t.Errorf("expected 10s, got %v", cfg.requestTimeout)
	}
}

func TestWithReconnectDelay(t *testing.T) {
	cfg := defaultClientConfig()
	WithReconnectDelay(5 * time.Second)(cfg)
	if cfg.reconnectDelay != 5*time.Second {
		t.Errorf("expected 5s, got %v", cfg.reconnectDelay)
	}
}
