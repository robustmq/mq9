// mq9 C# Demo
//
// Usage:
//   dotnet run --project demo.csproj -- message   (default)
//   dotnet run --project demo.csproj -- agent

var mode = args.FirstOrDefault() ?? "message";

switch (mode.ToLowerInvariant())
{
    case "agent":
        await AgentDemo.RunAsync();
        break;
    default:
        await MessageDemo.RunAsync();
        break;
}
