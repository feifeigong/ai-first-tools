using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal sealed record AutoResumeStatus(bool Installed, bool Running, bool Autostart, int WatcherCount, string Error = "");

internal interface IAutoResumeControl
{
    Task<AutoResumeStatus> ExecuteAsync(string action, CancellationToken cancellation);
}

internal sealed class AutoResumeControl : IAutoResumeControl
{
    public async Task<AutoResumeStatus> ExecuteAsync(string action, CancellationToken cancellation)
    {
        if (action is not ("status" or "start" or "stop" or "autostart-on" or "autostart-off")) throw new ArgumentException("未知操作。");
        var start = new ProcessStartInfo
        {
            FileName = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe"),
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };
        foreach (var argument in new[] { "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", Path.Combine(AppContext.BaseDirectory, "assets", "auto-resume-control.ps1"), "-Action", action }) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new IOException("暂时无法连接自动续跑程序。");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(40));
        var output = process.StandardOutput.ReadToEndAsync();
        var error = process.StandardError.ReadToEndAsync();
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(); } catch (InvalidOperationException) { }
            if (cancellation.IsCancellationRequested) throw;
            throw new TimeoutException("连接超时，请稍后刷新确认运行状态。");
        }
        var text = await output;
        await error; // Drain the pipe; raw process details never enter the UI or logs.
        AutoResumeStatus? status;
        try { status = JsonSerializer.Deserialize<AutoResumeStatus>(text.Trim(), new JsonSerializerOptions { PropertyNameCaseInsensitive = true }); }
        catch (JsonException) { throw new IOException("暂时无法读取运行状态，请稍后刷新。"); }
        if (status is null) throw new IOException("没有收到运行状态，请稍后刷新。");
        if (process.ExitCode != 0 || status.Error.Length > 0) throw new IOException(status.Error.Length > 0 ? status.Error : "操作没有完成，请刷新后重试。");
        return status;
    }
}
