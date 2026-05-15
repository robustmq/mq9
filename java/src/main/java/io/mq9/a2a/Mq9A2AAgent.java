package io.mq9.a2a;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.a2a.spec.AgentCard;
import io.a2a.spec.Message;
import io.a2a.spec.MessageSendParams;
import io.a2a.spec.SendMessageRequest;
import io.a2a.spec.TaskState;
import io.a2a.spec.TaskStatus;
import io.a2a.spec.TaskStatusUpdateEvent;
import io.mq9.ConsumeOptions;
import io.mq9.Mq9Client;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * A2A agent over mq9 — each instance can both send tasks to other agents
 * and receive tasks from other agents. There is no "client" or "server" role.
 *
 * <p>Typical usage:
 * <pre>{@code
 * Mq9A2AAgent agent = Mq9A2AAgent.builder().build();
 *
 * agent.onMessage((context, queue) ->
 *     queue.enqueue(new TaskStatusUpdateEvent(...WORKING...))
 *          .thenCompose(v -> queue.enqueue(new TaskArtifactUpdateEvent(...)))
 *          .thenCompose(v -> queue.enqueue(new TaskStatusUpdateEvent(...COMPLETED...)))
 * );
 *
 * agent.connect().join();
 * String mailbox = agent.createMailbox(card.name(), 0).join();
 * agent.register(card).join();
 * }</pre>
 */
public final class Mq9A2AAgent {

    private static final Logger LOG = Logger.getLogger(Mq9A2AAgent.class.getName());
    static final ObjectMapper MAPPER = new ObjectMapper();

    // A2A message headers
    static final String HEADER_REPLY_TO = "mq9-reply-to";
    static final String HEADER_TASK_ID  = "mq9-a2a-task-id";
    static final String HEADER_TYPE     = "mq9-a2a-type";
    static final String HEADER_LAST     = "mq9-a2a-last";
    static final String HEADER_METHOD   = "mq9-a2a-method";

    static final String METHOD_SEND = "SendMessage";

    private static final String DEFAULT_SERVER = "nats://demo.robustmq.com:4222";
    private static final int    HEARTBEAT_INTERVAL_SEC = 30;

    // ── config ────────────────────────────────────────────────────────────────

    private final String server;
    private final long   requestTimeoutMs;

    // consumer options — set via onMessage(handler, options)
    private String  groupName;
    private String  deliver    = "earliest";
    private int     numMsgs    = 10;
    private int     maxWaitMs  = 500;
    private ConsumeOptions consumeOptions; // non-null when set via onMessage(handler, ConsumeOptions)

    // ── runtime state ─────────────────────────────────────────────────────────

    private Mq9Client mq9;
    private String    mailbox;
    private String    agentName;
    private AgentCard agentCard;

    private io.mq9.Consumer    consumer;
    private MessageHandler     handler;
    private ScheduledFuture<?> heartbeatFuture;
    private final ScheduledExecutorService scheduler =
            new ScheduledThreadPoolExecutor(1, r -> {
                Thread t = new Thread(r, "mq9-heartbeat");
                t.setDaemon(true);
                return t;
            });

    private Mq9A2AAgent(Builder b) {
        this.server           = b.server;
        this.requestTimeoutMs = b.requestTimeoutMs;
    }

    // ── builder ───────────────────────────────────────────────────────────────

    public static Builder builder() { return new Builder(); }

    public static final class Builder {
        private String server           = DEFAULT_SERVER;
        private long   requestTimeoutMs = 60_000;

        public Builder server(String server)             { this.server = server; return this; }
        public Builder requestTimeoutMs(long ms)         { this.requestTimeoutMs = ms; return this; }
        public Mq9A2AAgent build()                       { return new Mq9A2AAgent(this); }
    }

    // ── handler registration ──────────────────────────────────────────────────

    /**
     * Registers the message handler with default consumer options.
     */
    public void onMessage(MessageHandler handler) {
        this.handler = handler;
    }

    /**
     * Registers the message handler with explicit consumer options.
     *
     * <p>Example:
     * <pre>{@code
     * agent.onMessage(handler, ConsumeOptions.builder()
     *         .groupName("my-agent.workers")
     *         .deliver("earliest")
     *         .numMsgs(10)
     *         .maxWaitMs(500)
     *         .build());
     * }</pre>
     */
    public void onMessage(MessageHandler handler, ConsumeOptions options) {
        this.handler        = handler;
        this.consumeOptions = options;
    }

    // ── lifecycle ─────────────────────────────────────────────────────────────

    /** Connects to the broker. Must be called before any other operation. */
    public CompletableFuture<Void> connect() {
        return Mq9Client.connect(server).thenAccept(client -> this.mq9 = client);
    }

