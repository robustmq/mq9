namespace Mq9;

/// <summary>
/// Thrown when the mq9 broker returns a non-empty error field,
/// or when the client is not connected.
/// </summary>
public sealed class Mq9Error : Exception
{
    public Mq9Error(string message) : base(message) { }
}
