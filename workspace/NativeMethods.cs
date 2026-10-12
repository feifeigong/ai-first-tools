using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace AIFirst.Workspace;

internal static class NativeMethods
{
    internal const int Style = -16;
    internal const int ExtendedStyle = -20;
    internal const int Owner = -8;
    internal const long Child = 0x40000000;
    internal const long Popup = 0x80000000;
    internal const long Caption = 0x00C00000;
    internal const long ThickFrame = 0x00040000;
    internal const long AppWindow = 0x00040000;
    internal const long ToolWindow = 0x00000080;
    internal const long ClipChildren = 0x02000000;
    internal const long ClipSiblings = 0x04000000;
    internal const uint FrameChanged = 0x0020;
    internal const uint NoActivate = 0x0010;
    internal const uint NoZOrder = 0x0004;
    internal delegate bool WindowVisitor(IntPtr window, IntPtr parameter);

    [StructLayout(LayoutKind.Sequential)] internal struct Rectangle { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] internal struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] internal struct MinMaxInfo { public Point Reserved, MaxSize, MaxPosition, MinTrackSize, MaxTrackSize; }
    [StructLayout(LayoutKind.Sequential)] internal struct MonitorInfo { public int Size; public Rectangle Monitor, WorkArea; public uint Flags; }
    [DllImport("user32.dll")] internal static extern IntPtr MonitorFromWindow(IntPtr window, uint flags);
    [DllImport("user32.dll", EntryPoint = "GetMonitorInfoW")] internal static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo information);
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)] internal static extern IntPtr CreateWindowEx(int extendedStyle, string className, string name, long style, int left, int top, int width, int height, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr parameter);
    [DllImport("user32.dll", SetLastError = true)] internal static extern bool DestroyWindow(IntPtr window);
    [DllImport("user32.dll", SetLastError = true)] internal static extern IntPtr SetParent(IntPtr window, IntPtr parent);
    [DllImport("user32.dll")] internal static extern IntPtr GetParent(IntPtr window);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr window, int index);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)] internal static extern IntPtr SetWindowLongPtr(IntPtr window, int index, IntPtr value);
    [DllImport("user32.dll", SetLastError = true)] internal static extern bool SetWindowPos(IntPtr window, IntPtr after, int left, int top, int width, int height, uint flags);
    [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr window);
    [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] internal static extern bool GetClientRect(IntPtr window, out Rectangle rectangle);
    [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr window, out Rectangle rectangle);
    [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")] internal static extern bool EnumWindows(WindowVisitor visitor, IntPtr parameter);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] internal static extern int GetClassName(IntPtr window, StringBuilder value, int length);
    [DllImport("user32.dll")] internal static extern IntPtr GetWindow(IntPtr window, uint command);
    [DllImport("user32.dll")] internal static extern IntPtr SetFocus(IntPtr window);
    [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", SetLastError = true)] internal static extern bool PostMessage(IntPtr window, uint message, IntPtr first, IntPtr second);
    [DllImport("user32.dll")] internal static extern IntPtr GetWindowDpiAwarenessContext(IntPtr window);
    [DllImport("user32.dll")] internal static extern bool AreDpiAwarenessContextsEqual(IntPtr first, IntPtr second);

    internal static void ApplyWorkArea(ref MinMaxInfo limits, Rectangle monitor, Rectangle workArea)
    {
        limits.MaxPosition = new Point { X = workArea.Left - monitor.Left, Y = workArea.Top - monitor.Top };
        limits.MaxSize = new Point { X = workArea.Right - workArea.Left, Y = workArea.Bottom - workArea.Top };
    }

    internal static void SetStyle(IntPtr window, int index, long value)
    {
        Marshal.SetLastPInvokeError(0);
        var previous = SetWindowLongPtr(window, index, new IntPtr(value));
        var error = Marshal.GetLastPInvokeError();
        if (previous == IntPtr.Zero && error != 0) throw new Win32Exception(error);
    }

    internal static void ParentWindow(IntPtr window, IntPtr parent)
    {
        Marshal.SetLastPInvokeError(0);
        var previous = SetParent(window, parent);
        var error = Marshal.GetLastPInvokeError();
        if (previous == IntPtr.Zero && error != 0) throw new Win32Exception(error);
    }

    internal static IntPtr FindMainWindow(int processId, bool includeHidden = false)
    {
        var result = IntPtr.Zero;
        EnumWindows((window, _) =>
        {
            GetWindowThreadProcessId(window, out var owner);
            if (owner != processId || GetWindow(window, 4) != IntPtr.Zero || (!includeHidden && !IsWindowVisible(window))) return true;
            var style = GetWindowLongPtr(window, Style).ToInt64();
            if ((style & Caption) == 0 || (style & Child) != 0) return true;
            var className = new StringBuilder(256);
            GetClassName(window, className, className.Capacity);
            if (className.ToString() == "ConsoleWindowClass") return true;
            result = window;
            return false;
        }, IntPtr.Zero);
        return result;
    }
}