    /**
     * Creates a mailbox and starts the background consumer.
     *
     * <p>The agent can receive messages immediately after this call.
     * Call {@link #register(AgentCard)} afterwards to become discoverable.
     *
     * @param name mailbox name, typically {@code AgentCard.name()}
     * @param ttl  mailbox TTL in seconds; {@code 0} = permanent
     * @return the mailbox address
     */
    public CompletableFuture<String> createMailbox(String name, long ttl) {
        requireConnected();
        return mq9.mailboxCreate(name, ttl).thenCompose(addr -> {
            this.mailbox   = addr;
            this.agentName = name;

            ConsumeOptions opts;
            if (consumeOptions != null) {
                opts = consumeOptions;
            } else {
                String group = (groupName != null) ? groupName : name + ".workers";
                opts = ConsumeOptions.builder()
                        .groupName(group)
                        .deliver(deliver)
                        .numMsgs(numMsgs)
                        .maxWaitMs(maxWaitMs)
                        .autoAck(true)
                        .build();
            }

            return mq9.consume(mailbox, this::dispatch, opts)
                    .thenApply(c -> {
                        this.consumer = c;
                        LOG.info("[mq9.a2a] mailbox ready — " + mailbox);
                        return addr;
                    });
        });
    }

    /**
     * Publishes agent identity to the registry so others can discover this agent.
     * Must be called after {@link #createMailbox}.
     */
    public CompletableFuture<Void> register(AgentCard card) {
        requireConnected();
        if (mailbox == null) throw new IllegalStateException("Call createMailbox() before register().");

        this.agentCard = card;
        Map<String, Object> body = new HashMap<>();
        body.put("name",       agentName);
        body.put("mailbox",    mailbox);
        body.put("payload",    card.description());
        body.put("agent_card", card);

        return mq9.agentRegister(body).thenRun(() -> {
            LOG.info("[mq9.a2a] registered agent=" + agentName);
            heartbeatFuture = scheduler.scheduleAtFixedRate(
                    this::heartbeat,
                    HEARTBEAT_INTERVAL_SEC,
                    HEARTBEAT_INTERVAL_SEC,
                    TimeUnit.SECONDS);
        });
    }

    /**
     * Removes this agent from the registry. The connection and consumer stay
     * active so queued messages can still be processed.
     * Call {@link #close()} when ready to fully stop.
     */
    public CompletableFuture<Void> unregister() {
        if (heartbeatFuture != null) {
            heartbeatFuture.cancel(false);
            heartbeatFuture = null;
        }
        if (mq9 != null && mailbox != null) {
            return mq9.agentUnregister(mailbox);
        }
        return CompletableFuture.completedFuture(null);
    }

    /** Stops the consumer and disconnects from the broker. */
    public void close() {
        if (consumer != null) consumer.stop();
        if (mq9 != null)      mq9.close();
        scheduler.shutdown();
    }

    // ── discovery ─────────────────────────────────────────────────────────────

    /**
     * Discovers agents by natural-language description.
     *
     * @param query    natural-language query; {@code null} to list all
     * @param semantic {@code true} vector search, {@code false} keyword match
     * @param limit    max results
     */
    public CompletableFuture<java.util.List<Map<String, Object>>> discover(
            String query, boolean semantic, int limit) {
        requireConnected();
        if (query == null) return mq9.agentDiscover(null, null, limit, null);
        return semantic
                ? mq9.agentDiscover(null, query, limit, null)
                : mq9.agentDiscover(query, null, limit, null);
    }

    // ── outbound messaging ────────────────────────────────────────────────────

    /**
     * Sends an A2A {@link SendMessageRequest} to another agent.
     *
     * <p>With {@code replyTo} set the executing agent will stream result events
     * back to that mailbox. Each event carries a {@code task_id} generated by
     * the executor; read it from {@link A2AContext#taskId} in your handler.
     *
     * @param mailAddress destination mailbox address (string) or agent-info map
     *                    containing a {@code "mailbox"} key
     * @param request     the A2A message request
     * @param replyTo     your own mailbox address; {@code null} for one-way send
     * @return msg_id assigned by the broker
     */
    public CompletableFuture<Long> sendMessage(
            Object mailAddress, SendMessageRequest request, String replyTo) {
        requireConnected();
        String dest = mailboxOf(mailAddress);

        byte[] payload;
        try {
            payload = MAPPER.writeValueAsBytes(request);
        } catch (Exception e) {
            CompletableFuture<Long> f = new CompletableFuture<>();
            f.completeExceptionally(e);
            return f;
        }

        Map<String, String> headers = new HashMap<>();
        headers.put(HEADER_METHOD, METHOD_SEND);
        if (replyTo != null) {
            headers.put(HEADER_REPLY_TO, replyTo);
        }
        return mq9.send(dest, payload, io.mq9.SendOptions.builder().build(), headers);
    }

