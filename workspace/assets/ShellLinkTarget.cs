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
            void GetIDList(out IntPtr value);
            void SetIDList(IntPtr value);
            void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int size);
            void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string value);
            void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int size);
            void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string value);
            void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int size);
            void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string value);
            void GetHotkey(out short value);
            void SetHotkey(short value);
            void GetShowCmd(out int value);
            void SetShowCmd(int value);
            void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int size, out int index);
            void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string value, int index);
            void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string value, uint reserved);
            void Resolve(IntPtr window, uint flags);
            void SetPath([MarshalAs(UnmanagedType.LPWStr)] string value);
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct PropertyKey
        {
            public Guid Format;
            public uint Id;
            public PropertyKey(uint id) { Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"); Id = id; }
        }
        [StructLayout(LayoutKind.Explicit, Size = 24)]
        private struct PropVariant
        {
            [FieldOffset(0)] public ushort Type;
            [FieldOffset(8)] public IntPtr Text;
        }
        [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
        private interface IPropertyStore
        {
            void GetCount(out uint count);
            void GetAt(uint index, out PropertyKey key);
            void GetValue(ref PropertyKey key, out PropVariant value);
            void SetValue(ref PropertyKey key, ref PropVariant value);
            void Commit();
        }
        [DllImport("ole32.dll")]
        private static extern int PropVariantClear(ref PropVariant value);

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

        public static string ReadAppId(string shortcut)
        {
            if (string.IsNullOrEmpty(Read(shortcut))) return string.Empty;
            object instance = new ShellLink();
            try
            {
                ((IPersistFile)instance).Load(Path.GetFullPath(shortcut), 0);
                var key = new PropertyKey(5);
                PropVariant value;
                ((IPropertyStore)instance).GetValue(ref key, out value);
                try { return value.Type == 31 ? Marshal.PtrToStringUni(value.Text) ?? string.Empty : string.Empty; }
                finally { PropVariantClear(ref value); }
            }
            finally { Marshal.FinalReleaseComObject(instance); }
        }

        public static void Create(string shortcut, string target)
        {
            if (File.Exists(shortcut)) throw new IOException("Shortcut already exists");
            object instance = new ShellLink();
            try
            {
                ((IShellLinkW)instance).SetPath(Path.GetFullPath(target));
                ((IPersistFile)instance).Save(Path.GetFullPath(shortcut), true);
            }
            finally { Marshal.FinalReleaseComObject(instance); }
        }

        public static bool ApplyBranding(string shortcut, string expectedTarget, string appId, string icon)
        {
            if (!string.Equals(Read(shortcut), Path.GetFullPath(expectedTarget), StringComparison.OrdinalIgnoreCase)) return false;
            var image = new FileInfo(icon);
            if (!image.Exists || (image.Attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Missing toolbox icon");
            object instance = new ShellLink();
            try
            {
                ((IPersistFile)instance).Load(Path.GetFullPath(shortcut), 2);
                ((IShellLinkW)instance).SetIconLocation(image.FullName, 0);
                var key = new PropertyKey(5);
                var value = new PropVariant { Type = 31, Text = Marshal.StringToCoTaskMemUni(appId) };
                try { ((IPropertyStore)instance).SetValue(ref key, ref value); }
                finally { PropVariantClear(ref value); }
                ((IPropertyStore)instance).Commit();
                ((IPersistFile)instance).Save(Path.GetFullPath(shortcut), true);
                return true;
            }
            finally { Marshal.FinalReleaseComObject(instance); }
        }
    }
}
