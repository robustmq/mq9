// mq9 C# SDK — Agent Demo
//
// Demonstrates:
//  1. Agent registers its capabilities
//  2. Agent sends heartbeat via report
//  3. Discover by full-text search
//  4. Discover by semantic search
//  5. Send a task to discovered agent's mailbox
//  6. Agent unregisters at shutdown

using System.Text.Json;
using Mq9;

internal static class AgentDemo
{
    private static readonly string Server =
        Environment.GetEnvironmentVariable("MQ9_SERVER") ?? "nats://demo.robustmq.com:4222";

    public static async Task RunAsync()
    {
        await using var client = new Mq9Client(Server);
        await client.ConnectAsync();

        // ── 1. Create mailbox for the agent ─────────────────────────────
        var address = await client.MailboxCreateAsync(name: "demo.csharp.translator", ttl: 300);
        Console.WriteLine($"[mailbox] agent mailbox: {address}");

        // ── 2. Register agent ────────────────────────────────────────────
        await client.AgentRegisterAsync(new Dictionary<string, object>
        {
            ["name"]    = "demo.csharp.translator",
            ["mailbox"] = address,
            ["payload"] = "Multilingual translation agent. Supports EN, ZH, JA, KO. " +
                          "Input: text + target language. Output: translated text.",
        });
        Console.WriteLine("[register] agent registered: demo.csharp.translator");

        // ── 3. Send heartbeat ────────────────────────────────────────────
        await client.AgentReportAsync(new Dictionary<string, object>
        {
            ["name"]        = "demo.csharp.translator",
            ["mailbox"]     = address,
            ["report_info"] = "running, processed: 64 tasks, avg latency: 310ms",
        });
        Console.WriteLine("[report] heartbeat sent");

        // ── 4. Discover by full-text search ──────────────────────────────
        var byText = await client.AgentDiscoverAsync(text: "translator", limit: 5);
        Console.WriteLine($"\n[discover] text='translator' → {byText.Count} result(s):");
        foreach (var a in byText)
            Console.WriteLine($"  name={a.GetValueOrDefault("name")}  mailbox={a.GetValueOrDefault("mailbox")}");

        // ── 5. Discover by semantic search ───────────────────────────────
        var bySemantic = await client.AgentDiscoverAsync(
            semantic: "I need to translate Chinese text into English", limit: 5);
        Console.WriteLine($"\n[discover] semantic='translate Chinese to English' → {bySemantic.Count} result(s):");
        foreach (var a in bySemantic)
            Console.WriteLine($"  name={a.GetValueOrDefault("name")}  mailbox={a.GetValueOrDefault("mailbox")}");

        // ── 6. Send a task to the discovered agent ────────────────────────
        if (bySemantic.Count > 0)
        {
            var target = bySemantic[0].GetValueOrDefault("mailbox")?.ToString();
            if (!string.IsNullOrEmpty(target))
            {
                var replyAddress = await client.MailboxCreateAsync(ttl: 60);
                var payload = JsonSerializer.SerializeToUtf8Bytes(new
                {
                    text        = "你好，世界",
                    target_lang = "en",
                    reply_to    = replyAddress,
                });
                var msgId = await client.SendAsync(target, payload);
                Console.WriteLine($"\n[send] task sent to {target}  msg_id={msgId}");
                Console.WriteLine($"[send] reply_to={replyAddress}");
            }
        }

        // ── 7. List all registered agents ────────────────────────────────
        var all = await client.AgentDiscoverAsync(limit: 20);
        Console.WriteLine($"\n[discover] all agents → {all.Count} registered");

        // ── 8. Unregister at shutdown ─────────────────────────────────────
        await client.AgentUnregisterAsync(address);
        Console.WriteLine($"\n[unregister] agent {address} unregistered");
    }
}
