using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using NATS.Client.Core;

namespace Mq9;

/// <summary>
/// Async mq9 client.  Create with <c>new Mq9Client(server)</c> then call
/// <see cref="ConnectAsync"/>, or use <c>await using</c> for automatic cleanup.
/// </summary>
public sealed class Mq9Client : IAsyncDisposable
{
    // ── Subject constants ────────────────────────────────────────────────────
    private const string Prefix = "$mq9.AI";

    private static string SubMailboxCreate()                        => $"{Prefix}.MAILBOX.CREATE";
    private static string SubMsgSend(string addr)                   => $"{Prefix}.MSG.SEND.{addr}";
    private static string SubMsgFetch(string addr)                  => $"{Prefix}.MSG.FETCH.{addr}";
    private static string SubMsgAck(string addr)                    => $"{Prefix}.MSG.ACK.{addr}";
    private static string SubMsgQuery(string addr)                  => $"{Prefix}.MSG.QUERY.{addr}";
    private static string SubMsgDelete(string addr, long msgId)     => $"{Prefix}.MSG.DELETE.{addr}.{msgId}";
    private static string SubAgentRegister()                        => $"{Prefix}.AGENT.REGISTER";
    private static string SubAgentUnregister()                      => $"{Prefix}.AGENT.UNREGISTER";
    private static string SubAgentReport()                          => $"{Prefix}.AGENT.REPORT";
    private static string SubAgentDiscover()                        => $"{Prefix}.AGENT.DISCOVER";

    // ── Fields ───────────────────────────────────────────────────────────────
    private readonly string        _server;
    private readonly ClientOptions _opts;
    private          NatsConnection? _nc;

    // ── Construction ─────────────────────────────────────────────────────────
    public Mq9Client(string server, ClientOptions? options = null)
    {
        _server = server;
        _opts   = options ?? new ClientOptions();
    }

    public async Task ConnectAsync(CancellationToken ct = default)
    {
        var natsOpts = new NatsOpts
        {
            Url              = _server,
            RequestTimeout   = _opts.RequestTimeout,
            MaxReconnectRetry = _opts.ReconnectAttempts,
            ReconnectWaitMin = _opts.ReconnectDelay,
        };
        _nc = new NatsConnection(natsOpts);
        await _nc.ConnectAsync().ConfigureAwait(false);
    }

    public async Task CloseAsync()
    {
        if (_nc is not null)
        {
            await _nc.DisposeAsync().ConfigureAwait(false);
            _nc = null;
        }
    }

    public async ValueTask DisposeAsync() => await CloseAsync().ConfigureAwait(false);

    // ── Internal helpers ─────────────────────────────────────────────────────
    private NatsConnection Conn => _nc ?? throw new Mq9Error("not connected");

    /// <summary>
    /// Send a JSON-serialisable request and return the parsed reply object.
    /// Throws <see cref="Mq9Error"/> if the broker returns a non-empty "error" field.
    /// </summary>
    private async Task<JsonObject> RequestAsync(
        string subject, object payload, CancellationToken ct = default)
    {
        var data  = JsonSerializer.SerializeToUtf8Bytes(payload);
        var reply = await Conn.RequestAsync<byte[], byte[]>(subject, data, cancellationToken: ct)
                              .ConfigureAwait(false);

        var node = JsonNode.Parse(reply.Data ?? [])
                   ?? throw new Mq9Error("empty response");

        var err = node["error"]?.GetValue<string>();
        if (!string.IsNullOrEmpty(err))
            throw new Mq9Error(err);

        return (JsonObject)node;
    }

    /// <summary>
    /// Send a raw-bytes request (with optional NATS headers) and return the parsed reply.
    /// </summary>
    private async Task<JsonObject> RequestRawAsync(
        string subject, byte[] payload,
        NatsHeaders? headers = null,
        CancellationToken ct = default)
    {
        var msg   = new NatsMsg<byte[]>(subject, Data: payload, Headers: headers);
        var reply = await Conn.RequestAsync<byte[], byte[]>(
                        subject, payload, headers: headers, cancellationToken: ct)
                              .ConfigureAwait(false);

        var node = JsonNode.Parse(reply.Data ?? [])
                   ?? throw new Mq9Error("empty response");

        var err = node["error"]?.GetValue<string>();
        if (!string.IsNullOrEmpty(err))
            throw new Mq9Error(err);

        return (JsonObject)node;
    }

