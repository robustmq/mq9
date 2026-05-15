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

import io.a2a.spec.Artifact;
import io.a2a.spec.Message;
import io.a2a.spec.MessageSendParams;
import io.a2a.spec.SendMessageRequest;
import io.a2a.spec.TaskArtifactUpdateEvent;
import io.a2a.spec.TaskState;
import io.a2a.spec.TaskStatus;
import io.a2a.spec.TaskStatusUpdateEvent;
import io.a2a.spec.TextPart;
import io.mq9.a2a.A2AContext;
import io.mq9.a2a.EventQueue;
import io.mq9.a2a.Mq9A2AAgent;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class A2ADemo {

    private static final String SERVER =
            System.getenv().getOrDefault("MQ9_SERVER", "nats://demo.robustmq.com:4222");

    // ── Agent A — translator ───────────────────────────────────────────────────

    static void runAgent() throws Exception {
        Mq9A2AAgent agentA = Mq9A2AAgent.builder().server(SERVER).build();

        // A2A protocol: handler receives tasks and streams back events in order:
        //   WORKING → Artifact(s) → COMPLETED
        agentA.onMessage(
            (A2AContext context, EventQueue queue) -> {
                // Step 1: signal processing has started
                queue.enqueue(new TaskStatusUpdateEvent.Builder()
                        .taskId(context.taskId)
                        .contextId(context.contextId)
                        .status(new TaskStatus(TaskState.WORKING))
                        .isFinal(false)
                        .build()).join();

                // Step 2: extract text from message — A2A messages carry one or more Parts
                String text = "";
                if (context.message != null && context.message.getParts() != null
                        && !context.message.getParts().isEmpty()) {
                    Object part = context.message.getParts().get(0);
                    if (part instanceof TextPart tp) text = tp.getText();
                }
                String translated = "[translated] " + text;
                System.out.println("[agent-a] '" + text + "' → '" + translated + "'");

                // Step 3: push result as Artifact — call multiple times for chunked streaming
                queue.enqueue(new TaskArtifactUpdateEvent.Builder()
                        .taskId(context.taskId)
                        .contextId(context.contextId)
                        .artifact(new Artifact.Builder()
                                .name("translation")
                                .parts(new TextPart(translated))
                                .build())
                        .lastChunk(true)
                        .build()).join();

                // Step 4: signal task is done
                return queue.enqueue(new TaskStatusUpdateEvent.Builder()
                        .taskId(context.taskId)
                        .contextId(context.contextId)
                        .status(new TaskStatus(TaskState.COMPLETED))
                        .isFinal(true)
                        .build());
            },
            "demo.java.translator.workers", "earliest", 10, 500
        );

        agentA.connect().join();
        String mailbox = agentA.createMailbox("demo.java.translator", 0).join();
        System.out.println("[agent-a] mailbox=" + mailbox);

        // agentRegister makes this agent discoverable via agentDiscover
        // (omit AgentCard import — pass null to skip full card registration for the demo)
        System.out.println("[agent-a] running — waiting for tasks (Ctrl+C to stop)");
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            agentA.unregister().join();
            agentA.close();
            System.out.println("[agent-a] shut down");
        }));
        Thread.currentThread().join(); // keep alive
    }

    // ── Agent B — sender + receiver ────────────────────────────────────────────

    static void runClient() throws Exception {
        Mq9A2AAgent agentB = Mq9A2AAgent.builder().server(SERVER).build();

        // Agent B's @on_message receives reply events from Agent A.
        // context.taskId identifies which task the event belongs to.
        CountDownLatch done = new CountDownLatch(1);
        agentB.onMessage(
            (A2AContext context, EventQueue queue) -> {
                System.out.println("[agent-b] reply event  task_id=" + context.taskId);
                if (context.message != null && context.message.getParts() != null) {
                    for (Object part : context.message.getParts()) {
                        if (part instanceof TextPart tp) {
                            System.out.println("[agent-b] text part: " + tp.getText());
                        }
                    }
                }
                done.countDown();
                return java.util.concurrent.CompletableFuture.completedFuture(null);
            },
            "demo.java.sender.workers", "earliest", 10, 500
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

        // send_message returns msg_id; task_id is generated by Agent A (executor)
        // and arrives in @on_message via context.taskId
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
        // Start Agent A in background thread
        Mq9A2AAgent agentA = Mq9A2AAgent.builder().server(SERVER).build();
        agentA.onMessage(
            (A2AContext context, EventQueue queue) -> {
                String text = "";
                if (context.message != null && context.message.getParts() != null
                        && !context.message.getParts().isEmpty()) {
                    Object part = context.message.getParts().get(0);
                    if (part instanceof TextPart tp) text = tp.getText();
                }
                String translated = "[translated] " + text;
                System.out.println("[agent-a] '" + text + "' → '" + translated + "'");

                queue.enqueue(new TaskStatusUpdateEvent.Builder()
                        .taskId(context.taskId).contextId(context.contextId)
                        .status(new TaskStatus(TaskState.WORKING)).isFinal(false).build()).join();
                queue.enqueue(new TaskArtifactUpdateEvent.Builder()
                        .taskId(context.taskId).contextId(context.contextId)
                        .artifact(new Artifact.Builder()
                                .name("translation")
                                .parts(new TextPart(translated)).build())
                        .lastChunk(true).build()).join();
                return queue.enqueue(new TaskStatusUpdateEvent.Builder()
                        .taskId(context.taskId).contextId(context.contextId)
                        .status(new TaskStatus(TaskState.COMPLETED)).isFinal(true).build());
            },
            "demo.java.translator.workers", "earliest", 10, 500
        );

        agentA.connect().join();
        String aMailbox = agentA.createMailbox("demo.java.translator", 0).join();
        System.out.println("[agent-a] mailbox=" + aMailbox);

        Thread.sleep(500); // give consumer a moment before Agent B sends

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
