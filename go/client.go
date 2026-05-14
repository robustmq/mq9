package mq9

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"sync/atomic"
	"time"

	"github.com/nats-io/nats.go"
)

// ---------------------------------------------------------------------------
// Subject helpers
// ---------------------------------------------------------------------------

const subjectPrefix = "$mq9.AI"

func subjectMailboxCreate() string {
	return subjectPrefix + ".MAILBOX.CREATE"
}

func subjectMsgSend(mailAddress string) string {
	return fmt.Sprintf("%s.MSG.SEND.%s", subjectPrefix, mailAddress)
}

func subjectMsgFetch(mailAddress string) string {
	return fmt.Sprintf("%s.MSG.FETCH.%s", subjectPrefix, mailAddress)
}

func subjectMsgAck(mailAddress string) string {
	return fmt.Sprintf("%s.MSG.ACK.%s", subjectPrefix, mailAddress)
}

func subjectMsgQuery(mailAddress string) string {
	return fmt.Sprintf("%s.MSG.QUERY.%s", subjectPrefix, mailAddress)
}

func subjectMsgDelete(mailAddress string, msgID int64) string {
	return fmt.Sprintf("%s.MSG.DELETE.%s.%d", subjectPrefix, mailAddress, msgID)
}

func subjectAgentRegister() string   { return subjectPrefix + ".AGENT.REGISTER" }
func subjectAgentUnregister() string { return subjectPrefix + ".AGENT.UNREGISTER" }
func subjectAgentReport() string     { return subjectPrefix + ".AGENT.REPORT" }
func subjectAgentDiscover() string   { return subjectPrefix + ".AGENT.DISCOVER" }

// ---------------------------------------------------------------------------
// natsConn interface — allows mock injection in tests
// ---------------------------------------------------------------------------

// natsConn abstracts the nats.Conn operations used by Client.
type natsConn interface {
	RequestMsgWithContext(ctx context.Context, msg *nats.Msg) (*nats.Msg, error)
	Drain() error
}

// natsConnAdapter wraps *nats.Conn to satisfy natsConn using context-aware requests.
type natsConnAdapter struct {
	nc *nats.Conn
}

func (a *natsConnAdapter) RequestMsgWithContext(ctx context.Context, msg *nats.Msg) (*nats.Msg, error) {
	return a.nc.RequestMsgWithContext(ctx, msg)
}

func (a *natsConnAdapter) Drain() error {
	return a.nc.Drain()
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

// Client is a synchronous mq9 client. Create one with Connect.
type Client struct {
	cfg *clientConfig
	nc  natsConn
}

// Connect dials the NATS server and returns a ready Client.
// server should be in the form "nats://host:port".
func Connect(server string, opts ...Option) (*Client, error) {
	cfg := defaultClientConfig()
	for _, o := range opts {
		o(cfg)
	}

	nc, err := nats.Connect(server,
		nats.MaxReconnects(-1),
		nats.ReconnectWait(cfg.reconnectDelay),
	)
	if err != nil {
		return nil, fmt.Errorf("mq9: connect: %w", err)
	}

	return &Client{cfg: cfg, nc: &natsConnAdapter{nc: nc}}, nil
}

// Close drains and closes the underlying NATS connection.
func (c *Client) Close() error {
	return c.nc.Drain()
}

// ---------------------------------------------------------------------------
// Internal request helper
// ---------------------------------------------------------------------------

// request encodes payload as JSON, sends a NATS request, decodes the JSON reply,
// checks the "error" field, and returns the raw reply bytes for further decoding.
func (c *Client) request(ctx context.Context, subject string, payload any) ([]byte, error) {
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("mq9: marshal request: %w", err)
	}

	msg := nats.NewMsg(subject)
	msg.Data = data

	// Apply per-request timeout from config if ctx has no deadline.
	reqCtx := ctx
	if _, ok := ctx.Deadline(); !ok {
		var cancel context.CancelFunc
		reqCtx, cancel = context.WithTimeout(ctx, c.cfg.requestTimeout)
		defer cancel()
	}

	reply, err := c.nc.RequestMsgWithContext(reqCtx, msg)
	if err != nil {
		return nil, fmt.Errorf("mq9: request %s: %w", subject, err)
	}

	// Check top-level "error" field.
	var base struct {
		Error string `json:"error"`
	}
	if err := json.Unmarshal(reply.Data, &base); err != nil {
		return nil, fmt.Errorf("mq9: decode reply: %w", err)
	}
	if base.Error != "" {
		return nil, newMq9Error(base.Error)
	}

	return reply.Data, nil
}

