package io.mq9;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.nats.client.Connection;
import io.nats.client.Nats;
import io.nats.client.Options;
import io.nats.client.impl.Headers;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Async Java client for the mq9 Agent messaging protocol.
 *
 * <p>All operations return {@link CompletableFuture} and do not block the
 * calling thread.  Obtain an instance via {@link #connect(String)} or
 * {@link #connect(String, ClientOptions)}.
 *
 * <pre>{@code
 * Mq9Client client = Mq9Client.connect("nats://localhost:4222").join();
 * String addr = client.mailboxCreate("agent.inbox", 0).join();
 * long msgId  = client.send(addr, "hello".getBytes(), SendOptions.builder().build()).join();
 * client.close();
 * }</pre>
 */
public final class Mq9Client implements AutoCloseable {

    private static final Logger LOG = Logger.getLogger(Mq9Client.class.getName());

    private static final String PREFIX = "$mq9.AI";
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Connection nc;
    private final ClientOptions options;

    // package-private for testing
    Mq9Client(Connection nc, ClientOptions options) {
        this.nc = nc;
        this.options = options;
    }

    // -------------------------------------------------------------------------
    // Factory methods
    // -------------------------------------------------------------------------

    /**
     * Connects to a NATS server using default {@link ClientOptions}.
     *
     * @param server NATS URL, e.g. {@code "nats://localhost:4222"}
     */
    public static CompletableFuture<Mq9Client> connect(String server) {
        return connect(server, ClientOptions.builder().build());
    }

    /**
     * Connects to a NATS server with custom options.
     */
    public static CompletableFuture<Mq9Client> connect(String server, ClientOptions options) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Options natsOptions = new Options.Builder()
                        .server(server)
                        .connectionTimeout(options.requestTimeout)
                        .build();
                Connection nc = Nats.connect(natsOptions);
                return new Mq9Client(nc, options);
            } catch (IOException | InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new Mq9Error("Failed to connect to NATS server: " + server, e);
            }
        });
    }

    // -------------------------------------------------------------------------
    // AutoCloseable
    // -------------------------------------------------------------------------

    /**
     * Drains and closes the underlying NATS connection.  Blocks up to the
     * configured request timeout waiting for the drain to complete.
     */
    @Override
    public void close() {
        try {
            nc.drain(options.requestTimeout).get();
        } catch (Exception e) {
            LOG.log(Level.WARNING, "Error draining NATS connection", e);
        }
        try {
            nc.close();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    // -------------------------------------------------------------------------
    // Mailbox
    // -------------------------------------------------------------------------

    /**
     * Creates a mailbox and returns its {@code mail_address}.
     *
     * @param name name hint for the mailbox; {@code null} to let the broker
     *             auto-generate an address
     * @param ttl  time-to-live in seconds; {@code 0} means never expires
     */
    public CompletableFuture<String> mailboxCreate(String name, long ttl) {
        return CompletableFuture.supplyAsync(() -> {
            ObjectNode req = MAPPER.createObjectNode();
            if (name != null) req.put("name", name);
            req.put("ttl", ttl);

            JsonNode resp = request(PREFIX + ".MAILBOX.CREATE", toBytes(req));
            checkError(resp);
            return resp.get("mail_address").asText();
        });
    }

    // -------------------------------------------------------------------------
    // Messaging
    // -------------------------------------------------------------------------

    /**
     * Sends a message to {@code mailAddress}.
     *
     * @param mailAddress destination mailbox address
     * @param payload     raw message bytes
     * @param options     optional send parameters (priority, key, delay …)
     * @return the assigned {@code msg_id}; {@code -1} for delayed messages
     */
    public CompletableFuture<Long> send(String mailAddress, byte[] payload, SendOptions options) {
        return send(mailAddress, payload, options, null);
    }

    /**
     * Sends a message with additional protocol headers (e.g. A2A headers).
     *
     * @param extraHeaders additional NATS headers; merged with {@code options}-derived headers
     */
    public CompletableFuture<Long> send(String mailAddress, byte[] payload, SendOptions options,
                                        Map<String, String> extraHeaders) {
        return CompletableFuture.supplyAsync(() -> {
            String subject = PREFIX + ".MSG.SEND." + mailAddress;
            Headers headers = buildSendHeaders(options);
            if (extraHeaders != null) {
                extraHeaders.forEach(headers::add);
            }

            io.nats.client.Message natsResp = requestWithHeaders(subject, headers, payload);

            JsonNode resp = parseJson(natsResp.getData());
            checkError(resp);
            return resp.get("msg_id").asLong();
        });
    }

    /**
     * Fetches a batch of messages from {@code mailAddress}.
     */
    public CompletableFuture<List<Message>> fetch(String mailAddress, FetchOptions options) {
        return CompletableFuture.supplyAsync(() -> {
            ObjectNode req = buildFetchRequest(options);
            JsonNode resp = request(PREFIX + ".MSG.FETCH." + mailAddress, toBytes(req));
            checkError(resp);
            return parseMessages(resp.get("messages"));
        });
    }

    /**
     * Acknowledges {@code msgId} for the given consumer group, advancing the
     * group's offset past that message.
     */
    public CompletableFuture<Void> ack(String mailAddress, String groupName, long msgId) {
        return CompletableFuture.supplyAsync(() -> {
            ObjectNode req = MAPPER.createObjectNode();
            req.put("group_name", groupName);
            req.put("mail_address", mailAddress);
            req.put("msg_id", msgId);

            JsonNode resp = request(PREFIX + ".MSG.ACK." + mailAddress, toBytes(req));
            checkError(resp);
            return (Void) null;
        });
    }

    /**
     * Starts a long-running consume loop for {@code mailAddress}.
     *
     * <p>The loop fetches messages in batches, invokes {@code handler} for
     * each, and (if {@code autoAck}) ACKs after a successful invocation.
     * Handler failures invoke {@code options.errorHandler} and skip the ACK.
     * Fetch failures are logged and retried after a 1-second sleep.
     *
     * @return a future that resolves to a {@link Consumer} handle immediately
     *         (before any message is processed)
     */
    public CompletableFuture<Consumer> consume(
            String mailAddress,
            Function<Message, CompletableFuture<Void>> handler,
            ConsumeOptions options) {

        AtomicBoolean running = new AtomicBoolean(true);
        AtomicLong processedCount = new AtomicLong(0);
        CompletableFuture<Void> doneFuture = new CompletableFuture<>();

        FetchOptions fetchOpts = FetchOptions.builder()
                .groupName(options.groupName)
                .deliver(options.deliver)
                .numMsgs(options.numMsgs)
                .maxWaitMs(options.maxWaitMs)
                .build();

        Thread.ofVirtual().name("mq9-consume-" + mailAddress).start(() -> {
            try {
                while (running.get()) {
                    List<Message> messages;
                    try {
                        messages = fetch(mailAddress, fetchOpts).get();
                    } catch (Exception e) {
                        if (!running.get()) break;
                        LOG.log(Level.WARNING, "Fetch failed for mailbox " + mailAddress + "; retrying in 1 s", e);
                        sleepQuietly(1000);
                        continue;
                    }

                    for (Message msg : messages) {
                        if (!running.get()) break;
                        boolean success = false;
                        try {
                            handler.apply(msg).get();
                            success = true;
                        } catch (Exception e) {
                            Throwable cause = (e.getCause() != null) ? e.getCause() : e;
                            if (options.errorHandler != null) {
                                try {
                                    options.errorHandler.accept(msg, cause);
                                } catch (Exception handlerEx) {
                                    LOG.log(Level.WARNING, "errorHandler threw", handlerEx);
                                }
                            } else {
                                LOG.log(Level.WARNING, "Message handler failed for msg_id=" + msg.msgId, cause);
                            }
                        }

                        if (success) {
                            processedCount.incrementAndGet();
                            if (options.autoAck && options.groupName != null) {
                                try {
                                    ack(mailAddress, options.groupName, msg.msgId).get();
                                } catch (Exception ackEx) {
                                    LOG.log(Level.WARNING, "ACK failed for msg_id=" + msg.msgId, ackEx);
                                }
                            }
                        }
                    }
                }
            } finally {
                running.set(false);
                doneFuture.complete(null);
            }
        });

        Consumer consumer = new Consumer(running, processedCount, doneFuture);
        return CompletableFuture.completedFuture(consumer);
    }

    /**
     * Queries messages in a mailbox without advancing any consumer group offset.
     *
     * @param mailAddress target mailbox
     * @param key         dedup key filter; {@code null} to omit
     * @param limit       max results; {@code null} to omit
     * @param since       Unix timestamp (seconds) lower bound; {@code null} to omit
     */
    public CompletableFuture<List<Message>> query(
            String mailAddress, String key, Long limit, Long since) {
        return CompletableFuture.supplyAsync(() -> {
            ObjectNode req = MAPPER.createObjectNode();
            if (key != null) req.put("key", key);
            if (limit != null) req.put("limit", limit);
            if (since != null) req.put("since", since);

            JsonNode resp = request(PREFIX + ".MSG.QUERY." + mailAddress, toBytes(req));
            checkError(resp);
            return parseMessages(resp.get("messages"));
        });
    }

    /**
     * Deletes a specific message from {@code mailAddress}.
     */
    public CompletableFuture<Void> delete(String mailAddress, long msgId) {
        return CompletableFuture.supplyAsync(() -> {
            String subject = PREFIX + ".MSG.DELETE." + mailAddress + "." + msgId;
            JsonNode resp = request(subject, new byte[0]);
            checkError(resp);
            return (Void) null;
        });
    }

    // -------------------------------------------------------------------------
    // Agent registry
    // -------------------------------------------------------------------------

    /**
     * Registers an agent. The {@code agentCard} map must contain at least
     * a {@code "mailbox"} key.
     */
    public CompletableFuture<Void> agentRegister(Map<String, Object> agentCard) {
        return agentCommand(PREFIX + ".AGENT.REGISTER", agentCard);
    }

    /**
     * Unregisters the agent identified by {@code mailbox}.
     */
    public CompletableFuture<Void> agentUnregister(String mailbox) {
        Map<String, Object> body = new HashMap<>();
        body.put("mailbox", mailbox);
        return agentCommand(PREFIX + ".AGENT.UNREGISTER", body);
    }

    /**
     * Reports agent status/metrics.  The {@code report} map must contain at
     * least a {@code "mailbox"} key.
     */
    public CompletableFuture<Void> agentReport(Map<String, Object> report) {
        return agentCommand(PREFIX + ".AGENT.REPORT", report);
    }

    /**
     * Discovers agents matching the given criteria.
     *
     * @param text     free-text search; {@code null} to omit
     * @param semantic semantic search query; {@code null} to omit
     * @param limit    max results; {@code null} defaults to broker default (20)
     * @param page     1-based page number; {@code null} defaults to 1
     * @return list of agent-card maps returned by the broker
     */
    public CompletableFuture<List<Map<String, Object>>> agentDiscover(
            String text, String semantic, Integer limit, Integer page) {
        return CompletableFuture.supplyAsync(() -> {
            ObjectNode req = MAPPER.createObjectNode();
            if (text != null) req.put("text", text);
            if (semantic != null) req.put("semantic", semantic);
            if (limit != null) req.put("limit", limit);
            if (page != null) req.put("page", page);

            JsonNode resp = request(PREFIX + ".AGENT.DISCOVER", toBytes(req));
            checkError(resp);

            JsonNode agentsNode = resp.get("agents");
            if (agentsNode == null || agentsNode.isNull()) return List.of();

            List<Map<String, Object>> result = new ArrayList<>();
            for (JsonNode node : agentsNode) {
                result.add(MAPPER.convertValue(node, new TypeReference<>() {}));
            }
            return result;
        });
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private CompletableFuture<Void> agentCommand(String subject, Map<String, Object> body) {
        return CompletableFuture.supplyAsync(() -> {
            byte[] payload;
            try {
                payload = MAPPER.writeValueAsBytes(body);
            } catch (Exception e) {
                throw new Mq9Error("Failed to serialize request", e);
            }
            JsonNode resp = request(subject, payload);
            checkError(resp);
            return (Void) null;
        });
    }

    /** Synchronous NATS request/reply.  Called from within supplyAsync lambdas. */
    private JsonNode request(String subject, byte[] payload) {
        try {
            io.nats.client.Message reply = nc.request(subject, payload, options.requestTimeout);
            if (reply == null) {
                throw new Mq9Error("Request timed out: " + subject);
            }
            return parseJson(reply.getData());
        } catch (Mq9Error e) {
            throw e;
        } catch (Exception e) {
            throw new Mq9Error("NATS request failed: " + subject, e);
        }
    }

    /** Send a message with NATS headers (used for MSG.SEND). */
    private io.nats.client.Message requestWithHeaders(String subject, Headers headers, byte[] payload) {
        try {
            io.nats.client.Message reply =
                    nc.request(subject, headers, payload, options.requestTimeout);
            if (reply == null) {
                throw new Mq9Error("Request timed out: " + subject);
            }
            return reply;
        } catch (Mq9Error e) {
            throw e;
        } catch (Exception e) {
            throw new Mq9Error("NATS request failed: " + subject, e);
        }
    }

    private static JsonNode parseJson(byte[] data) {
        try {
            return MAPPER.readTree(data);
        } catch (Exception e) {
            throw new Mq9Error("Failed to parse server response: "
                    + new String(data, StandardCharsets.UTF_8), e);
        }
    }

    private static void checkError(JsonNode node) {
        JsonNode errorNode = node.get("error");
        if (errorNode != null && !errorNode.asText().isEmpty()) {
            throw new Mq9Error(errorNode.asText());
        }
    }

    private static byte[] toBytes(ObjectNode node) {
        try {
            return MAPPER.writeValueAsBytes(node);
        } catch (Exception e) {
            throw new Mq9Error("Failed to serialize request", e);
        }
    }

    private static Headers buildSendHeaders(SendOptions opts) {
        Headers h = new Headers();
        if (opts != null) {
            if (opts.priority != null) {
                h.add("mq9-priority", opts.priority.value);
            }
            if (opts.key != null) {
                h.add("mq9-key", opts.key);
            }
            if (opts.delay != null) {
                h.add("mq9-delay", String.valueOf(opts.delay));
            }
            if (opts.ttl != null) {
                h.add("mq9-ttl", String.valueOf(opts.ttl));
            }
            if (opts.tags != null && !opts.tags.isEmpty()) {
                h.add("mq9-tags", String.join(",", opts.tags));
            }
        }
        return h;
    }

    private static ObjectNode buildFetchRequest(FetchOptions opts) {
        ObjectNode req = MAPPER.createObjectNode();
        if (opts.groupName != null) req.put("group_name", opts.groupName);
        req.put("deliver", opts.deliver);
        if (opts.fromTime != null) req.put("from_time", opts.fromTime);
        if (opts.fromId != null) req.put("from_id", opts.fromId);
        req.put("force_deliver", opts.forceDeliver);

        ObjectNode config = req.putObject("config");
        config.put("num_msgs", opts.numMsgs);
        config.put("max_wait_ms", opts.maxWaitMs);

        return req;
    }

    private static List<Message> parseMessages(JsonNode messagesNode) {
        List<Message> result = new ArrayList<>();
        if (messagesNode == null || messagesNode.isNull()) return result;

        for (JsonNode node : messagesNode) {
            long msgId = node.get("msg_id").asLong();
            String payloadB64 = node.has("payload") ? node.get("payload").asText() : "";
            byte[] payload = payloadB64.isEmpty()
                    ? new byte[0]
                    : Base64.getDecoder().decode(payloadB64);
            Priority priority = Priority.fromValue(
                    node.has("priority") ? node.get("priority").asText() : null);
            long createTime = node.has("create_time") ? node.get("create_time").asLong() : 0L;

            result.add(new Message(msgId, payload, priority, createTime));
        }
        return result;
    }

    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
