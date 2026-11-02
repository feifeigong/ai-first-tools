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

    internal static void Initialize() => Marshal.ThrowExceptionForHR(SetCurrentProcessExplicitAppUserModelID(AppId));
    internal static string Read()
    {
        Marshal.ThrowExceptionForHR(GetCurrentProcessExplicitAppUserModelID(out var value));
        try { return Marshal.PtrToStringUni(value) ?? ""; }
        finally { Marshal.FreeCoTaskMem(value); }
    }
}
