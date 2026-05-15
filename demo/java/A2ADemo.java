/**
 * mq9 A2A Demo
 * ============
 * Two-way A2A communication over mq9: Agent B sends a task to Agent A
 * (a translator) and receives the result back via its own mailbox.
 *
 * Run two terminals:
 *
 *   Terminal 1 — start Agent A (translator):
 *     mvn compile exec:java -Dexec.mainClass=A2ADemo -Dexec.args=agent
 *
 *   Terminal 2 — run Agent B (sender):
 *     mvn compile exec:java -Dexec.mainClass=A2ADemo -Dexec.args=client
 *
 * Or run both in the same JVM:
 *     mvn compile exec:java -Dexec.mainClass=A2ADemo
 */

import io.a2a.spec.Message;
import io.a2a.spec.MessageSendParams;
import io.a2a.spec.SendMessageRequest;
import io.a2a.spec.TextPart;
import io.mq9.ConsumeOptions;
import io.mq9.a2a.A2AContext;
import io.mq9.a2a.EventQueue;
import io.mq9.a2a.Mq9A2AAgent;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class A2ADemo {

    private static final String SERVER =
            System.getenv().getOrDefault("MQ9_SERVER", "nats://demo.robustmq.com:4222");

    // ── Agent A — translator ───────────────────────────────────────────────────

    static void runAgent() throws Exception {
        Mq9A2AAgent agentA = Mq9A2AAgent.builder().server(SERVER).build();

        // A2A protocol event sequence: WORKING → Artifact → COMPLETED
        agentA.onMessage(
            (A2AContext ctx, EventQueue queue) ->
                // A2A protocol: WORKING first — tells the sender processing has started
                queue.working(ctx)
                    .thenCompose(v -> {
                        // A2A protocol: message body is one or more Parts; get the first text
                        String text = ctx.firstTextPart().orElse("");
                        String translated = "[translated] " + text;
                        System.out.println("[agent-a] '" + text + "' → '" + translated + "'");
                        // A2A protocol: push result as Artifact — call multiple times for streaming
                        return queue.artifact(ctx, "translation", translated);
                    })
                    // A2A protocol: COMPLETED last — signals the task is done
                    .thenCompose(v -> queue.completed(ctx)),
            ConsumeOptions.builder()
                .groupName("demo.java.translator.workers")
                .deliver("earliest")
                .numMsgs(10)
                .maxWaitMs(500)
                .build()
        );

        agentA.connect().join();
        String mailbox = agentA.createMailbox("demo.java.translator", 0).join();
        System.out.println("[agent-a] mailbox=" + mailbox);
        System.out.println("[agent-a] running — waiting for tasks (Ctrl+C to stop)");

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            agentA.unregister().join();
            agentA.close();
            System.out.println("[agent-a] shut down");
        }));
        Thread.currentThread().join();
    }

    // ── Agent B — sender + receiver ────────────────────────────────────────────

    static void runClient() throws Exception {
        Mq9A2AAgent agentB = Mq9A2AAgent.builder().server(SERVER).build();

        CountDownLatch done = new CountDownLatch(1);

        // All messages arrive here — both reply events and new incoming tasks.
        // Use context.taskId to tell them apart: if it matches a task you sent,
        // it's a reply; otherwise it's a new task from another agent.
        agentB.onMessage(
            (A2AContext ctx, EventQueue queue) -> {
                System.out.println("[agent-b] reply event  task_id=" + ctx.taskId);
                ctx.firstTextPart().ifPresent(t -> System.out.println("[agent-b] text: " + t));
                done.countDown();
                return CompletableFuture.completedFuture(null);
            },
            ConsumeOptions.builder()
                .groupName("demo.java.sender.workers")
                .deliver("earliest")
                .numMsgs(10)
                .maxWaitMs(500)
                .build()
        );

        agentB.connect().join();
        String bMailbox = agentB.createMailbox("demo.java.sender", 300).join();
        System.out.println("[agent-b] mailbox=" + bMailbox);

        // Discover Agent A
        System.out.println("[agent-b] discovering translator agents…");
        List<Map<String, Object>> agents = agentB.discover("translation", false, 5).join();
        if (agents.isEmpty()) {
            System.out.println("[agent-b] no agents found — is agent-a running?");
            agentB.close();
            return;
        }
        Map<String, Object> target = agents.get(0);
        System.out.println("[agent-b] found: name=" + target.get("name")
                + "  mailbox=" + target.get("mailbox"));

        // Build A2A SendMessageRequest — message body is one or more Parts
        Message msg = new Message.Builder()
                .role(Message.Role.USER)
                .parts(new TextPart("你好，世界"))
                .build();
        SendMessageRequest request = new SendMessageRequest(
                null, new MessageSendParams(msg, null, null));

        // sendMessage returns msg_id; task_id is generated by Agent A (the executor)
        // and arrives with reply events, readable as context.taskId in onMessage
        System.out.println("[agent-b] sending task…");
        long msgId = agentB.sendMessage(target, request, bMailbox).join();
        System.out.println("[agent-b] sent  msg_id=" + msgId);

        System.out.println("[agent-b] waiting for reply…");
        boolean received = done.await(15, TimeUnit.SECONDS);
        if (!received) System.out.println("[agent-b] timed out waiting for reply");

        System.out.println("[agent-b] done.");
        agentB.close();
    }

    // ── Combined mode ──────────────────────────────────────────────────────────

    static void runBoth() throws Exception {
        Mq9A2AAgent agentA = Mq9A2AAgent.builder().server(SERVER).build();

        agentA.onMessage(
            (A2AContext ctx, EventQueue queue) ->
                queue.working(ctx)
                    .thenCompose(v -> {
                        String text = ctx.firstTextPart().orElse("");
                        System.out.println("[agent-a] translating: '" + text + "'");
                        return queue.artifact(ctx, "translation", "[translated] " + text);
                    })
                    .thenCompose(v -> queue.completed(ctx)),
            ConsumeOptions.builder()
                .groupName("demo.java.translator.workers")
                .deliver("earliest")
                .numMsgs(10)
                .maxWaitMs(500)
                .build()
        );

        agentA.connect().join();
        String aMailbox = agentA.createMailbox("demo.java.translator", 0).join();
        System.out.println("[agent-a] mailbox=" + aMailbox);

        Thread.sleep(500);
        runClient();

        agentA.close();
    }

    // ── Entry point ────────────────────────────────────────────────────────────

    public static void main(String[] args) throws Exception {
        String mode = args.length > 0 ? args[0] : "both";
        switch (mode) {
            case "agent"  -> runAgent();
            case "client" -> runClient();
            case "both"   -> runBoth();
            default -> {
                System.out.println("Usage: A2ADemo [agent|client|both]");
                System.exit(1);
            }
        }
    }
}
