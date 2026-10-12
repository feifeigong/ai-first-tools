using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace AIFirst.Workspace;

internal sealed class WorkspacePreferences
{
    private readonly string path;
    private bool unreadable;
    internal WorkspacePreferences(string configuration) => path = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(configuration))!, "workspace-preferences.json");

    internal bool LoadCollapsed()
    {
        if (!File.Exists(path)) return false;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            return document.RootElement.GetProperty("sidebarCollapsed").GetBoolean();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException or KeyNotFoundException)
        {
            unreadable = true;
            App.Log(exception);
            return false;
        }
    }

    internal void SaveCollapsed(bool collapsed)
    {
        if (unreadable) throw new InvalidDataException("侧栏设置文件暂时无法读取，原文件已保留。");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, JsonSerializer.Serialize(new { sidebarCollapsed = collapsed }));
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
