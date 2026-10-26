using System;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;

namespace AIFirst.Workspace;

internal static class ResetMonitorTests
{
    private sealed class FakeControl : IAutoResumeControl
    {
        internal int Calls;
        internal AutoResumeStatus Result = new(true, false, false, 0);
        public Task<AutoResumeStatus> ExecuteAsync(string action, CancellationToken cancellation)
        {
            if (action != "stop") throw new InvalidOperationException("Unexpected command");
            Calls++;
            return Task.FromResult(Result);
        }
    }

    private sealed class PendingHttp : HttpMessageHandler
    {
        internal int Calls;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellation)
        {
            Calls++;
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellation).ConfigureAwait(false);
            throw new InvalidOperationException();
        }
    }

    internal static void Run(Action<string, Action> check, Action<bool> require)
    {
        check("Reset monitor pauses only after an explicit callback and confirms both switches", () =>
        {
            var fake = new FakeControl { Result = new(true, true, true, 1) };
            require(!ResetMonitorHost.PauseAsync(fake).GetAwaiter().GetResult() && fake.Calls == 1);
            fake.Result = new(true, false, true, 0);
            require(!ResetMonitorHost.PauseAsync(fake).GetAwaiter().GetResult());
            fake.Result = new(true, false, false, 0);
            require(ResetMonitorHost.PauseAsync(fake).GetAwaiter().GetResult() && fake.Calls == 3);
        });
        check("Reset monitor ignores stale or foreign-package stop requests", () =>
        {
            var root = Path.Combine(Path.GetTempPath(), "reset-owner-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            var path = Path.Combine(root, "monitor-stop.json");
            File.WriteAllText(path, JsonSerializer.Serialize(new { token = "owned", executable = "fixture.exe", reason = "update" }));
            require(!ResetMonitorHost.StopRequested(root, "old", "fixture.exe"));
            require(!ResetMonitorHost.StopRequested(root, "owned", "other.exe"));
            require(ResetMonitorHost.StopRequested(root, "owned", "fixture.exe"));
            File.WriteAllText(path, "partial");
            require(!ResetMonitorHost.StopRequested(root, "owned", "fixture.exe"));
        });
        check("Reset monitor exits cooperatively even during a stalled public request, without touching resume", () =>
        {
            var root = Path.Combine(Path.GetTempPath(), "reset-monitor-test-" + Guid.NewGuid().ToString("N"));
            using var handler = new PendingHttp();
            using var http = new HttpClient(handler);
            using var service = new ResetNewsService(root, http, () => DateTimeOffset.UtcNow);
            using var cancellation = new CancellationTokenSource();
            var fake = new FakeControl();
            var alerts = 0;
            var run = ResetMonitorHost.RunAsync(service, fake, (_, _) => alerts++, cancellation.Token);
            require(ResetMonitorHost.IsRunning(root));
            require(File.Exists(Path.Combine(root, "monitor-owner.json")));
            using var second = new ResetNewsService(root, http, () => DateTimeOffset.UtcNow);
            require(ResetMonitorHost.RunAsync(second, fake).GetAwaiter().GetResult() == 0);
            using var owner = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "monitor-owner.json")));
            File.WriteAllText(Path.Combine(root, "monitor-stop.json"), JsonSerializer.Serialize(new
            {
                token = owner.RootElement.GetProperty("token").GetString(),
                executable = owner.RootElement.GetProperty("executable").GetString(), reason = "update"
            }));
            Pump(run);
            require(run.GetAwaiter().GetResult() == 0 && fake.Calls == 0 && alerts == 0 && handler.Calls == 1);
            require(!File.Exists(Path.Combine(root, "monitor-owner.json")) && !ResetMonitorHost.IsRunning(root));
        });
        check("Reset monitor releases its ownership after unreadable local state, and disabled reminders never request news", () =>
        {
            var root = Path.Combine(Path.GetTempPath(), "reset-monitor-failure-" + Guid.NewGuid().ToString("N"));
            using var handler = new PendingHttp();
            using var http = new HttpClient(handler);
            using (var disabled = new ResetNewsService(root, http, () => DateTimeOffset.UtcNow))
            {
                disabled.SetEnabledAsync(false).GetAwaiter().GetResult();
                require(ResetMonitorHost.RunAsync(disabled, new FakeControl()).GetAwaiter().GetResult() == 0);
                require(handler.Calls == 0 && !ResetMonitorHost.IsRunning(root));
            }
            File.WriteAllText(Path.Combine(root, "state.json"), "unreadable fixture");
            using var broken = new ResetNewsService(root, http, () => DateTimeOffset.UtcNow);
            var task = ResetMonitorHost.RunAsync(broken, new FakeControl());
            Pump(task);
            require(task.IsFaulted && !File.Exists(Path.Combine(root, "monitor-owner.json")) && !ResetMonitorHost.IsRunning(root));
            _ = task.Exception;
        });
    }

    private static void Pump(Task task)
    {
        var frame = new DispatcherFrame();
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(10) };
        var deadline = DateTime.UtcNow.AddSeconds(5);
        timer.Tick += (_, _) => { if (task.IsCompleted || DateTime.UtcNow > deadline) frame.Continue = false; };
        timer.Start();
        try { Dispatcher.PushFrame(frame); }
        finally { timer.Stop(); }
        if (!task.IsCompleted) throw new TimeoutException("Synthetic monitor did not stop.");
    }
}
