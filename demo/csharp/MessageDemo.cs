// mq9 C# SDK — Message Demo
//
// Demonstrates:
//  1. Create a mailbox
//  2. Send messages with different priorities
//  3. Fetch + ACK (stateful consumption)
//  4. Consume loop (auto poll)
//  5. Message attributes: key dedup, tags, delay, ttl
//  6. Query without affecting offset
//  7. Delete a message

using System.Text;
using System.Text.Json;
using Mq9;

internal static class MessageDemo
{
    private static readonly string Server =
        Environment.GetEnvironmentVariable("MQ9_SERVER") ?? "nats://demo.robustmq.com:4222";

    public static async Task RunAsync()
    {
        await using var client = new Mq9Client(Server);
        await client.ConnectAsync();

        // ── 1. Create a mailbox ──────────────────────────────────────────
        var address = await client.MailboxCreateAsync(name: "demo.csharp.message", ttl: 300);
        Console.WriteLine($"[mailbox] created: {address}");

        // ── 2. Send messages with different priorities ───────────────────
        var mid1 = await client.SendAsync(address, Json(new { type = "task", id = 1 }));
        Console.WriteLine($"[send] normal    msg_id={mid1}");

        var mid2 = await client.SendAsync(address, Json(new { type = "interrupt", id = 2 }),
            new SendOptions { Priority = Priority.Urgent });
        Console.WriteLine($"[send] urgent    msg_id={mid2}");

        var mid3 = await client.SendAsync(address, Json(new { type = "abort", id = 3 }),
            new SendOptions { Priority = Priority.Critical });
        Console.WriteLine($"[send] critical  msg_id={mid3}");

        // ── 3. Message attributes ────────────────────────────────────────
        // Key dedup: only the latest message with key="status" is kept
        await client.SendAsync(address, Json(new { status = "running" }), new SendOptions { Key = "status" });
        await client.SendAsync(address, Json(new { status = "60%"     }), new SendOptions { Key = "status" });
        var midStatus = await client.SendAsync(address, Json(new { status = "done" }),
            new SendOptions { Key = "status" });
        Console.WriteLine($"[send] dedup key=status, latest msg_id={midStatus}");

        await client.SendAsync(address, Json(new { order = "o-001" }),
            new SendOptions { Tags = ["billing", "vip"] });
        Console.WriteLine("[send] with tags billing,vip");

        await client.SendAsync(address, Json(new { temp = true }), new SendOptions { Ttl = 10 });
        Console.WriteLine("[send] with message ttl=10s");

        var delayedId = await client.SendAsync(address, Json(new { delayed = true }),
            new SendOptions { Delay = 5 });
        Console.WriteLine($"[send] delay=5s  msg_id={delayedId} (returns -1 for delayed)");

        // ── 4. Fetch + ACK (stateful) ────────────────────────────────────
        var messages = await client.FetchAsync(address,
            new FetchOptions { GroupName = "workers", Deliver = "earliest", NumMsgs = 10 });

        Console.WriteLine($"\n[fetch] got {messages.Count} messages (priority order):");
        foreach (var msg in messages)
            Console.WriteLine($"  msg_id={msg.MsgId}  priority={msg.Priority}  payload={Text(msg.Payload)}");

        if (messages.Count > 0)
        {
            await client.AckAsync(address, "workers", messages[^1].MsgId);
            Console.WriteLine($"[ack]   advanced offset to msg_id={messages[^1].MsgId}");
        }

        // ── 5. Query without affecting offset ────────────────────────────
        var results = await client.QueryAsync(address, key: "status");
        Console.WriteLine($"\n[query] key=status → {results.Count} message(s)");
        foreach (var msg in results)
            Console.WriteLine($"  msg_id={msg.MsgId}  payload={Text(msg.Payload)}");

        // ── 6. Consume loop ──────────────────────────────────────────────
        Console.WriteLine("\n[consume] starting loop for 3 s …");

        var consumer = await client.ConsumeAsync(address, async msg =>
        {
            Console.WriteLine($"  [handler] msg_id={msg.MsgId}  payload={Text(msg.Payload)}");
            await Task.CompletedTask;
        }, new ConsumeOptions
        {
            GroupName    = "consume-workers",
            Deliver      = "earliest",
            AutoAck      = true,
            ErrorHandler = async (msg, ex) =>
            {
                Console.Error.WriteLine($"  [error] msg_id={msg.MsgId}  error={ex.Message}");
                await Task.CompletedTask;
            },
        });

        await Task.Delay(3_000);
        await consumer.StopAsync();
        Console.WriteLine($"[consume] stopped. processed={consumer.ProcessedCount}");

        // ── 7. Delete a message ──────────────────────────────────────────
        await client.DeleteAsync(address, mid1);
        Console.WriteLine($"\n[delete] msg_id={mid1} deleted");
    }

    private static byte[] Json(object obj) => JsonSerializer.SerializeToUtf8Bytes(obj);
    private static string Text(byte[] b)   => Encoding.UTF8.GetString(b);
}
