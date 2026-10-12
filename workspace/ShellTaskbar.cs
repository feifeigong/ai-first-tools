using System;
using System.Runtime.InteropServices;

namespace AIFirst.Workspace;

internal static class ShellTaskbar
{
    [ComImport, Guid("56FDF342-FD6D-11D0-958A-006097C9A090"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ITaskbarList
    {
        void HrInit();
        void AddTab(IntPtr window);
        void DeleteTab(IntPtr window);
        void ActivateTab(IntPtr window);
        void SetActiveAlt(IntPtr window);
    }

    internal static void RemoveToolButton(IntPtr window)
    {
        object? instance = null;
        try
        {
            instance = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("56FDF344-FD6D-11D0-958A-006097C9A090"))!);
            var taskbar = (ITaskbarList)instance!;
            taskbar.HrInit();
            taskbar.DeleteTab(window);
        }
        catch (COMException exception) { App.Log(exception); }
        finally { if (instance is not null && Marshal.IsComObject(instance)) Marshal.ReleaseComObject(instance); }
    }
}
