using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace AIFirst.Workspace;

internal sealed class ToolWindowHost : HwndHost
{
    private IntPtr container;
    internal ToolSession? Session { get; private set; }

    protected override HandleRef BuildWindowCore(HandleRef parent)
    {
        // 不设 WS_VISIBLE，也不写占位文字：没有工具挂上来时这块容器保持隐藏，
        // 否则会露出一块系统灰底和 "AI First tool container" 字样。
        container = NativeMethods.CreateWindowEx(0, "static", "", NativeMethods.Child | NativeMethods.ClipChildren | NativeMethods.ClipSiblings, 0, 0, 1, 1, parent.Handle, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        if (container == IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastPInvokeError());
        return new HandleRef(this, container);
    }

    internal void Use(ToolSession? session)
    {
        if (Session == session) { session?.Resize(container); return; }
        Session?.SetVisible(false);
        Session = session;
        if (session is null)
        {
            NativeMethods.ShowWindow(container, 0);
            return;
        }
        session.Attach(container);
        session.Resize(container);
        NativeMethods.ShowWindow(container, 5);
    }

    protected override void OnWindowPositionChanged(Rect bounds)
    {
        base.OnWindowPositionChanged(bounds);
        Session?.Resize(container);
    }

    protected override void DestroyWindowCore(HandleRef window)
    {
        Session?.Detach();
        Session = null;
        NativeMethods.DestroyWindow(window.Handle);
        container = IntPtr.Zero;
    }
}
