namespace Mq9;

/// <summary>Delivery priority of an mq9 message.</summary>
public enum Priority
{
    Normal,
    Urgent,
    Critical,
}

internal static class PriorityExtensions
{
    internal static string ToWire(this Priority p) => p switch
    {
        Priority.Urgent   => "urgent",
        Priority.Critical => "critical",
        _                 => "normal",
    };

    internal static Priority FromWire(string? s) => s switch
    {
        "urgent"   => Priority.Urgent,
        "critical" => Priority.Critical,
        _          => Priority.Normal,
    };
}

/// <summary>A message received from an mq9 mailbox.</summary>
public sealed class Mq9Message
{
    public long     MsgId      { get; init; }
    public byte[]   Payload    { get; init; } = [];
    public Priority Priority   { get; init; }
    public long     CreateTime { get; init; } // Unix timestamp (seconds)
}

/// <summary>Options for <see cref="Mq9Client.SendAsync"/>.</summary>
public sealed class SendOptions
{
    public Priority  Priority { get; set; } = Priority.Normal;
    /// <summary>Dedup key — broker keeps only the latest message per key.</summary>
    public string?   Key      { get; set; }
    /// <summary>Delay visibility by N seconds.</summary>
    public long?     Delay    { get; set; }
    /// <summary>Per-message TTL in seconds.</summary>
    public long?     Ttl      { get; set; }
    public string[]? Tags     { get; set; }
}

/// <summary>Options for <see cref="Mq9Client.FetchAsync"/>.</summary>
public sealed class FetchOptions
{
    /// <summary>Omit for stateless consumption.</summary>
    public string? GroupName    { get; set; }
    /// <summary>"latest" | "earliest" | "from_time" | "from_id"</summary>
    public string  Deliver      { get; set; } = "latest";
    public long?   FromTime     { get; set; }
    public long?   FromId       { get; set; }
    public bool    ForceDeliver { get; set; }
    public int     NumMsgs      { get; set; } = 100;
    public long    MaxWaitMs    { get; set; } = 500;
}

/// <summary>Options for <see cref="Mq9Client.ConsumeAsync"/>.</summary>
public sealed class ConsumeOptions
{
    public string? GroupName    { get; set; }
    public string  Deliver      { get; set; } = "latest";
    public int     NumMsgs      { get; set; } = 10;
    public long    MaxWaitMs    { get; set; } = 500;
    public bool    AutoAck      { get; set; } = true;
    public Func<Mq9Message, Exception, Task>? ErrorHandler { get; set; }
}

/// <summary>Options for constructing an <see cref="Mq9Client"/>.</summary>
public sealed class ClientOptions
{
    public TimeSpan RequestTimeout    { get; set; } = TimeSpan.FromSeconds(5);
    public int      ReconnectAttempts { get; set; } = 5;
    public TimeSpan ReconnectDelay    { get; set; } = TimeSpan.FromSeconds(2);
}

/// <summary>Handle to a background consume loop started by <see cref="Mq9Client.ConsumeAsync"/>.</summary>
public sealed class Consumer
{
    private readonly CancellationTokenSource _cts = new();
    private readonly Task _task;
    private long _count;

    internal Consumer(Task task) => _task = task;

    internal CancellationToken Token => _cts.Token;

    public bool IsRunning    => !_task.IsCompleted;
    public long ProcessedCount => Interlocked.Read(ref _count);

    internal void IncrementCount() => Interlocked.Increment(ref _count);

    /// <summary>Signal the loop to stop and wait for it to drain the current batch.</summary>
    public async Task StopAsync()
    {
        _cts.Cancel();
        try { await _task.ConfigureAwait(false); }
        catch (OperationCanceledException) { }
    }
}