// requestMsg sends a NATS message with optional headers and returns the reply bytes.
func (c *Client) requestMsg(ctx context.Context, msg *nats.Msg) ([]byte, error) {
	reqCtx := ctx
	if _, ok := ctx.Deadline(); !ok {
		var cancel context.CancelFunc
		reqCtx, cancel = context.WithTimeout(ctx, c.cfg.requestTimeout)
		defer cancel()
	}

	reply, err := c.nc.RequestMsgWithContext(reqCtx, msg)
	if err != nil {
		return nil, fmt.Errorf("mq9: request %s: %w", msg.Subject, err)
	}

	var base struct {
		Error string `json:"error"`
	}
	if err := json.Unmarshal(reply.Data, &base); err != nil {
		return nil, fmt.Errorf("mq9: decode reply: %w", err)
	}
	if base.Error != "" {
		return nil, newMq9Error(base.Error)
	}

	return reply.Data, nil
}

// ---------------------------------------------------------------------------
// Mailbox
// ---------------------------------------------------------------------------

// MailboxCreate creates a new mailbox. name="" lets the broker auto-generate an address.
// ttl=0 means the mailbox never expires. Returns the mail_address string.
func (c *Client) MailboxCreate(ctx context.Context, name string, ttl int64) (string, error) {
	req := map[string]any{"ttl": ttl}
	if name != "" {
		req["name"] = name
	}

	data, err := c.request(ctx, subjectMailboxCreate(), req)
	if err != nil {
		return "", err
	}

	var resp struct {
		MailAddress string `json:"mail_address"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		return "", fmt.Errorf("mq9: decode mailbox create response: %w", err)
	}
	return resp.MailAddress, nil
}

// ---------------------------------------------------------------------------
// Messaging — Send
// ---------------------------------------------------------------------------

// Send sends payload to the given mailAddress and returns the msg_id assigned by the
// broker. msg_id is -1 for delayed messages.
func (c *Client) Send(ctx context.Context, mailAddress string, payload []byte, opts SendOptions) (int64, error) {
	msg := nats.NewMsg(subjectMsgSend(mailAddress))
	msg.Data = payload

	// Set headers for non-default options only.
	priority := opts.Priority
	if priority == "" {
		priority = PriorityNormal
	}
	if priority != PriorityNormal {
		msg.Header.Set("mq9-priority", string(priority))
	}
	if opts.Key != "" {
		msg.Header.Set("mq9-key", opts.Key)
	}
	if opts.Delay > 0 {
		msg.Header.Set("mq9-delay", fmt.Sprintf("%d", opts.Delay))
	}
	if opts.TTL > 0 {
		msg.Header.Set("mq9-ttl", fmt.Sprintf("%d", opts.TTL))
	}
	if len(opts.Tags) > 0 {
		msg.Header.Set("mq9-tags", strings.Join(opts.Tags, ","))
	}

	data, err := c.requestMsg(ctx, msg)
	if err != nil {
		return 0, err
	}

	var resp struct {
		MsgID int64 `json:"msg_id"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		return 0, fmt.Errorf("mq9: decode send response: %w", err)
	}
	return resp.MsgID, nil
}

// ---------------------------------------------------------------------------
// Messaging — Fetch
// ---------------------------------------------------------------------------

