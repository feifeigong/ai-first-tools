using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal static class AutoResumeRuntime
{
    internal static bool Present(string directory) => File.Exists(Path.Combine(directory, "tools", "auto-resume", "AI一手续跑后台.exe")) && File.Exists(Path.Combine(directory, "assets", "auto-resume-bundled.ps1"));
    internal static async Task PrepareAsync(string directory)
    {
        if (Present(directory)) await AutoResumeControl.ExecuteAtAsync(directory, "prepare-update", CancellationToken.None);
    }
    internal static async Task RestoreAsync(string directory)
    {
        if (!Present(directory)) return;
        await AutoResumeControl.ExecuteAtAsync(directory, "finish-update", CancellationToken.None);
        // 手动跑安装包时，续跑后台会被安装器停掉，更新收据也在那时用掉了，"finish-update" 就没东西可恢复。
        // 开关还开着就说明用户希望它在跑：这里直接把后台接回来，别让界面写着「已开启」却没有任何进程在等额度。
        try
        {
            var status = await AutoResumeControl.ExecuteAtAsync(directory, "status", CancellationToken.None);
            if (status.Installed && status.ResumeEnabled && !status.Running)
                await AutoResumeControl.ExecuteAtAsync(directory, "start", CancellationToken.None);
        }
        catch (Exception exception) when (exception is IOException or TimeoutException or InvalidOperationException or System.ComponentModel.Win32Exception) { App.Log(exception); }
    }
}
