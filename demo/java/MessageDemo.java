/**
 * mq9 Java SDK — Message Demo
 *
 * Demonstrates:
 *   1. Create a mailbox
 *   2. Send messages with different priorities
 *   3. Fetch + ACK (stateful consumption)
 *   4. Consume loop (auto poll)
 *   5. Message attributes: key dedup, tags, delay, ttl
 *   6. Query without affecting offset
 *   7. Delete a message
 *
 * Compile & run:
 *   mvn compile exec:java -Dexec.mainClass=MessageDemo
 */

import io.mq9.*;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class MessageDemo {

    private static final String SERVER = "nats://demo.robustmq.com:4222";

    public static void main(String[] args) throws Exception {
        Mq9Client client = Mq9Client.connect(SERVER).get();

        try {
            // ── 1. Create a mailbox ──────────────────────────────────────
            String address = client.mailboxCreate("demo.java.message", 300).get();
            System.out.println("[mailbox] created: " + address);

            // ── 2. Send messages with different priorities ───────────────
            long mid1 = client.send(address, "{\"type\":\"task\",\"id\":1}".getBytes(),
                SendOptions.builder().build()).get();
            System.out.println("[send] normal    msg_id=" + mid1);

            long mid2 = client.send(address, "{\"type\":\"interrupt\",\"id\":2}".getBytes(),
                SendOptions.builder().priority(Priority.URGENT).build()).get();
            System.out.println("[send] urgent    msg_id=" + mid2);

            long mid3 = client.send(address, "{\"type\":\"abort\",\"id\":3}".getBytes(),
                SendOptions.builder().priority(Priority.CRITICAL).build()).get();
            System.out.println("[send] critical  msg_id=" + mid3);

            // ── 3. Message attributes ────────────────────────────────────
            // Key dedup: only the latest message with key="status" is kept
            client.send(address, "{\"status\":\"running\"}".getBytes(),
                SendOptions.builder().key("status").build()).get();
            client.send(address, "{\"status\":\"60%\"}".getBytes(),
                SendOptions.builder().key("status").build()).get();
            long midStatus = client.send(address, "{\"status\":\"done\"}".getBytes(),
                SendOptions.builder().key("status").build()).get();
            System.out.println("[send] dedup key=status, latest msg_id=" + midStatus);

            // Tags
            client.send(address, "{\"order\":\"o-001\"}".getBytes(),
                SendOptions.builder().tags(List.of("billing", "vip")).build()).get();
            System.out.println("[send] with tags billing,vip");

            // Per-message TTL
            client.send(address, "{\"temp\":true}".getBytes(),
                SendOptions.builder().ttl(10L).build()).get();
            System.out.println("[send] with message ttl=10s");

            // Delayed delivery
            long delayedId = client.send(address, "{\"delayed\":true}".getBytes(),
                SendOptions.builder().delay(5L).build()).get();
            System.out.println("[send] delay=5s  msg_id=" + delayedId + " (returns -1 for delayed)");

            // ── 4. Fetch + ACK (stateful) ────────────────────────────────
            List<Message> messages = client.fetch(address, FetchOptions.builder()
                .groupName("workers")
                .deliver("earliest")
                .numMsgs(10)
                .build()).get();
            System.out.println("\n[fetch] got " + messages.size() + " messages (priority order):");
            for (Message msg : messages) {
                System.out.printf("  msg_id=%d  priority=%s  payload=%s%n",
                    msg.msgId, msg.priority, new String(msg.payload));
            }

            if (!messages.isEmpty()) {
                long lastId = messages.get(messages.size() - 1).msgId;
                client.ack(address, "workers", lastId).get();
                System.out.println("[ack]   advanced offset to msg_id=" + lastId);
            }

            // ── 5. Query without affecting offset ────────────────────────
            List<Message> results = client.query(address, "status", null, null).get();
            System.out.println("\n[query] key=status → " + results.size() + " message(s)");
            for (Message msg : results) {
                System.out.printf("  msg_id=%d  payload=%s%n", msg.msgId, new String(msg.payload));
            }

            // ── 6. Consume loop ──────────────────────────────────────────
            System.out.println("\n[consume] starting loop for 3 s …");

            Consumer consumer = client.consume(address, msg -> {
                System.out.printf("  [handler] msg_id=%d  priority=%s  payload=%s%n",
                    msg.msgId, msg.priority, new String(msg.payload));
                return CompletableFuture.completedFuture(null);
            }, ConsumeOptions.builder()
                .groupName("consume-workers")
                .deliver("earliest")
                .autoAck(true)
                .errorHandler((msg, err) ->
                    System.err.printf("  [error]   msg_id=%d  error=%s%n", msg.msgId, err.getMessage()))
                .build()).get();

            Thread.sleep(3000);
            consumer.stop().get();
            System.out.println("[consume] stopped. processed=" + consumer.getProcessedCount());

            // ── 7. Delete a message ──────────────────────────────────────
            client.delete(address, mid1).get();
            System.out.println("\n[delete] msg_id=" + mid1 + " deleted");

        } finally {
            client.close();
        }
    }
}
