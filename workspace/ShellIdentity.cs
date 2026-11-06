using System;
using System.Runtime.InteropServices;

namespace AIFirst.Workspace;

internal static class ShellIdentity
{
    internal const string AppId = "AI.First.Tools.Toolbox";
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string value);
    [DllImport("shell32.dll")]
    private static extern int GetCurrentProcessExplicitAppUserModelID(out IntPtr value);

    // 开发预览用独立的 AppUserModelID：任务栏会当成新应用，重新从 exe 读取图标，
    // 不会沿用已注销版本留下的旧图标缓存。
    internal static void Initialize() => Marshal.ThrowExceptionForHR(SetCurrentProcessExplicitAppUserModelID(App.IsDevelopmentPreview ? AppId + ".Preview" : AppId));
    internal static string Read()
    {
        Marshal.ThrowExceptionForHR(GetCurrentProcessExplicitAppUserModelID(out var value));
        try { return Marshal.PtrToStringUni(value) ?? ""; }
        finally { Marshal.FreeCoTaskMem(value); }
    }
}
