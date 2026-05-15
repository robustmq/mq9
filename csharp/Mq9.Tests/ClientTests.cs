using System.Text;
using System.Text.Json;
using Mq9;
using Xunit;

namespace Mq9.Tests;

/// <summary>
/// Unit tests for helpers and types that do not require a live broker.
/// Integration tests require a running mq9 broker at nats://localhost:4222.
/// </summary>
public class PriorityTests
{
    [Theory]
    [InlineData(Priority.Normal,   "normal")]
    [InlineData(Priority.Urgent,   "urgent")]
    [InlineData(Priority.Critical, "critical")]
    public void ToWire_ReturnsCorrectString(Priority p, string expected)
    {
        Assert.Equal(expected, p.ToWire());
    }

    [Theory]
    [InlineData("normal",   Priority.Normal)]
    [InlineData("urgent",   Priority.Urgent)]
    [InlineData("critical", Priority.Critical)]
    [InlineData(null,       Priority.Normal)]
    [InlineData("",         Priority.Normal)]
    [InlineData("unknown",  Priority.Normal)]
    public void FromWire_ReturnsCorrectPriority(string? s, Priority expected)
    {
        Assert.Equal(expected, PriorityExtensions.FromWire(s));
    }
}

public class Mq9ErrorTests
{
    [Fact]
    public void Mq9Error_MessageIsPreserved()
    {
        var err = new Mq9Error("mailbox not found");
        Assert.Equal("mailbox not found", err.Message);
        Assert.IsAssignableFrom<Exception>(err);
    }
}

public class SendOptionsTests
{
    [Fact]
    public void SendOptions_Defaults()
    {
        var opts = new SendOptions();
        Assert.Equal(Priority.Normal, opts.Priority);
        Assert.Null(opts.Key);
        Assert.Null(opts.Delay);
        Assert.Null(opts.Ttl);
        Assert.Null(opts.Tags);
    }
}

public class FetchOptionsTests
{
    [Fact]
    public void FetchOptions_Defaults()
    {
        var opts = new FetchOptions();
        Assert.Null(opts.GroupName);
        Assert.Equal("latest", opts.Deliver);
        Assert.Equal(100, opts.NumMsgs);
        Assert.Equal(500, opts.MaxWaitMs);
    }
}

public class ConsumeOptionsTests
{
    [Fact]
    public void ConsumeOptions_AutoAckDefaultTrue()
    {
        var opts = new ConsumeOptions();
        Assert.True(opts.AutoAck);
    }
}

public class Mq9MessageTests
{
    [Fact]
    public void Mq9Message_PayloadRoundtrip()
    {
        var payload = Encoding.UTF8.GetBytes("hello mq9");
        var msg = new Mq9Message
        {
            MsgId      = 42,
            Payload    = payload,
            Priority   = Priority.Urgent,
            CreateTime = 1_700_000_000,
        };

        Assert.Equal(42, msg.MsgId);
        Assert.Equal("hello mq9", Encoding.UTF8.GetString(msg.Payload));
        Assert.Equal(Priority.Urgent, msg.Priority);
        Assert.Equal(1_700_000_000, msg.CreateTime);
    }
}

public class ClientOptionsTests
{
    [Fact]
    public void ClientOptions_Defaults()
    {
        var opts = new ClientOptions();
        Assert.Equal(TimeSpan.FromSeconds(5), opts.RequestTimeout);
        Assert.Equal(5, opts.ReconnectAttempts);
        Assert.Equal(TimeSpan.FromSeconds(2), opts.ReconnectDelay);
    }
}

public class NotConnectedTests
{
    [Fact]
    public async Task MailboxCreate_ThrowsMq9Error_WhenNotConnected()
    {
        var client = new Mq9Client("nats://localhost:4222");
        // ConnectAsync not called — should throw Mq9Error("not connected")
        var ex = await Assert.ThrowsAsync<Mq9Error>(() =>
            client.MailboxCreateAsync(name: "test", ttl: 60));
        Assert.Equal("not connected", ex.Message);
    }

    [Fact]
    public async Task Send_ThrowsMq9Error_WhenNotConnected()
    {
        var client = new Mq9Client("nats://localhost:4222");
        var ex = await Assert.ThrowsAsync<Mq9Error>(() =>
            client.SendAsync("some.address", "hello"u8.ToArray()));
        Assert.Equal("not connected", ex.Message);
    }
}
