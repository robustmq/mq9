/**
 * mq9 Java SDK — Agent Demo
 *
 * Demonstrates:
 *   1. Agent registers its capabilities
 *   2. Agent sends heartbeat via report
 *   3. Discover by full-text search
 *   4. Discover by semantic search
 *   5. Send a task to discovered agent's mailbox
 *   6. Agent unregisters at shutdown
 *
 * Compile & run:
 *   mvn compile exec:java -Dexec.mainClass=AgentDemo
 */

import io.mq9.*;
import java.util.List;
import java.util.Map;

public class AgentDemo {

    private static final String SERVER = "nats://demo.robustmq.com:4222";

    public static void main(String[] args) throws Exception {
        Mq9Client client = Mq9Client.connect(SERVER).get();

        try {
            // ── 1. Create mailbox for the agent ─────────────────────────
            String address = client.mailboxCreate("demo.java.translator", 300).get();
            System.out.println("[mailbox] agent mailbox: " + address);

            // ── 2. Register agent ────────────────────────────────────────
            client.agentRegister(Map.of(
                "name",    "demo.java.translator",
                "mailbox", address,
                "payload", "Multilingual translation agent. Supports EN, ZH, JA, KO. " +
                           "Input: text + target language. Output: translated text."
            )).get();
            System.out.println("[register] agent registered: demo.java.translator");

            // ── 3. Send heartbeat ────────────────────────────────────────
            client.agentReport(Map.of(
                "name",        "demo.java.translator",
                "mailbox",     address,
                "report_info", "running, processed: 320 tasks"
            )).get();
            System.out.println("[report] heartbeat sent");

            // ── 4. Discover by full-text search ──────────────────────────
            List<Map<String, Object>> byText = client.agentDiscover("translator", null, 5, 1).get();
            System.out.println("\n[discover] text='translator' → " + byText.size() + " result(s):");
            for (Map<String, Object> a : byText) {
                System.out.println("  name=" + a.get("name") + "  mailbox=" + a.get("mailbox"));
            }

            // ── 5. Discover by semantic search ───────────────────────────
            List<Map<String, Object>> bySemantic = client.agentDiscover(
                null, "I need to translate Chinese text into English", 5, 1).get();
            System.out.println("\n[discover] semantic='translate Chinese to English' → " +
                bySemantic.size() + " result(s):");
            for (Map<String, Object> a : bySemantic) {
                System.out.println("  name=" + a.get("name") + "  mailbox=" + a.get("mailbox"));
            }

            // ── 6. Send a task to discovered agent ───────────────────────
            if (!bySemantic.isEmpty()) {
                String target = (String) bySemantic.get(0).get("mailbox");
                if (target != null) {
                    String replyAddress = client.mailboxCreate(null, 60).get();
                    String payload = String.format(
                        "{\"text\":\"你好，世界\",\"target_lang\":\"en\",\"reply_to\":\"%s\"}",
                        replyAddress);
                    long msgId = client.send(target, payload.getBytes(),
                        SendOptions.builder().build()).get();
                    System.out.println("\n[send] task sent to " + target + "  msg_id=" + msgId);
                    System.out.println("[send] reply_to=" + replyAddress);
                }
            }

            // ── 7. List all agents ────────────────────────────────────────
            List<Map<String, Object>> all = client.agentDiscover(null, null, 20, 1).get();
            System.out.println("\n[discover] all agents → " + all.size() + " registered");

            // ── 8. Unregister ─────────────────────────────────────────────
            client.agentUnregister(address).get();
            System.out.println("\n[unregister] agent " + address + " unregistered");

        } finally {
            client.close();
        }
    }
}
