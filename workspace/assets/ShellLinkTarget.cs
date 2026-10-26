using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace AIFirst.Toolbox
{
    // WScript.Shell can return an empty target for Chinese executable paths
    // on an English Windows profile. Read the original Unicode path directly.
    public static class ShellLinkTarget
    {
        [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
        private class ShellLink { }

        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
        private interface IShellLinkW
        {
            void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,
                         int characters, IntPtr findData, uint flags);
        }

        public static string Read(string shortcut)
        {
            var file = new FileInfo(shortcut);
            if (!file.Exists || file.Length > 1024 * 1024 ||
                (file.Attributes & FileAttributes.ReparsePoint) != 0) return string.Empty;
            object instance = new ShellLink();
            try
            {
                ((IPersistFile)instance).Load(file.FullName, 0);
                var result = new StringBuilder(32768);
                ((IShellLinkW)instance).GetPath(result, result.Capacity, IntPtr.Zero, 4); // SLGP_RAWPATH
                var value = Environment.ExpandEnvironmentVariables(result.ToString());
                if (string.IsNullOrEmpty(value) || !Path.IsPathRooted(value) || value.StartsWith(@"\\")) return string.Empty;
                return Path.GetFullPath(value);
            }
            finally { Marshal.FinalReleaseComObject(instance); }
        }
    }
}
