using System;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace AIFirst.Workspace;

// A formal installation may keep this user's existing preview data in place.
// The binding contains an enum, never a supplied filesystem path or chat data.
internal static class DataProfile
{
    internal const string FileName = "active-data-profile.json";
    internal static string Resolve(string root, bool development)
    {
        if (!Path.IsPathFullyQualified(root)) throw new InvalidDataException("资料位置无效。");
        root = Path.GetFullPath(root);
        Plain(root);
        var preview = Path.Combine(root,"memory-preview");
        if (development) { Plain(preview); return preview; }
        var binding = Path.Combine(root,FileName);
        Plain(binding);
        if (!File.Exists(binding)) return root;
        if (new FileInfo(binding).Length > 1024) throw new InvalidDataException("资料设置无效，原资料已保留。");
        using var data = JsonDocument.Parse(File.ReadAllText(binding));
        var value = data.RootElement;
        if (value.ValueKind != JsonValueKind.Object || value.EnumerateObject().Count()!=2
            || value.GetProperty("format").GetString()!="ai-first-data-profile-v1") throw new InvalidDataException("资料设置无效，原资料已保留。");
        var profile = value.GetProperty("profile").GetString();
        if (profile=="default") return root;
        if (profile!="memory-preview") throw new InvalidDataException("资料设置无效，原资料已保留。");
        Plain(preview);
        return preview;
    }
    private static void Plain(string path)
    {
        if ((File.Exists(path)||Directory.Exists(path)) && (File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)
            throw new InvalidDataException("资料位置暂时无法核对，原资料已保留。");
    }
}
