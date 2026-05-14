// Package mq9 provides a Go client for the mq9 AI-native async messaging protocol.
// mq9 is a NATS-based message broker built for Agent-to-Agent async communication.
// Every Agent gets a mailbox; sender and receiver do not need to be online simultaneously.
package mq9

import (
	"sync"
	"sync/atomic"
	"time"
)

// Priority represents the delivery priority of a message.
type Priority string

const (
	PriorityNormal   Priority = "normal"
	PriorityUrgent   Priority = "urgent"
	PriorityCritical Priority = "critical"
)

// Message is a message received from an mq9 mailbox.
type Message struct {
	MsgID      int64
	Payload    []byte
	Priority   Priority
	CreateTime int64 // Unix timestamp in seconds
}

// SendOptions configures how a message is sent.
type SendOptions struct {
	Priority Priority // default: PriorityNormal
	Key      string
	Delay    int64    // seconds; 0 = no delay
	TTL      int64    // seconds; 0 = no TTL
	Tags     []string
}

// FetchOptions configures a single Fetch call.
type FetchOptions struct {
	GroupName    string
	Deliver      string // "latest"|"earliest"|"from_time"|"from_id"; default "latest"
	FromTime     int64
	FromID       int64
	ForceDeliver bool
	NumMsgs      int   // default 100
	MaxWaitMs    int64 // default 500
}

// ConsumeOptions configures a long-running Consume loop.
type ConsumeOptions struct {
	GroupName    string
	Deliver      string
	NumMsgs      int
	MaxWaitMs    int64
	AutoAck      bool
	ErrorHandler func(msg Message, err error)
}

// Consumer represents an active consume loop. Obtain one via Client.Consume.
type Consumer struct {
	running   int32 // atomic bool: 1 = running, 0 = stopped
	count     int64 // atomic processed message count
	done      chan struct{}
	wg        sync.WaitGroup
}

// IsRunning reports whether the consumer goroutine is still running.
func (c *Consumer) IsRunning() bool {
	return atomic.LoadInt32(&c.running) == 1
}

// ProcessedCount returns the total number of messages successfully processed.
func (c *Consumer) ProcessedCount() int64 {
	return atomic.LoadInt64(&c.count)
}

// Stop signals the consumer to stop and blocks until the goroutine exits.
func (c *Consumer) Stop() {
	close(c.done)
	c.wg.Wait()
}

// clientConfig holds the configuration for a Client.
type clientConfig struct {
	requestTimeout time.Duration
	reconnectDelay time.Duration
}

func defaultClientConfig() *clientConfig {
	return &clientConfig{
		requestTimeout: 5 * time.Second,
		reconnectDelay: 2 * time.Second,
	}
}

// Option is a functional option for configuring a Client.
type Option func(*clientConfig)

// WithRequestTimeout sets the timeout for each NATS request/reply call.
func WithRequestTimeout(d time.Duration) Option {
	return func(cfg *clientConfig) {
		cfg.requestTimeout = d
	}
}

// WithReconnectDelay sets the delay between reconnection attempts.
func WithReconnectDelay(d time.Duration) Option {
	return func(cfg *clientConfig) {
		cfg.reconnectDelay = d
	}
}
