using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Windows.Media.Imaging;

namespace AIFirst.Workspace;

internal static class ToolCatalog
{
    internal sealed class Entry
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string Executable { get; set; } = "";
        public string Icon { get; set; } = "";
        public bool EmbeddedStartup { get; set; }
    }

    internal static List<ToolDefinition> Load(string directory, string version)
    {
        var entries = JsonSerializer.Deserialize<List<Entry>>(File.ReadAllText(Path.Combine(directory, "assets", "tool-catalog.json")), new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        if (entries is null || entries.Count == 0) throw new InvalidDataException("工具包中没有登记工具，请使用完整的发布目录。");
        var tools = new List<ToolDefinition>();
        foreach (var entry in entries)
        {
            if (entry is null || entry.Executable is null) throw new InvalidDataException("工具包包含无效的工具登记。");
            var tool = new ToolDefinition { Id = entry.Id, Name = entry.Name, BuiltIn = true, EmbeddedStartup = entry.EmbeddedStartup, Executable = Resolve(directory, entry.Executable.Replace("{version}", version)) };
            ToolRepository.Validate(tool);
            if (tools.Any(existing => existing.Id.Equals(tool.Id, StringComparison.OrdinalIgnoreCase) || ToolRepository.SameExecutable(existing.Executable, tool.Executable))) throw new InvalidDataException("工具包包含重复的工具登记。");
            if (!string.IsNullOrEmpty(entry.Icon))
            {
                var image = new BitmapImage();
                image.BeginInit();
                image.CacheOption = BitmapCacheOption.OnLoad;
                image.UriSource = new Uri(Resolve(directory, entry.Icon));
                image.EndInit();
                image.Freeze();
                tool.Icon = image;
            }
            else tool.Icon = ToolRepository.ReadIcon(new ToolDefinition { Executable = tool.Executable });
            tools.Add(tool);
        }
        return tools;
    }

    private static string Resolve(string directory, string relative)
    {
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative)) throw new InvalidDataException("工具包只能使用包内的相对路径。");
        var root = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var resolved = Path.GetFullPath(Path.Combine(root, relative));
        if (!resolved.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("工具路径不能指向发布目录外部。");
        return resolved;
    }
}