    private static List<Mq9Message> ParseMessages(JsonNode? node)
    {
        var result = new List<Mq9Message>();
        if (node is not JsonArray arr) return result;

        foreach (var item in arr)
        {
            if (item is null) continue;
            var rawPayload = item["payload"]?.GetValue<string>() ?? "";
            byte[] payload;
            try   { payload = Convert.FromBase64String(rawPayload); }
            catch { payload = Encoding.UTF8.GetBytes(rawPayload); }

            result.Add(new Mq9Message
            {
                MsgId      = item["msg_id"]?.GetValue<long>()    ?? 0,
                Payload    = payload,
                Priority   = PriorityExtensions.FromWire(item["priority"]?.GetValue<string>()),
                CreateTime = item["create_time"]?.GetValue<long>() ?? 0,
            });
        }
        return result;
    }

    // ── Mailbox ──────────────────────────────────────────────────────────────

    /// <summary>
    /// Create a mailbox. <paramref name="name"/>=null lets the broker auto-generate an address.
    /// <paramref name="ttl"/>=0 means the mailbox never expires.
    /// Returns the <c>mail_address</c>.
    /// </summary>
    public async Task<string> MailboxCreateAsync(
        string? name = null, long ttl = 0, CancellationToken ct = default)
    {
        var req = new Dictionary<string, object> { ["ttl"] = ttl };
        if (!string.IsNullOrEmpty(name)) req["name"] = name;

        var reply = await RequestAsync(SubMailboxCreate(), req, ct).ConfigureAwait(false);
        return reply["mail_address"]?.GetValue<string>()
               ?? throw new Mq9Error("missing mail_address in response");
    }

    // ── Messaging — Send ─────────────────────────────────────────────────────

    /// <summary>
    /// Send <paramref name="payload"/> to <paramref name="mailAddress"/>.
    /// Returns the broker-assigned <c>msg_id</c> (-1 for delayed messages).
    /// </summary>
    public async Task<long> SendAsync(
        string mailAddress, byte[] payload,
        SendOptions? options = null, CancellationToken ct = default)
    {
        options ??= new SendOptions();

        var headers = new NatsHeaders();
        if (options.Priority != Priority.Normal)
            headers["mq9-priority"] = options.Priority.ToWire();
        if (!string.IsNullOrEmpty(options.Key))
            headers["mq9-key"] = options.Key;
        if (options.Delay is long delay and > 0)
            headers["mq9-delay"] = delay.ToString();
        if (options.Ttl is long ttl and > 0)
            headers["mq9-ttl"] = ttl.ToString();
        if (options.Tags is { Length: > 0 } tags)
            headers["mq9-tags"] = string.Join(",", tags);

        var reply = await RequestRawAsync(SubMsgSend(mailAddress), payload, headers, ct)
                          .ConfigureAwait(false);
        return reply["msg_id"]?.GetValue<long>() ?? -1;
    }

    // ── Messaging — Fetch ────────────────────────────────────────────────────

    public async Task<List<Mq9Message>> FetchAsync(
        string mailAddress, FetchOptions? options = null, CancellationToken ct = default)
    {
        options ??= new FetchOptions();

        var req = new Dictionary<string, object>
        {
            ["group_name"]    = options.GroupName ?? (object)JsonSerializer.Deserialize<object>("null")!,
            ["deliver"]       = options.Deliver,
            ["force_deliver"] = options.ForceDeliver,
            ["config"]        = new { num_msgs = options.NumMsgs, max_wait_ms = options.MaxWaitMs },
        };
        if (options.FromTime.HasValue) req["from_time"] = options.FromTime.Value;
        if (options.FromId.HasValue)   req["from_id"]   = options.FromId.Value;

        var reply = await RequestAsync(SubMsgFetch(mailAddress), req, ct).ConfigureAwait(false);
        return ParseMessages(reply["messages"]);
    }

    // ── Messaging — Ack ──────────────────────────────────────────────────────

    public async Task AckAsync(
        string mailAddress, string groupName, long msgId, CancellationToken ct = default)
    {
        var req = new
        {
            group_name   = groupName,
            mail_address = mailAddress,
            msg_id       = msgId,
        };
        await RequestAsync(SubMsgAck(mailAddress), req, ct).ConfigureAwait(false);
    }

    // ── Messaging — Consume ──────────────────────────────────────────────────

