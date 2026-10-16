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
        if (Present(directory)) await AutoResumeControl.ExecuteAtAsync(directory, "finish-update", CancellationToken.None);
    }
}