// Fetch pulls messages from the mailbox in a single call.
func (c *Client) Fetch(ctx context.Context, mailAddress string, opts FetchOptions) ([]Message, error) {
	deliver := opts.Deliver
	if deliver == "" {
		deliver = "latest"
	}
	numMsgs := opts.NumMsgs
	if numMsgs == 0 {
		numMsgs = 100
	}
	maxWaitMs := opts.MaxWaitMs
	if maxWaitMs == 0 {
		maxWaitMs = 500
	}

	req := map[string]any{
		"group_name":    opts.GroupName,
		"deliver":       deliver,
		"from_time":     opts.FromTime,
		"from_id":       opts.FromID,
		"force_deliver": opts.ForceDeliver,
		"config": map[string]any{
			"num_msgs":    numMsgs,
			"max_wait_ms": maxWaitMs,
		},
	}

	data, err := c.request(ctx, subjectMsgFetch(mailAddress), req)
	if err != nil {
		return nil, err
	}

	var resp struct {
		Messages []struct {
			MsgID      int64  `json:"msg_id"`
			Payload    string `json:"payload"` // base64-encoded
			Priority   string `json:"priority"`
			CreateTime int64  `json:"create_time"`
		} `json:"messages"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil, fmt.Errorf("mq9: decode fetch response: %w", err)
	}

	msgs := make([]Message, 0, len(resp.Messages))
	for _, m := range resp.Messages {
		decoded, err := base64.StdEncoding.DecodeString(m.Payload)
		if err != nil {
			// Treat as raw bytes if not valid base64.
			decoded = []byte(m.Payload)
		}
		p := Priority(m.Priority)
		if p == "" {
			p = PriorityNormal
		}
		msgs = append(msgs, Message{
			MsgID:      m.MsgID,
			Payload:    decoded,
			Priority:   p,
			CreateTime: m.CreateTime,
		})
	}
	return msgs, nil
}

// ---------------------------------------------------------------------------
// Messaging — Ack
// ---------------------------------------------------------------------------

// Ack advances the consumer group offset to msgID for the given mailAddress.
func (c *Client) Ack(ctx context.Context, mailAddress string, groupName string, msgID int64) error {
	req := map[string]any{
		"group_name":   groupName,
		"mail_address": mailAddress,
		"msg_id":       msgID,
	}
	_, err := c.request(ctx, subjectMsgAck(mailAddress), req)
	return err
}

// ---------------------------------------------------------------------------
// Messaging — Consume
// ---------------------------------------------------------------------------

// Consume starts a background goroutine that repeatedly fetches messages and calls
// handler for each one. It returns a *Consumer immediately.
//
// If opts.AutoAck is true and handler returns nil, the message is Acked.
// If handler returns an error, the message is NOT acked; opts.ErrorHandler is called
// if set, otherwise the error is logged with log.Printf.
// On Fetch failure the goroutine sleeps 1 second before retrying.
func (c *Client) Consume(ctx context.Context, mailAddress string, handler func(Message) error, opts ConsumeOptions) (*Consumer, error) {
	consumer := &Consumer{
		done: make(chan struct{}),
	}
	atomic.StoreInt32(&consumer.running, 1)

	fetchOpts := FetchOptions{
		GroupName: opts.GroupName,
		Deliver:   opts.Deliver,
		NumMsgs:   opts.NumMsgs,
		MaxWaitMs: opts.MaxWaitMs,
	}

	consumer.wg.Add(1)
	go func() {
		defer consumer.wg.Done()
		defer atomic.StoreInt32(&consumer.running, 0)

		for {
			// Check if stop was requested.
			select {
			case <-consumer.done:
				return
			default:
			}

			msgs, err := c.Fetch(ctx, mailAddress, fetchOpts)
			if err != nil {
				log.Printf("mq9: consume fetch error on %s: %v", mailAddress, err)
				select {
				case <-consumer.done:
					return
				case <-time.After(time.Second):
				}
				continue
			}

			for _, msg := range msgs {
				// Re-check stop between messages.
				select {
				case <-consumer.done:
					return
				default:
				}

				handlerErr := handler(msg)
				if handlerErr != nil {
					if opts.ErrorHandler != nil {
						opts.ErrorHandler(msg, handlerErr)
					} else {
						log.Printf("mq9: consume handler error (msg_id=%d): %v", msg.MsgID, handlerErr)
					}
					continue
				}

				atomic.AddInt64(&consumer.count, 1)

				if opts.AutoAck {
					if ackErr := c.Ack(ctx, mailAddress, opts.GroupName, msg.MsgID); ackErr != nil {
						log.Printf("mq9: consume ack error (msg_id=%d): %v", msg.MsgID, ackErr)
					}
				}
			}
		}
	}()

	return consumer, nil
}

// ---------------------------------------------------------------------------
// Messaging — Query
// ---------------------------------------------------------------------------

// Query inspects the mailbox without affecting any consumer group offset.
// key="", limit=0, since=0 means omit those fields from the request.
func (c *Client) Query(ctx context.Context, mailAddress string, key string, limit int64, since int64) ([]Message, error) {
	req := map[string]any{}
	if key != "" {
		req["key"] = key
	}
	if limit > 0 {
		req["limit"] = limit
	}
	if since > 0 {
		req["since"] = since
	}

	data, err := c.request(ctx, subjectMsgQuery(mailAddress), req)
	if err != nil {
		return nil, err
	}

	var resp struct {
		Messages []struct {
			MsgID      int64  `json:"msg_id"`
			Payload    string `json:"payload"`
			Priority   string `json:"priority"`
			CreateTime int64  `json:"create_time"`
		} `json:"messages"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil, fmt.Errorf("mq9: decode query response: %w", err)
	}

	msgs := make([]Message, 0, len(resp.Messages))
	for _, m := range resp.Messages {
		decoded, err := base64.StdEncoding.DecodeString(m.Payload)
		if err != nil {
			decoded = []byte(m.Payload)
		}
		p := Priority(m.Priority)
		if p == "" {
			p = PriorityNormal
		}
		msgs = append(msgs, Message{
			MsgID:      m.MsgID,
			Payload:    decoded,
			Priority:   p,
			CreateTime: m.CreateTime,
		})
	}
	return msgs, nil
}