    // ── dispatch (incoming messages) ──────────────────────────────────────────

    private CompletableFuture<Void> dispatch(io.mq9.Message msg) {
        Map<String, String> headers = headersOf(msg);
        String method  = headers.getOrDefault(HEADER_METHOD, METHOD_SEND);
        String replyTo = headers.get(HEADER_REPLY_TO);

        if (METHOD_SEND.equals(method)) {
            return handleSendMessage(msg, replyTo);
        }
        LOG.warning("[mq9.a2a] unknown method=" + method + ", dropping msg_id=" + msg.msgId);
        return CompletableFuture.completedFuture(null);
    }

    private CompletableFuture<Void> handleSendMessage(io.mq9.Message msg, String replyTo) {
        if (handler == null) {
            LOG.warning("[mq9.a2a] no handler registered, dropping msg_id=" + msg.msgId);
            return CompletableFuture.completedFuture(null);
        }

        SendMessageRequest request;
        try {
            request = MAPPER.readValue(msg.payload, SendMessageRequest.class);
        } catch (Exception e) {
            LOG.log(Level.WARNING, "[mq9.a2a] bad SendMessageRequest msg_id=" + msg.msgId, e);
            return CompletableFuture.completedFuture(null);
        }

        MessageSendParams params = request.getParams();
        Message a2aMessage = (params != null) ? params.message() : null;

        // task_id is generated here (executor side), per A2A protocol
        String taskId    = UUID.randomUUID().toString();
        String contextId = (a2aMessage != null) ? a2aMessage.getContextId() : null;

        A2AContext context = new A2AContext(taskId, contextId, a2aMessage, null);
        ForwardingEventQueue queue = new ForwardingEventQueue(this, replyTo, taskId);

        return handler.handle(context, queue)
                .exceptionally(ex -> {
                    LOG.log(Level.WARNING, "[mq9.a2a] handler error msg_id=" + msg.msgId, ex);
                    if (replyTo != null) {
                        sendEvent(replyTo, failedEvent(taskId, contextId), taskId, true);
                    }
                    return null;
                })
                .thenCompose(v -> queue.flushLast());
    }

    // ── internals ─────────────────────────────────────────────────────────────

    CompletableFuture<Void> sendEvent(String replyTo, Object event, String taskId, boolean last) {
        byte[] payload;
        try {
            payload = MAPPER.writeValueAsBytes(event);
        } catch (Exception e) {
            LOG.log(Level.WARNING, "[mq9.a2a] failed to serialize event", e);
            return CompletableFuture.completedFuture(null);
        }
        Map<String, String> headers = new HashMap<>();
        headers.put(HEADER_TYPE, event.getClass().getSimpleName());
        headers.put(HEADER_TASK_ID, taskId);
        if (last) headers.put(HEADER_LAST, "true");
        return mq9.send(replyTo, payload, io.mq9.SendOptions.builder().build(), headers)
                .thenApply(id -> null);
    }

    private void heartbeat() {
        try {
            Map<String, Object> report = new HashMap<>();
            report.put("name",        agentName);
            report.put("mailbox",     mailbox);
            report.put("report_info", "running, processed="
                    + (consumer != null ? consumer.getProcessedCount() : 0));
            mq9.agentReport(report).join();
        } catch (Exception e) {
            LOG.log(Level.WARNING, "[mq9.a2a] heartbeat error", e);
        }
    }

    private void requireConnected() {
        if (mq9 == null) throw new IllegalStateException("Not connected — call connect() first.");
    }

    private static String mailboxOf(Object agent) {
        if (agent instanceof String s) return s;
        if (agent instanceof Map<?,?> m) {
            Object v = m.get("mailbox");
            if (v instanceof String s) return s;
        }
        throw new IllegalArgumentException("agent must be a mailbox string or Map with 'mailbox' key");
    }

    private static Map<String, String> headersOf(io.mq9.Message msg) {
        if (msg.headers == null) return Map.of();
        return msg.headers;
    }

    private static TaskStatusUpdateEvent failedEvent(String taskId, String contextId) {
        TaskStatus status = new TaskStatus(TaskState.FAILED);
        return new TaskStatusUpdateEvent.Builder()
                .taskId(taskId)
                .contextId(contextId)
                .status(status)
                .isFinal(true)
                .build();
    }
}
