using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AIFirst.Workspace;

internal sealed record ReleaseHighlight(string Label, string Title, string Text);
internal sealed record ReleaseHighlights(string Version, string Title, string Description, List<ReleaseHighlight> Items)
{
    internal string Url => UpdateClient.Repository + "/releases/tag/v" + Version;
    internal static void Fields(JsonElement value, params string[] expected)
    {
        if (value.ValueKind != JsonValueKind.Object) throw new InvalidDataException();
        var actual = value.EnumerateObject().Select(p => p.Name).ToArray();
        if (actual.Length != expected.Length || !actual.OrderBy(x => x).SequenceEqual(expected.OrderBy(x => x))) throw new InvalidDataException();
    }
    internal static bool ValidVersion(string value) => Regex.IsMatch(value, @"\A\d+\.\d+\.\d+(?:-macos-preview\.\d+)?\z") && value.Length <= 48;
    private static string Text(JsonElement value, string key, int limit)
    {
        var text = value.GetProperty(key).GetString();
        if (string.IsNullOrWhiteSpace(text) || text.Length > limit || text.Any(char.IsControl)) throw new InvalidDataException();
        return text;
    }
    internal static ReleaseHighlights Parse(string json, string version)
    {
        using var parsed = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 8 });
        var root = parsed.RootElement;
        Fields(root, "schema", "versions", "title", "description", "items");
        if (root.GetProperty("schema").GetInt32() != 1 || !ValidVersion(version)) throw new InvalidDataException();
        var versions = root.GetProperty("versions"); Fields(versions, "windows", "macos");
        var windows = versions.GetProperty("windows").GetString() ?? "";
        var mac = versions.GetProperty("macos").GetString() ?? "";
        if (!ValidVersion(windows) || windows.Contains('-') || !ValidVersion(mac) || !mac.Contains("-macos-preview.") || windows != version) throw new InvalidDataException();
        var rows = root.GetProperty("items");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() is < 1 or > 3) throw new InvalidDataException();
        var items = new List<ReleaseHighlight>();
        foreach (var row in rows.EnumerateArray())
        {
            Fields(row, "label", "title", "text"); var label = Text(row, "label", 4);
            if (label is not ("新增" or "改进" or "修复" or "完善")) throw new InvalidDataException();
            items.Add(new(label, Text(row, "title", 32), Text(row, "text", 140)));
        }
        return new(version, Text(root, "title", 32), Text(root, "description", 80), items);
    }
    internal static ReleaseHighlights? Load(string path, string version)
    {
        try { return new FileInfo(path).Length <= 32768 ? Parse(File.ReadAllText(path), version) : null; }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException or JsonException or InvalidOperationException or FormatException or KeyNotFoundException) { return null; }
    }
}

internal sealed class ReleaseHighlightsState
{
    private readonly string path;
    private readonly string version;
    private bool acknowledged;
    internal ReleaseHighlightsState(string directory, string version) { path = Path.Combine(directory, "whats-new.json"); this.version = version; }
    private List<string> Read()
    {
        UpdatePackage.EnsureNoLinks(path);
        if (Directory.Exists(path)) throw new InvalidDataException();
        if (!File.Exists(path)) return new();
        if (new FileInfo(path).Length > 16384) throw new InvalidDataException();
        using var parsed = JsonDocument.Parse(File.ReadAllText(path)); var root = parsed.RootElement;
        ReleaseHighlights.Fields(root, "schema", "seen");
        if (root.GetProperty("schema").GetInt32() != 1) throw new InvalidDataException();
        var rows = root.GetProperty("seen");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 64) throw new InvalidDataException();
        var seen = rows.EnumerateArray().Select(x => x.GetString() ?? "").ToList();
        if (seen.Any(x => !ReleaseHighlights.ValidVersion(x)) || seen.Distinct().Count() != seen.Count) throw new InvalidDataException();
        return seen;
    }
    internal bool ShouldShow
    {
        get { try { return !acknowledged && ReleaseHighlights.ValidVersion(version) && !Read().Contains(version); } catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException or JsonException or InvalidOperationException or FormatException) { return false; } }
    }
    internal bool Acknowledge()
    {
        acknowledged = true;
        string? temporary = null;
        try
        {
            if (!ReleaseHighlights.ValidVersion(version)) return false;
            var seen = Read(); if (seen.Contains(version)) return true;
            seen = seen.TakeLast(63).Append(version).ToList();
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            UpdatePackage.EnsureNoLinks(path);
            temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temporary, JsonSerializer.Serialize(new { schema = 1, seen }));
            File.Move(temporary, path, true); return true;
        }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException or JsonException or InvalidOperationException or FormatException) { return false; }
        finally { if (temporary is not null && File.Exists(temporary)) try { File.Delete(temporary); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { } }
    }
}