    /// <summary>
    /// Start a background consume loop. Returns immediately; call
    /// <see cref="Consumer.StopAsync"/> to drain and exit.
    /// </summary>
    public Task<Consumer> ConsumeAsync(
        string mailAddress,
        Func<Mq9Message, Task> handler,
        ConsumeOptions? options = null,
        CancellationToken ct = default)
    {
        options ??= new ConsumeOptions();

        // Use a TaskCompletionSource so the Consumer exists before the loop starts.
        var consumerTcs = new TaskCompletionSource<Consumer>(
            TaskCreationOptions.RunContinuationsAsynchronously);

        var loopTask = Task.Run(async () =>
        {
            // Wait for consumer to be set (completes synchronously after Task.Run returns).
            var consumer = await consumerTcs.Task.ConfigureAwait(false);

            var fetchOpts = new FetchOptions
            {
                GroupName = options.GroupName,
                Deliver   = options.Deliver,
                NumMsgs   = options.NumMsgs,
                MaxWaitMs = options.MaxWaitMs,
            };

            while (!consumer.Token.IsCancellationRequested)
            {
                List<Mq9Message> msgs;
                try
                {
                    msgs = await FetchAsync(mailAddress, fetchOpts, consumer.Token)
                                 .ConfigureAwait(false);
                }
                catch (OperationCanceledException) { return; }
                catch
                {
                    try { await Task.Delay(1000, consumer.Token).ConfigureAwait(false); }
                    catch (OperationCanceledException) { return; }
                    continue;
                }

                foreach (var msg in msgs)
                {
                    if (consumer.Token.IsCancellationRequested) return;
                    try
                    {
                        await handler(msg).ConfigureAwait(false);
                        consumer.IncrementCount();
                        if (options.AutoAck)
                            await AckAsync(mailAddress, options.GroupName ?? "", msg.MsgId,
                                           consumer.Token).ConfigureAwait(false);
                    }
                    catch (Exception handlerEx)
                    {
                        if (options.ErrorHandler is not null)
                            await options.ErrorHandler(msg, handlerEx).ConfigureAwait(false);
                    }
                }
            }
        }, ct);

        var consumer = new Consumer(loopTask);
        consumerTcs.SetResult(consumer);
        return Task.FromResult(consumer);
    }

    // ── Messaging — Query ────────────────────────────────────────────────────

    public async Task<List<Mq9Message>> QueryAsync(
        string mailAddress,
        string? key = null, long? limit = null, long? since = null,
        CancellationToken ct = default)
    {
        var req = new Dictionary<string, object>();
        if (!string.IsNullOrEmpty(key))  req["key"]   = key;
        if (limit.HasValue)              req["limit"]  = limit.Value;
        if (since.HasValue)              req["since"]  = since.Value;

        var reply = await RequestAsync(SubMsgQuery(mailAddress), req, ct).ConfigureAwait(false);
        return ParseMessages(reply["messages"]);
    }

    // ── Messaging — Delete ───────────────────────────────────────────────────

    public async Task DeleteAsync(string mailAddress, long msgId, CancellationToken ct = default)
    {
        await RequestRawAsync(SubMsgDelete(mailAddress, msgId), [], ct: ct).ConfigureAwait(false);
    }

    // ── Agent registry ───────────────────────────────────────────────────────

    /// <summary>
    /// Register an agent. <paramref name="agentCard"/> must contain a "mailbox" key.
    /// </summary>
    public async Task AgentRegisterAsync(
        Dictionary<string, object> agentCard, CancellationToken ct = default)
    {
        await RequestAsync(SubAgentRegister(), agentCard, ct).ConfigureAwait(false);
    }

    public async Task AgentUnregisterAsync(string mailbox, CancellationToken ct = default)
    {
        await RequestAsync(SubAgentUnregister(), new { mailbox }, ct).ConfigureAwait(false);
    }

    public async Task AgentReportAsync(
        Dictionary<string, object> report, CancellationToken ct = default)
    {
        await RequestAsync(SubAgentReport(), report, ct).ConfigureAwait(false);
    }

    public async Task<List<Dictionary<string, object>>> AgentDiscoverAsync(
        string? text = null, string? semantic = null,
        int limit = 20, int page = 1,
        CancellationToken ct = default)
    {
        var req = new Dictionary<string, object>
        {
            ["limit"] = limit,
            ["page"]  = page,
        };
        if (!string.IsNullOrEmpty(text))     req["text"]     = text;
        if (!string.IsNullOrEmpty(semantic)) req["semantic"] = semantic;

        var reply = await RequestAsync(SubAgentDiscover(), req, ct).ConfigureAwait(false);

        var agents = new List<Dictionary<string, object>>();
        if (reply["agents"] is not JsonArray arr) return agents;

        foreach (var item in arr)
        {
            if (item is JsonObject obj)
                agents.Add(obj.ToDictionary(
                    kv => kv.Key,
                    kv => (object)(kv.Value?.ToString() ?? "")));
        }
        return agents;
    }
}
