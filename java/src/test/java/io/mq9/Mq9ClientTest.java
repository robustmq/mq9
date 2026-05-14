package io.mq9;

import io.nats.client.Connection;
import io.nats.client.impl.Headers;
import io.nats.client.impl.NatsMessage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class Mq9ClientTest {

    @Mock
    private Connection mockConn;

    private Mq9Client client;

    @BeforeEach
    void setUp() {
        ClientOptions opts = ClientOptions.builder()
                .requestTimeout(Duration.ofSeconds(5))
                .build();
        client = new Mq9Client(mockConn, opts);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private io.nats.client.Message natsMsg(String json) {
        return NatsMessage.builder()
                .subject("_reply")
                .data(json.getBytes(StandardCharsets.UTF_8))
                .build();
    }

    private void givenRequest(String subjectContains, String jsonResponse) throws Exception {
        when(mockConn.request(contains(subjectContains), any(byte[].class), any(Duration.class)))
                .thenReturn(natsMsg(jsonResponse));
    }

    /**
     * Stubs nc.request(subject, headers, payload, timeout) — used for MSG.SEND.
     */
    @SuppressWarnings("unchecked")
    private void givenRequestWithHeaders(String subjectContains, String jsonResponse) throws Exception {
        when(mockConn.request(contains(subjectContains), any(Headers.class), any(byte[].class), any(Duration.class)))
                .thenReturn(natsMsg(jsonResponse));
    }

    // -------------------------------------------------------------------------
    // mailboxCreate
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("mailboxCreate")
    class MailboxCreateTests {

        @Test
        @DisplayName("returns mail_address when name is provided")
        void withName() throws Exception {
            givenRequest("MAILBOX.CREATE",
                    "{\"error\":\"\",\"mail_address\":\"agent.inbox\"}");

            String addr = client.mailboxCreate("agent.inbox", 3600).get();

            assertEquals("agent.inbox", addr);
            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("MAILBOX.CREATE"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"name\":\"agent.inbox\""));
            assertTrue(body.contains("\"ttl\":3600"));
        }

        @Test
        @DisplayName("omits name field when name is null")
        void withoutName() throws Exception {
            givenRequest("MAILBOX.CREATE",
                    "{\"error\":\"\",\"mail_address\":\"auto.xyz\"}");

            String addr = client.mailboxCreate(null, 0).get();

            assertEquals("auto.xyz", addr);
            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("MAILBOX.CREATE"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertFalse(body.contains("\"name\""), "name should be absent when null");
        }

        @Test
        @DisplayName("throws Mq9Error when server returns error")
        void serverError() throws Exception {
            givenRequest("MAILBOX.CREATE",
                    "{\"error\":\"name already taken\",\"mail_address\":\"\"}");

            var ex = assertThrows(Exception.class,
                    () -> client.mailboxCreate("taken", 0).get());
            assertTrue(ex.getCause() instanceof Mq9Error);
            assertTrue(ex.getCause().getMessage().contains("name already taken"));
        }
    }

    // -------------------------------------------------------------------------
    // send
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("send")
    class SendTests {

        @Test
        @DisplayName("returns msg_id and sends priority header")
        void withPriority() throws Exception {
            givenRequestWithHeaders("MSG.SEND.box1",
                    "{\"error\":\"\",\"msg_id\":42}");

            SendOptions opts = SendOptions.builder()
                    .priority(Priority.URGENT)
                    .build();
            long id = client.send("box1", "hello".getBytes(), opts).get();

            assertEquals(42L, id);
            ArgumentCaptor<Headers> headersCaptor = ArgumentCaptor.forClass(Headers.class);
            ArgumentCaptor<String> subjectCaptor = ArgumentCaptor.forClass(String.class);
            verify(mockConn).request(subjectCaptor.capture(), headersCaptor.capture(),
                    any(byte[].class), any(Duration.class));
            assertEquals("$mq9.AI.MSG.SEND.box1", subjectCaptor.getValue());
            assertEquals("urgent", headersCaptor.getValue().getFirst("mq9-priority"));
        }

        @Test
        @DisplayName("sends key, delay, ttl, tags headers")
        void withAllHeaders() throws Exception {
            givenRequestWithHeaders("MSG.SEND.box2",
                    "{\"error\":\"\",\"msg_id\":7}");

            SendOptions opts = SendOptions.builder()
                    .priority(Priority.CRITICAL)
                    .key("dedup-abc")
                    .delay(30L)
                    .ttl(600L)
                    .tags(List.of("alpha", "beta"))
                    .build();
            long id = client.send("box2", new byte[]{1, 2}, opts).get();

            assertEquals(7L, id);
            ArgumentCaptor<Headers> headersCaptor = ArgumentCaptor.forClass(Headers.class);
            verify(mockConn).request(contains("MSG.SEND.box2"), headersCaptor.capture(),
                    any(byte[].class), any(Duration.class));
            Headers h = headersCaptor.getValue();
            assertEquals("critical", h.getFirst("mq9-priority"));
            assertEquals("dedup-abc", h.getFirst("mq9-key"));
            assertEquals("30", h.getFirst("mq9-delay"));
            assertEquals("600", h.getFirst("mq9-ttl"));
            assertEquals("alpha,beta", h.getFirst("mq9-tags"));
        }

        @Test
        @DisplayName("returns -1 for delayed messages")
        void delayedMsgId() throws Exception {
            givenRequestWithHeaders("MSG.SEND.box3",
                    "{\"error\":\"\",\"msg_id\":-1}");

            long id = client.send("box3", new byte[0],
                    SendOptions.builder().delay(60L).build()).get();

            assertEquals(-1L, id);
        }
    }

    // -------------------------------------------------------------------------
    // fetch
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("fetch")
    class FetchTests {

        @Test
        @DisplayName("stateless fetch returns decoded messages")
        void statelessFetch() throws Exception {
            String b64 = Base64.getEncoder().encodeToString("world".getBytes());
            givenRequest("MSG.FETCH.mailA",
                    "{\"error\":\"\",\"messages\":[" +
                    "{\"msg_id\":1,\"payload\":\"" + b64 + "\",\"priority\":\"normal\",\"create_time\":1000}" +
                    "]}");

            List<Message> msgs = client.fetch("mailA", FetchOptions.builder().build()).get();

            assertEquals(1, msgs.size());
            Message m = msgs.get(0);
            assertEquals(1L, m.msgId);
            assertArrayEquals("world".getBytes(), m.payload);
            assertEquals(Priority.NORMAL, m.priority);
            assertEquals(1000L, m.createTime);
        }

        @Test
        @DisplayName("stateful fetch sends group_name")
        void statefulFetch() throws Exception {
            givenRequest("MSG.FETCH.mailB",
                    "{\"error\":\"\",\"messages\":[]}");

            FetchOptions opts = FetchOptions.builder()
                    .groupName("worker-1")
                    .numMsgs(50)
                    .build();
            List<Message> msgs = client.fetch("mailB", opts).get();

            assertTrue(msgs.isEmpty());
            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("MSG.FETCH.mailB"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"group_name\":\"worker-1\""));
            assertTrue(body.contains("\"num_msgs\":50"));
        }

        @Test
        @DisplayName("returns empty list when messages array is absent")
        void emptyMessages() throws Exception {
            givenRequest("MSG.FETCH.mailC",
                    "{\"error\":\"\",\"messages\":[]}");

            List<Message> msgs = client.fetch("mailC", FetchOptions.builder().build()).get();

            assertTrue(msgs.isEmpty());
        }
    }

    // -------------------------------------------------------------------------
    // ack
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("ack")
    class AckTests {

        @Test
        @DisplayName("sends correct body")
        void correctBody() throws Exception {
            givenRequest("MSG.ACK.mybox",
                    "{\"error\":\"\"}");

            client.ack("mybox", "grp-1", 99L).get();

            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("MSG.ACK.mybox"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"group_name\":\"grp-1\""));
            assertTrue(body.contains("\"mail_address\":\"mybox\""));
            assertTrue(body.contains("\"msg_id\":99"));
        }
    }

    // -------------------------------------------------------------------------
    // consume
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("consume")
    class ConsumeTests {

        @Test
        @DisplayName("happy path: handler called, processedCount incremented, autoAck sent")
        void happyPath() throws Exception {
            String b64 = Base64.getEncoder().encodeToString("data".getBytes());
            // First fetch returns one message, subsequent fetches return empty
            when(mockConn.request(contains("MSG.FETCH"), any(byte[].class), any(Duration.class)))
                    .thenReturn(natsMsg("{\"error\":\"\",\"messages\":[" +
                            "{\"msg_id\":5,\"payload\":\"" + b64 + "\",\"priority\":\"normal\",\"create_time\":0}" +
                            "]}"))
                    .thenReturn(natsMsg("{\"error\":\"\",\"messages\":[]}"));

            when(mockConn.request(contains("MSG.ACK"), any(byte[].class), any(Duration.class)))
                    .thenReturn(natsMsg("{\"error\":\"\"}"));

            CountDownLatch processed = new CountDownLatch(1);
            ConsumeOptions opts = ConsumeOptions.builder()
                    .groupName("g1")
                    .autoAck(true)
                    .build();

            Consumer consumer = client.consume("inbox",
                    msg -> {
                        processed.countDown();
                        return CompletableFuture.completedFuture(null);
                    }, opts).get();

            assertTrue(processed.await(3, TimeUnit.SECONDS), "handler should be called");
            consumer.stop().get(2, TimeUnit.SECONDS);

            assertEquals(1L, consumer.getProcessedCount());
            assertFalse(consumer.isRunning());
            verify(mockConn, atLeastOnce()).request(contains("MSG.ACK"), any(byte[].class), any(Duration.class));
        }

        @Test
        @DisplayName("handler error: errorHandler called, no ACK, loop continues")
        void handlerError() throws Exception {
            String b64 = Base64.getEncoder().encodeToString("bad".getBytes());
            when(mockConn.request(contains("MSG.FETCH"), any(byte[].class), any(Duration.class)))
                    .thenReturn(natsMsg("{\"error\":\"\",\"messages\":[" +
                            "{\"msg_id\":3,\"payload\":\"" + b64 + "\",\"priority\":\"normal\",\"create_time\":0}" +
                            "]}"))
                    .thenReturn(natsMsg("{\"error\":\"\",\"messages\":[]}"));

            AtomicReference<Throwable> captured = new AtomicReference<>();
            CountDownLatch errLatch = new CountDownLatch(1);

            ConsumeOptions opts = ConsumeOptions.builder()
                    .groupName("g2")
                    .autoAck(true)
                    .errorHandler((msg, err) -> {
                        captured.set(err);
                        errLatch.countDown();
                    })
                    .build();

            Consumer consumer = client.consume("errbox",
                    msg -> CompletableFuture.failedFuture(new RuntimeException("boom")),
                    opts).get();

            assertTrue(errLatch.await(3, TimeUnit.SECONDS));
            consumer.stop().get(2, TimeUnit.SECONDS);

            assertNotNull(captured.get());
            assertEquals("boom", captured.get().getMessage());
            assertEquals(0L, consumer.getProcessedCount());
            // ACK must NOT be sent
            verify(mockConn, never()).request(contains("MSG.ACK"), any(byte[].class), any(Duration.class));
        }

        @Test
        @DisplayName("stop() completes doneFuture and isRunning becomes false")
        void stopBehavior() throws Exception {
            lenient().when(mockConn.request(contains("MSG.FETCH"), any(byte[].class), any(Duration.class)))
                    .thenReturn(natsMsg("{\"error\":\"\",\"messages\":[]}"));

            ConsumeOptions opts = ConsumeOptions.builder().build();
            Consumer consumer = client.consume("stopbox",
                    msg -> CompletableFuture.completedFuture(null),
                    opts).get();

            assertTrue(consumer.isRunning());
            consumer.stop().get(2, TimeUnit.SECONDS);
            assertFalse(consumer.isRunning());
        }
    }

    // -------------------------------------------------------------------------
    // query
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("query")
    class QueryTests {

        @Test
        @DisplayName("sends optional fields and returns messages")
        void withOptions() throws Exception {
            String b64 = Base64.getEncoder().encodeToString("qdata".getBytes());
            givenRequest("MSG.QUERY.qbox",
                    "{\"error\":\"\",\"messages\":[" +
                    "{\"msg_id\":8,\"payload\":\"" + b64 + "\",\"priority\":\"urgent\",\"create_time\":500}" +
                    "]}");

            List<Message> msgs = client.query("qbox", "mykey", 5L, 1000L).get();

            assertEquals(1, msgs.size());
            assertEquals(8L, msgs.get(0).msgId);
            assertEquals(Priority.URGENT, msgs.get(0).priority);

            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("MSG.QUERY.qbox"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"key\":\"mykey\""));
            assertTrue(body.contains("\"limit\":5"));
            assertTrue(body.contains("\"since\":1000"));
        }

        @Test
        @DisplayName("omits null optional fields")
        void withNulls() throws Exception {
            givenRequest("MSG.QUERY.qbox2",
                    "{\"error\":\"\",\"messages\":[]}");

            List<Message> msgs = client.query("qbox2", null, null, null).get();

            assertTrue(msgs.isEmpty());
            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("MSG.QUERY.qbox2"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertFalse(body.contains("\"key\""));
            assertFalse(body.contains("\"limit\""));
            assertFalse(body.contains("\"since\""));
        }
    }

    // -------------------------------------------------------------------------
    // delete
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("delete")
    class DeleteTests {

        @Test
        @DisplayName("sends delete with correct subject")
        void correctSubject() throws Exception {
            givenRequest("MSG.DELETE.mybox.77",
                    "{\"error\":\"\"}");

            client.delete("mybox", 77L).get();

            verify(mockConn).request(eq("$mq9.AI.MSG.DELETE.mybox.77"), any(byte[].class), any());
        }
    }

    // -------------------------------------------------------------------------
    // agentRegister
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("agentRegister")
    class AgentRegisterTests {

        @Test
        @DisplayName("sends agent card to AGENT.REGISTER")
        void register() throws Exception {
            givenRequest("AGENT.REGISTER",
                    "{\"error\":\"\"}");

            Map<String, Object> card = Map.of("mailbox", "agent.abc", "name", "TestAgent");
            client.agentRegister(card).get();

            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("AGENT.REGISTER"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"mailbox\":\"agent.abc\""));
            assertTrue(body.contains("\"name\":\"TestAgent\""));
        }
    }

    // -------------------------------------------------------------------------
    // agentUnregister
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("agentUnregister")
    class AgentUnregisterTests {

        @Test
        @DisplayName("sends mailbox to AGENT.UNREGISTER")
        void unregister() throws Exception {
            givenRequest("AGENT.UNREGISTER",
                    "{\"error\":\"\"}");

            client.agentUnregister("agent.abc").get();

            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("AGENT.UNREGISTER"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"mailbox\":\"agent.abc\""));
        }
    }

    // -------------------------------------------------------------------------
    // agentReport
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("agentReport")
    class AgentReportTests {

        @Test
        @DisplayName("sends report to AGENT.REPORT")
        void report() throws Exception {
            givenRequest("AGENT.REPORT",
                    "{\"error\":\"\"}");

            Map<String, Object> report = Map.of("mailbox", "agent.xyz", "status", "healthy");
            client.agentReport(report).get();

            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("AGENT.REPORT"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"mailbox\":\"agent.xyz\""));
            assertTrue(body.contains("\"status\":\"healthy\""));
        }
    }

    // -------------------------------------------------------------------------
    // agentDiscover
    // -------------------------------------------------------------------------

    @Nested
    @DisplayName("agentDiscover")
    class AgentDiscoverTests {

        @Test
        @DisplayName("returns agents list with text/semantic query")
        void discover() throws Exception {
            givenRequest("AGENT.DISCOVER",
                    "{\"error\":\"\",\"agents\":[{\"mailbox\":\"a1\",\"name\":\"Agent1\"},{\"mailbox\":\"a2\",\"name\":\"Agent2\"}]}");

            List<Map<String, Object>> agents =
                    client.agentDiscover("search text", "semantic query", 10, 1).get();

            assertEquals(2, agents.size());
            assertEquals("a1", agents.get(0).get("mailbox"));
            assertEquals("Agent2", agents.get(1).get("name"));

            ArgumentCaptor<byte[]> captor = ArgumentCaptor.forClass(byte[].class);
            verify(mockConn).request(contains("AGENT.DISCOVER"), captor.capture(), any());
            String body = new String(captor.getValue(), StandardCharsets.UTF_8);
            assertTrue(body.contains("\"text\":\"search text\""));
            assertTrue(body.contains("\"semantic\":\"semantic query\""));
            assertTrue(body.contains("\"limit\":10"));
            assertTrue(body.contains("\"page\":1"));
        }

        @Test
        @DisplayName("returns empty list when agents is null")
        void emptyAgents() throws Exception {
            givenRequest("AGENT.DISCOVER",
                    "{\"error\":\"\",\"agents\":null}");

            List<Map<String, Object>> agents =
                    client.agentDiscover(null, null, null, null).get();

            assertTrue(agents.isEmpty());
        }
    }
}