// ---------------------------------------------------------------------------
// Messaging — Delete
// ---------------------------------------------------------------------------

// Delete removes a specific message from the mailbox. The msg_id is encoded in
// the subject; the payload is empty.
func (c *Client) Delete(ctx context.Context, mailAddress string, msgID int64) error {
	msg := nats.NewMsg(subjectMsgDelete(mailAddress, msgID))
	msg.Data = []byte{}

	_, err := c.requestMsg(ctx, msg)
	return err
}

// ---------------------------------------------------------------------------
// Agent registry
// ---------------------------------------------------------------------------

// AgentRegister registers an agent. agentCard must contain a "mailbox" field.
func (c *Client) AgentRegister(ctx context.Context, agentCard map[string]any) error {
	_, err := c.request(ctx, subjectAgentRegister(), agentCard)
	return err
}

// AgentUnregister removes an agent from the registry by mailbox address.
func (c *Client) AgentUnregister(ctx context.Context, mailbox string) error {
	req := map[string]any{"mailbox": mailbox}
	_, err := c.request(ctx, subjectAgentUnregister(), req)
	return err
}

// AgentReport updates the agent's live status/metrics. report must contain a "mailbox" field.
func (c *Client) AgentReport(ctx context.Context, report map[string]any) error {
	_, err := c.request(ctx, subjectAgentReport(), report)
	return err
}

// AgentDiscover searches the agent registry.
// text="", semantic="" means omit from request.
// limit=0 uses the broker default (20); page=0 uses default (1).
func (c *Client) AgentDiscover(ctx context.Context, text string, semantic string, limit int, page int) ([]map[string]any, error) {
	req := map[string]any{}
	if text != "" {
		req["text"] = text
	}
	if semantic != "" {
		req["semantic"] = semantic
	}
	if limit > 0 {
		req["limit"] = limit
	} else {
		req["limit"] = 20
	}
	if page > 0 {
		req["page"] = page
	} else {
		req["page"] = 1
	}

	data, err := c.request(ctx, subjectAgentDiscover(), req)
	if err != nil {
		return nil, err
	}

	var resp struct {
		Agents []map[string]any `json:"agents"`
	}
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil, fmt.Errorf("mq9: decode discover response: %w", err)
	}
	if resp.Agents == nil {
		resp.Agents = []map[string]any{}
	}
	return resp.Agents, nil
}
