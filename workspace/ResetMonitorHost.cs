using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;

namespace AIFirst.Workspace;

// This host only observes public announcements. Resuming or spending a card is never a news action.
internal static class ResetMonitorHost
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };
    private sealed record Owner(int Pid, string Executable, string Token);
    private sealed record Stop(string Token, string Executable, string Reason);
    private static string Key(string directory) => "Local\\AI_FIRST_RESET_" + ToolRepository.ConfigurationKey(Path.Combine(directory, "monitor"));
    private static string Program => Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "AI一手工具工作台.exe"));

    internal static bool IsRunning(string directory)
    {
        try { using var mutex = Mutex.OpenExisting(Key(directory)); return true; }
        catch (WaitHandleCannotBeOpenedException) { return false; }
    }

    internal static async Task EnsureStartedAsync(ResetNewsService service)
    {
        if (!service.Snapshot.Enabled || IsRunning(service.DataDirectory)) return;
        using var process = Process.Start(new ProcessStartInfo(Program, "--reset-monitor")
        {
            UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = AppContext.BaseDirectory
        }) ?? throw new IOException("重置提醒暂时没有开启，请稍后重试。");
        for (var attempt = 0; attempt < 40; attempt++)
        {
            if (IsRunning(service.DataDirectory)) return;
            if (process.HasExited) break;
            await Task.Delay(100);
        }
        if (!IsRunning(service.DataDirectory)) throw new IOException("重置提醒暂时没有开启，请稍后重试。");
    }

    internal static async Task<int> RunAsync(ResetNewsService service, IAutoResumeControl control,
        Action<ResetNewsItem, Func<Task<bool>>>? show = null, CancellationToken cancellation = default)
    {
        // All awaits return to the WPF dispatcher, the thread that owns this mutex.
        using var mutex = new Mutex(true, Key(service.DataDirectory), out var created);
        if (!created) return 0;
        var owner = new Owner(Environment.ProcessId, Program, Guid.NewGuid().ToString("N"));
        var ownerPath = Path.Combine(service.DataDirectory, "monitor-owner.json");
        ResetNoticeWindow? notice = null;
        Task? refresh = null;
        try
        {
            service.ReadCached();
            if (!service.Snapshot.Enabled) return 0;
            Directory.CreateDirectory(service.DataDirectory);
            WriteOwner(ownerPath, owner);
            while (!cancellation.IsCancellationRequested && !StopRequested(service.DataDirectory, owner.Token, owner.Executable))
            {
                service.ReadCached();
                if (!service.Snapshot.Enabled) break;
                if (refresh is null || refresh.IsCompleted)
                {
                    if (refresh is not null) await refresh;
                    refresh = service.RefreshAsync(false);
                }
                if (StopRequested(service.DataDirectory, owner.Token, owner.Executable) || cancellation.IsCancellationRequested) break;
                if (notice is null && service.TryTakeAlert(out var item) && item is not null)
                {
                    if (show is not null) show(item, () => PauseAsync(control));
                    else
                    {
                        notice = new ResetNoticeWindow(item, () => PauseAsync(control))
                        { ShowActivated = false, Topmost = true, WindowStartupLocation = WindowStartupLocation.CenterScreen };
                        notice.Closed += (_, _) => notice = null;
                        notice.Show();
                    }
                }
                await Task.Delay(2000, cancellation);
            }
            return 0;
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { return 0; }
        finally
        {
            try
            {
                service.Dispose();
                if (refresh is not null)
                    try { await refresh; } catch (OperationCanceledException) { }
            }
            finally
            {
                try
                {
                    // An explicit stop operation must finish before its notification closes.
                    if (notice is not null)
                    {
                        while (notice.IsBusy) await Task.Delay(100);
                        notice.Close();
                    }
                }
                finally { DeleteOwner(ownerPath, owner.Token); mutex.ReleaseMutex(); }
            }
        }
    }

    internal static async Task<bool> PauseAsync(IAutoResumeControl control)
    {
        var result = await control.ExecuteAsync("stop", CancellationToken.None);
        return !result.Running && !result.Autostart && string.IsNullOrEmpty(result.Error);
    }

    internal static bool StopRequested(string directory, string token, string executable)
    {
        var path = Path.Combine(directory, "monitor-stop.json");
        if (!File.Exists(path)) return false;
        try
        {
            if (new FileInfo(path).Length > 4096) return false;
            var stop = JsonSerializer.Deserialize<Stop>(File.ReadAllText(path), Json);
            return stop is not null && stop.Token == token &&
                string.Equals(stop.Executable, executable, StringComparison.OrdinalIgnoreCase) &&
                stop.Reason is "update" or "uninstall";
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException) { return false; }
    }

    private static void WriteOwner(string path, Owner value)
    {
        var temporary = path + "." + value.Token + ".tmp";
        try { File.WriteAllText(temporary, JsonSerializer.Serialize(value, Json)); File.Move(temporary, path, true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static void DeleteOwner(string path, string token)
    {
        try
        {
            if (File.Exists(path) && JsonSerializer.Deserialize<Owner>(File.ReadAllText(path), Json)?.Token == token) File.Delete(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException) { }
    }
}
