using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Interop;

namespace AIFirst.Workspace;

internal static class NativeSelfTests
{
    internal static async Task<int> Run(string fixture, string report)
    {
        var results = new List<object>();
        var failures = 0;
        ToolSession? first = null;
        ToolSession? second = null;
        ToolSession? busy = null;
        ToolSession? prepared = null;
        var busyFlag = Path.Combine(Path.GetDirectoryName(fixture)!, "busy-fixture.flag");
        var ownsFlag = false;
        using var parent = new HwndSource(new HwndSourceParameters("AI First isolated native test") { Width = 1000, Height = 700, WindowStyle = 0x00CF0000 });
        var container = NativeMethods.CreateWindowEx(0, "static", "Isolated test container", NativeMethods.Child | 0x10000000, 0, 0, 900, 600, parent.Handle, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        void Require(bool condition) { if (!condition) throw new InvalidOperationException("Assertion failed"); }
        void Check(string name, Action test)
        {
            try { test(); results.Add(new { name, passed = true, error = "" }); }
            catch (Exception exception) { failures++; results.Add(new { name, passed = false, error = exception.ToString() }); }
        }
        async Task CheckAsync(string name, Func<Task> test)
        {
            try { await test(); results.Add(new { name, passed = true, error = "" }); }
            catch (Exception exception) { failures++; results.Add(new { name, passed = false, error = exception.ToString() }); }
        }
        try
        {
            Require(container != IntPtr.Zero);
            first = new ToolSession(new ToolDefinition { Name = "Isolated fixture one", Executable = fixture });
            await first.FindWindowAsync(CancellationToken.None);
            var originalStyle = NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.Style);
            var originalExtendedStyle = NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.ExtendedStyle);
            NativeMethods.GetWindowRect(first.Window, out var originalBounds);
            var firstWindow = first.Window;
            Check("Attach uses the launched process window", () => { first.Attach(container); Require(first.Attached && NativeMethods.GetParent(first.Window) == container); });
            Check("Embedded window loses its independent caption", () => { var style = NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.Style).ToInt64(); Require((style & NativeMethods.Child) != 0 && (style & NativeMethods.Caption) == 0); });
            Check("Embedded tool has no independent taskbar entry", () => { var style = NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.ExtendedStyle).ToInt64(); Require((style & NativeMethods.AppWindow) == 0 && (style & NativeMethods.ToolWindow) != 0); });
            Check("Resize follows container client bounds", () => { NativeMethods.SetWindowPos(container, IntPtr.Zero, 0, 0, 780, 520, NativeMethods.NoActivate | NativeMethods.NoZOrder); first.Resize(container); NativeMethods.GetWindowRect(first.Window, out var bounds); Require(bounds.Right - bounds.Left == 780 && bounds.Bottom - bounds.Top == 520); });
            second = new ToolSession(new ToolDefinition { Name = "Isolated fixture two", Executable = fixture });
            await second.FindWindowAsync(CancellationToken.None);
            Check("Switch keeps each process and native window", () => { first.SetVisible(false); second.Attach(container); second.SetVisible(false); first.Attach(container); Require(first.Window == firstWindow && !first.Process.HasExited && !second.Process.HasExited); });
            Check("Detach restores independent frame and bounds", () => { first.Detach(); NativeMethods.GetWindowRect(first.Window, out var bounds); Require(!first.Attached && NativeMethods.GetParent(first.Window) == IntPtr.Zero && NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.Style) == originalStyle && bounds.Left == originalBounds.Left && bounds.Top == originalBounds.Top && bounds.Right == originalBounds.Right && bounds.Bottom == originalBounds.Bottom); });
            Check("Detach restores original taskbar styles", () => Require(NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.ExtendedStyle) == originalExtendedStyle));
            Check("Fallback window shares the workspace taskbar entry", () => { first.OpenManagedWindow(parent.Handle); Require(NativeMethods.GetWindow(first.Window, 4) == parent.Handle && (NativeMethods.GetWindowLongPtr(first.Window, NativeMethods.ExtendedStyle).ToInt64() & NativeMethods.ToolWindow) != 0); });
            Check("Reattach uses the original window without relaunch", () => { first.Attach(container); Require(first.Window == firstWindow && NativeMethods.GetParent(first.Window) == container); });
            Check("Workspace release preserves the tool process", () => { first.Dispose(); Require(NativeMethods.IsWindow(firstWindow) && NativeMethods.GetParent(firstWindow) == IntPtr.Zero); first = null; });
            NativeMethods.PostMessage(firstWindow, 0x0010, IntPtr.Zero, IntPtr.Zero);
            for (var attempt = 0; attempt < 25 && NativeMethods.IsWindow(firstWindow); attempt++) await Task.Delay(100);
            Require(!NativeMethods.IsWindow(firstWindow));
            Require(!File.Exists(busyFlag));
            File.WriteAllText(busyFlag, "isolated fixture close veto");
            ownsFlag = true;
            busy = new ToolSession(new ToolDefinition { Name = "Close safety fixture", Executable = fixture });
            await busy.FindWindowAsync(CancellationToken.None);
            busy.Attach(container);
            var pendingClose = busy.TryCloseAsync();
            Check("Layout changes do not resize a tool while its close request is pending", () =>
            {
                NativeMethods.GetWindowRect(busy.Window, out var before);
                NativeMethods.SetWindowPos(container, IntPtr.Zero, 0, 0, 760, 500, NativeMethods.NoActivate | NativeMethods.NoZOrder);
                busy.Resize(container);
                NativeMethods.GetWindowRect(busy.Window, out var after);
                Require(!pendingClose.IsCompleted && before.Right - before.Left == after.Right - after.Left && before.Bottom - before.Top == after.Bottom - after.Top);
            });
            await CheckAsync("Busy tool veto keeps its process and embedded window", async () => { Require(!await pendingClose); Require(!busy.Process.HasExited && busy.Attached && NativeMethods.GetParent(busy.Window) == container); });
            Check("Resize resumes after a busy tool refuses the close request", () =>
            {
                busy.Resize(container);
                NativeMethods.GetWindowRect(busy.Window, out var bounds);
                Require(bounds.Right - bounds.Left == 760 && bounds.Bottom - bounds.Top == 500);
            });
            File.Delete(busyFlag);
            ownsFlag = false;
            await CheckAsync("Idle tool closes normally without detaching or force killing", async () => { Require(await busy.TryCloseAsync()); Require(busy.Process.HasExited || !NativeMethods.IsWindow(busy.Window)); });
            await CheckAsync("Late layout and close callbacks are harmless after session disposal", async () => { busy.Dispose(); busy.Resize(container); Require(await busy.TryCloseAsync()); });
            prepared = new ToolSession(new ToolDefinition { Name = "Hidden startup fixture", Executable = fixture, EmbeddedStartup = true });
            await prepared.FindWindowAsync(CancellationToken.None);
            Check("Cooperative tool is prepared while still hidden, before any attachment", () => Require(prepared.StartupWasHidden == true && !NativeMethods.IsWindowVisible(prepared.Window)));
            Check("Prepared tool has no independent taskbar style", () => Require((NativeMethods.GetWindowLongPtr(prepared.Window, NativeMethods.ExtendedStyle).ToInt64() & NativeMethods.AppWindow) == 0));
            var preparedWindow = prepared.Window;
            Check("Prepared tool is revealed directly as a child without changing its process or window", () =>
            {
                prepared.Attach(container);
                Require(prepared.Attached && prepared.Window == preparedWindow && NativeMethods.GetParent(preparedWindow) == container);
            });
            Check("Revisiting a prepared tool preserves its parent and frame", () =>
            {
                prepared.SetVisible(false);
                prepared.Attach(container);
                var style = NativeMethods.GetWindowLongPtr(preparedWindow, NativeMethods.Style).ToInt64();
                Require(prepared.Window == preparedWindow && (style & NativeMethods.Child) != 0 && (style & NativeMethods.Caption) == 0);
            });
            await CheckAsync("Prepared tool accepts a normal close without force killing", async () => Require(await prepared.TryCloseAsync()));
            prepared.Dispose();
            prepared = new ToolSession(new ToolDefinition { Name = "Interrupted hidden startup fixture", Executable = fixture, EmbeddedStartup = true });
            await prepared.FindWindowAsync(CancellationToken.None);
            var interrupted = prepared.Window;
            prepared.Dispose();
            await CheckAsync("Interrupted preparation restores a usable independent window rather than stranding a hidden tool", async () =>
            {
                for (var attempt = 0; attempt < 30 && !NativeMethods.IsWindowVisible(interrupted); attempt++) await Task.Delay(100);
                Require(NativeMethods.IsWindowVisible(interrupted) && NativeMethods.GetParent(interrupted) == IntPtr.Zero);
                NativeMethods.PostMessage(interrupted, 0x0010, IntPtr.Zero, IntPtr.Zero);
                for (var attempt = 0; attempt < 30 && NativeMethods.IsWindow(interrupted); attempt++) await Task.Delay(100);
                Require(!NativeMethods.IsWindow(interrupted));
            });
        }
        catch (Exception exception)
        {
            failures++;
            results.Add(new { name = "Native test setup", passed = false, error = exception.ToString() });
        }
        finally
        {
            if (ownsFlag) File.Delete(busyFlag);
            foreach (var session in new[] { first, second, busy, prepared })
            {
                if (session is null) continue;
                try { session.RequestClose(); session.Dispose(); }
                catch (Exception exception) { failures++; results.Add(new { name = "Fixture cleanup", passed = false, error = exception.ToString() }); }
            }
            NativeMethods.DestroyWindow(container);
        }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(report))!);
        File.WriteAllText(report, JsonSerializer.Serialize(new { passed = results.Count - failures, failed = failures, tests = results }, new JsonSerializerOptions { WriteIndented = true }));
        return failures == 0 ? 0 : 1;
    }
}
