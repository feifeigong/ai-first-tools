using System;
using System.IO;
using System.Text.Json;
using System.Threading;

namespace AIFirst.Workspace;

/// <summary>
/// 定时用卡：到点用掉一张重置卡。
/// 放在页面之外，是为了即使这次开机没打开过「Codex 自动续跑」页面，
/// 只要工具箱在运行，到点也会执行；页面只负责设定时间与显示状态。
/// </summary>
internal static class ScheduledRedeem
{
    private static readonly object gate = new();
    private static Timer? timer;

    internal static string Directory
    {
        get
        {
            var root = Path.GetDirectoryName(ThemeManager.PreferencesPath ?? Path.Combine(AppContext.BaseDirectory, "preferences.json"));
            return string.IsNullOrEmpty(root) ? AppContext.BaseDirectory : root;
        }
    }

    internal static string FilePath => Path.Combine(Directory, "scheduled-redeem.json");

    internal static DateTimeOffset Now() => DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8));

    internal static DateTimeOffset? Read()
    {
        try
        {
            if (!File.Exists(FilePath)) return null;
            using var document = JsonDocument.Parse(File.ReadAllText(FilePath));
            if (document.RootElement.TryGetProperty("at", out var value) && DateTimeOffset.TryParse(value.GetString(), out var parsed)) return parsed;
        }
        catch (Exception exception) when (exception is IOException or JsonException or UnauthorizedAccessException) { App.Log(exception); }
        return null;
    }

    internal static void Write(DateTimeOffset? when)
    {
        try
        {
            if (when is null) { if (File.Exists(FilePath)) File.Delete(FilePath); return; }
            System.IO.Directory.CreateDirectory(Directory);
            File.WriteAllText(FilePath, JsonSerializer.Serialize(new { at = when.Value.ToString("O") }));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
    }

    internal static void Start()
    {
        timer ??= new Timer(_ => Check(), null, TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(30));
    }

    /// <summary>到点就执行一次；页面计时器与后台计时器都可以调用，靠删除文件认领，不会重复用卡。</summary>
    internal static string Check()
    {
        var due = Read();
        if (due is null || Now() < due) return "";
        lock (gate)
        {
            // 另一个计时器可能刚刚执行过：先确认文件还在，再删除以认领这一次执行。
            var current = Read();
            if (current is null || Now() < current) return "";
            var when = current.Value;
            Write(null);
            if (Now() - when > TimeSpan.FromMinutes(30)) return "已错过设定时间超过 30 分钟，这次没有执行用卡，请重新设定。";
            return Run(when);
        }
    }

    private static string Run(DateTimeOffset when)
    {
        try
        {
            var connectionFile = Path.Combine(Directory, "auto-resume-connection.json");
            if (!File.Exists(connectionFile)) return "没有找到续跑程序配置，定时用卡没有执行。";
            using var connection = JsonDocument.Parse(File.ReadAllText(connectionFile));
            var python = connection.RootElement.TryGetProperty("Python", out var pythonValue) ? pythonValue.GetString() : null;
            var runner = connection.RootElement.TryGetProperty("Runner", out var runnerValue) ? runnerValue.GetString() : null;
            if (string.IsNullOrEmpty(python) || string.IsNullOrEmpty(runner)) return "续跑程序配置不完整，定时用卡没有执行。";
            var script = Path.Combine(Path.GetDirectoryName(runner)!, "redeem_now.py");
            if (!File.Exists(script)) return "找不到 redeem_now.py，定时用卡没有执行。";
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(python, "\"" + script + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
            });
            return when.ToString("M月d日 HH:mm") + " 已触发用卡，结果写在 redeem-scheduled.log。";
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or System.ComponentModel.Win32Exception)
        {
            App.Log(exception);
            return "定时用卡没能启动：" + exception.Message;
        }
    }
}
