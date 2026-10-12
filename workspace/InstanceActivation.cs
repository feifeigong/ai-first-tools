using System;
using System.IO;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal sealed class InstanceActivation : IDisposable
{
    private readonly string name;
    private readonly CancellationTokenSource lifetime = new();
    private readonly Task listener;
    internal InstanceActivation(string key, Action show) { name = "AI_FIRST_TOOL_WORKSPACE_" + key; listener = ListenAsync(show); }

    private async Task ListenAsync(Action show)
    {
        while (!lifetime.IsCancellationRequested)
        {
            try
            {
                using var server = new NamedPipeServerStream(name, PipeDirection.In, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await server.WaitForConnectionAsync(lifetime.Token);
                using var request = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                request.CancelAfter(TimeSpan.FromSeconds(2));
                var bytes = new byte[4];
                await server.ReadExactlyAsync(bytes, request.Token);
                if (bytes.AsSpan().SequenceEqual("show"u8)) show();
            }
            catch (OperationCanceledException) { }
            catch (IOException exception) { App.Log(exception); await Task.Delay(150); }
        }
    }

    internal static async Task<bool> ShowExistingAsync(string key)
    {
        try
        {
            using var client = new NamedPipeClientStream(".", "AI_FIRST_TOOL_WORKSPACE_" + key, PipeDirection.Out, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            await client.ConnectAsync(timeout.Token);
            await client.WriteAsync("show"u8.ToArray(), timeout.Token);
            return true;
        }
        catch (Exception exception) when (exception is IOException or OperationCanceledException or TimeoutException) { return false; }
    }

    public void Dispose() => lifetime.Cancel();
}
