using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal sealed class ToolSession : IDisposable
{
    internal ToolDefinition Definition { get; }
    internal Process Process { get; }
    internal IntPtr Window { get; private set; }
    internal bool Attached { get; private set; }
    internal bool UseSeparateWindow { get; set; }
    internal bool? StartupWasHidden { get; private set; }
    private readonly string? startupDirectory;
    private long originalStyle;
    private long originalExtendedStyle;
    private IntPtr originalOwner;
    private NativeMethods.Rectangle originalBounds;
    private bool styleSaved;
    private bool needsRestore;
    private readonly CancellationTokenSource lifetime = new();
    private bool disposed;
    private bool closeRequested;

    internal ToolSession(ToolDefinition definition)
    {
        ToolRepository.Validate(definition);
        if (!File.Exists(definition.Executable)) throw new FileNotFoundException("找不到这个工具的 EXE。请保留完整程序目录，或重新解压工具包。", definition.Executable);
        Definition = definition;
        var start = new ProcessStartInfo
        {
            FileName = definition.Executable,
            WorkingDirectory = Path.GetDirectoryName(definition.Executable)!,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Normal
        };
        start.Environment.Remove("AI_FIRST_WORKSPACE_READY_FILE");
        start.Environment.Remove("AI_FIRST_WORKSPACE_HOST_PID");
        if (definition.EmbeddedStartup)
        {
            startupDirectory = Path.Combine(Path.GetTempPath(), "ai-first-startup-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(startupDirectory);
            start.Environment["AI_FIRST_WORKSPACE_READY_FILE"] = Path.Combine(startupDirectory, "window.json");
            start.Environment["AI_FIRST_WORKSPACE_HOST_PID"] = Environment.ProcessId.ToString();
        }
        try { Process = Process.Start(start) ?? throw new InvalidOperationException("工具没有成功启动。"); }
        catch { CleanStartup(); throw; }
    }

    internal async Task FindWindowAsync(CancellationToken cancellation)
    {
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellation, lifetime.Token);
        cancellation = linked.Token;
        var deadline = DateTime.UtcNow.AddSeconds(35);
        var candidate = IntPtr.Zero;
        var observations = 0;
        while (DateTime.UtcNow < deadline)
        {
            cancellation.ThrowIfCancellationRequested();
            if (Process.HasExited) throw new InvalidOperationException("工具没有打开新窗口。它可能已经开着，请先查看它现有的窗口。");
            var current = startupDirectory is null ? NativeMethods.FindMainWindow(Process.Id) : ReadPreparedWindow();
            observations = current != IntPtr.Zero && current == candidate ? observations + 1 : 0;
            candidate = current;
            if (current != IntPtr.Zero && (startupDirectory is not null || observations >= 2))
            {
                Window = current;
                StartupWasHidden = startupDirectory is null ? null : !NativeMethods.IsWindowVisible(current);
                return;
            }
            await Task.Delay(startupDirectory is null ? 200 : 50, cancellation);
        }
        throw new TimeoutException("工具打开得比较慢，请点“再试一次”。");
    }

    private IntPtr ReadPreparedWindow()
    {
        var file = Path.Combine(startupDirectory!, "window.json");
        if (!File.Exists(file)) return IntPtr.Zero;
        JsonDocument document;
        try { document = JsonDocument.Parse(File.ReadAllText(file)); }
        catch (JsonException exception) { throw new InvalidDataException("工具准备信息无效，已停止接入。", exception); }
        using var prepared = document;
        var root = document.RootElement;
        if (!root.TryGetProperty("processId", out var process) || !process.TryGetInt32(out var expected) || expected != Process.Id || !root.TryGetProperty("window", out var handle) || !handle.TryGetInt64(out var value))
            throw new InvalidDataException("工具准备信息无效，已停止接入。");
        var window = new IntPtr(value);
        NativeMethods.GetWindowThreadProcessId(window, out var actual);
        if (!NativeMethods.IsWindow(window) || actual != Process.Id) throw new InvalidDataException("准备好的窗口不属于这个工具，已停止接入。");
        return window;
    }

    private void CleanStartup()
    {
        if (startupDirectory is null) return;
        try
        {
            foreach (var name in new[] { "window.json", "window.tmp" }) File.Delete(Path.Combine(startupDirectory, name));
            if (Directory.Exists(startupDirectory)) Directory.Delete(startupDirectory);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
    }

    internal void Attach(IntPtr parent)
    {
        if (!NativeMethods.IsWindow(Window)) throw new InvalidOperationException("工具窗口已经关闭，请重新打开。");
        NativeMethods.GetWindowThreadProcessId(Window, out var processId);
        if (processId != Process.Id) throw new InvalidOperationException("工具窗口与启动的进程不一致，已停止接入。");
        if (!NativeMethods.AreDpiAwarenessContextsEqual(NativeMethods.GetWindowDpiAwarenessContext(Window), NativeMethods.GetWindowDpiAwarenessContext(parent)))
            throw new InvalidOperationException("这款工具和工具箱的显示缩放模式不同。为避免错位，请先独立打开。");
        if (Attached && NativeMethods.GetParent(Window) == parent)
        {
            Resize(parent);
            SetVisible(true);
            return;
        }
        SaveWindowState();
        try
        {
            needsRestore = true;
            NativeMethods.ShowWindow(Window, 0);
            NativeMethods.SetStyle(Window, NativeMethods.Style, (originalStyle & ~(NativeMethods.Popup | NativeMethods.Caption | NativeMethods.ThickFrame)) | NativeMethods.Child | NativeMethods.ClipChildren | NativeMethods.ClipSiblings);
            NativeMethods.SetStyle(Window, NativeMethods.ExtendedStyle, (originalExtendedStyle & ~(NativeMethods.AppWindow | (Definition.EmbeddedStartup ? 0x08000000 : 0))) | NativeMethods.ToolWindow);
            NativeMethods.ParentWindow(Window, parent);
            Attached = true;
            Resize(parent);
            NativeMethods.ShowWindow(Window, 5);
            ShellTaskbar.RemoveToolButton(Window);
        }
        catch
        {
            Detach();
            throw;
        }
    }

    private void SaveWindowState()
    {
        if (styleSaved) return;
        originalStyle = NativeMethods.GetWindowLongPtr(Window, NativeMethods.Style).ToInt64();
        originalExtendedStyle = NativeMethods.GetWindowLongPtr(Window, NativeMethods.ExtendedStyle).ToInt64();
        if (Definition.EmbeddedStartup) originalExtendedStyle &= ~0x08000000;
        originalOwner = NativeMethods.GetWindow(Window, 4);
        NativeMethods.GetWindowRect(Window, out originalBounds);
        styleSaved = true;
    }

    internal void ManageTaskbar(IntPtr owner)
    {
        if (!NativeMethods.IsWindow(Window)) return;
        NativeMethods.GetWindowThreadProcessId(Window, out var processId);
        if (processId != Process.Id) throw new InvalidOperationException("不是工具箱启动的工具窗口。");
        SaveWindowState();
        needsRestore = true;
        var visible = NativeMethods.IsWindowVisible(Window);
        NativeMethods.ShowWindow(Window, 0);
        NativeMethods.SetStyle(Window, NativeMethods.ExtendedStyle, (originalExtendedStyle & ~NativeMethods.AppWindow) | NativeMethods.ToolWindow);
        if (!Attached && NativeMethods.GetWindow(Window, 4) != owner) NativeMethods.SetStyle(Window, NativeMethods.Owner, owner.ToInt64());
        NativeMethods.SetWindowPos(Window, IntPtr.Zero, 0, 0, 0, 0, NativeMethods.NoActivate | NativeMethods.NoZOrder | NativeMethods.FrameChanged | 0x0001 | 0x0002);
        if (visible) NativeMethods.ShowWindow(Window, 5);
        ShellTaskbar.RemoveToolButton(Window);
    }

    internal void Resize(IntPtr parent)
    {
        if (disposed || closeRequested || !Attached || !NativeMethods.IsWindow(Window)) return;
        NativeMethods.GetClientRect(parent, out var bounds);
        if (!NativeMethods.SetWindowPos(Window, IntPtr.Zero, 0, 0, Math.Max(1, bounds.Right), Math.Max(1, bounds.Bottom), NativeMethods.NoActivate | NativeMethods.NoZOrder | NativeMethods.FrameChanged))
        {
            var error = System.Runtime.InteropServices.Marshal.GetLastPInvokeError();
            if (disposed || !NativeMethods.IsWindow(Window) || Process.HasExited) return;
            throw new Win32Exception(error);
        }
    }

    internal void SetVisible(bool visible)
    {
        if (Attached && NativeMethods.IsWindow(Window)) NativeMethods.ShowWindow(Window, visible ? 5 : 0);
    }

    internal void Detach()
    {
        if (!NativeMethods.IsWindow(Window)) { Attached = false; needsRestore = false; return; }
        try
        {
            if (styleSaved && needsRestore)
            {
                NativeMethods.ShowWindow(Window, 0);
                NativeMethods.ParentWindow(Window, IntPtr.Zero);
                NativeMethods.SetStyle(Window, NativeMethods.Style, originalStyle);
                NativeMethods.SetStyle(Window, NativeMethods.ExtendedStyle, originalExtendedStyle);
                if (NativeMethods.GetWindow(Window, 4) != originalOwner) NativeMethods.SetStyle(Window, NativeMethods.Owner, originalOwner.ToInt64());
                NativeMethods.SetWindowPos(Window, IntPtr.Zero, originalBounds.Left, originalBounds.Top, Math.Max(400, originalBounds.Right - originalBounds.Left), Math.Max(300, originalBounds.Bottom - originalBounds.Top), NativeMethods.NoActivate | NativeMethods.NoZOrder | NativeMethods.FrameChanged);
            }
            NativeMethods.ShowWindow(Window, 5);
        }
        catch (Win32Exception exception) when (exception.NativeErrorCode == 1400 && !NativeMethods.IsWindow(Window)) { }
        finally { Attached = false; needsRestore = false; }
    }

    internal void OpenManagedWindow(IntPtr owner)
    {
        if (Attached) Detach();
        ManageTaskbar(owner);
        if (NativeMethods.IsWindow(Window)) { NativeMethods.ShowWindow(Window, 9); NativeMethods.SetForegroundWindow(Window); }
    }

    internal void RequestClose()
    {
        if (Window == IntPtr.Zero && Definition.EmbeddedStartup && !Process.HasExited) Window = NativeMethods.FindMainWindow(Process.Id, true);
        if (NativeMethods.IsWindow(Window)) NativeMethods.PostMessage(Window, 0x0010, IntPtr.Zero, IntPtr.Zero);
    }

    internal async Task<bool> TryCloseAsync()
    {
        if (disposed) return true;
        closeRequested = true;
        try
        {
            RequestClose();
            for (var attempt = 0; attempt < 80; attempt++)
            {
                if (disposed || Process.HasExited || Window != IntPtr.Zero && !NativeMethods.IsWindow(Window)) return true;
                await Task.Delay(100);
            }
            return false;
        }
        finally { closeRequested = false; }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        lifetime.Cancel();
        try
        {
            if (Window == IntPtr.Zero && Definition.EmbeddedStartup && !Process.HasExited) Window = NativeMethods.FindMainWindow(Process.Id, true);
            Detach();
        }
        finally { CleanStartup(); Process.Dispose(); lifetime.Dispose(); }
    }
}
