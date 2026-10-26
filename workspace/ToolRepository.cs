using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace AIFirst.Workspace;

public sealed class ToolDefinition : INotifyPropertyChanged
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    private string name = "";
    public string Name { get => name; set { name = value; OnPropertyChanged(); } }
    public string Executable { get; set; } = "";
    [JsonIgnore] public bool Embed { get; set; } = true;
    public bool BuiltIn { get; set; }
    [JsonIgnore] public string NativePage { get; set; } = "";
    [JsonIgnore] public bool EmbeddedStartup { get; set; }
    [JsonIgnore] public ImageSource? Icon { get; set; }
    private string status = "点击使用";
    [JsonIgnore] public string Status { get => status; set { status = value; OnPropertyChanged(); } }
    public event PropertyChangedEventHandler? PropertyChanged;
    private void OnPropertyChanged([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
}

public sealed class ToolRepository
{
    private readonly string configuration;
    private bool unreadable;
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true, PropertyNameCaseInsensitive = true };
    public ToolRepository(string path) => configuration = Path.GetFullPath(path);

    public List<ToolDefinition> Load(string bundledTool)
    {
        var tools = new List<ToolDefinition>
        {
            new() { Id = "dialog-mover", Name = "对话搬家", Executable = Path.GetFullPath(bundledTool), Embed = true, BuiltIn = true }
        };
        if (File.Exists(configuration))
        {
            List<ToolDefinition> saved;
            try
            {
                saved = JsonSerializer.Deserialize<List<ToolDefinition>>(File.ReadAllText(configuration), Options) ?? throw new InvalidDataException("工具配置为空，原文件已保留。");
            }
            catch (Exception exception) when (exception is IOException or JsonException or UnauthorizedAccessException)
            {
                unreadable = true;
                throw;
            }
            foreach (var tool in saved)
            {
                if (tool.BuiltIn || tool.Id == "dialog-mover") continue;
                try { Validate(tool); }
                catch (InvalidDataException) { unreadable = true; throw; }
                if (tools.Any(existing => existing.Id == tool.Id || SameExecutable(existing.Executable, tool.Executable))) continue;
                tools.Add(tool);
            }
        }
        foreach (var tool in tools) tool.Icon = ReadIcon(tool);
        return tools;
    }

    public void Save(IEnumerable<ToolDefinition> tools)
    {
        if (unreadable) throw new InvalidDataException("原工具配置无法读取，已阻止覆盖。请先备份并修复 tools.json，再重新打开工具箱。");
        var saved = tools.Where(tool => !tool.BuiltIn).ToList();
        foreach (var tool in saved) Validate(tool);
        var directory = Path.GetDirectoryName(configuration)!;
        Directory.CreateDirectory(directory);
        var temporary = configuration + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, JsonSerializer.Serialize(saved, Options));
            File.Move(temporary, configuration, true);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }

    public static void Validate(ToolDefinition tool)
    {
        if (string.IsNullOrWhiteSpace(tool.Id) || tool.Id.Length > 80 || string.IsNullOrWhiteSpace(tool.Name) || tool.Name.Length > 80)
            throw new InvalidDataException("工具名称或登记信息无效。");
        if (string.IsNullOrWhiteSpace(tool.Executable) || !Path.IsPathFullyQualified(tool.Executable) || !string.Equals(Path.GetExtension(tool.Executable), ".exe", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("请选择完整路径的 EXE 程序，不能使用命令、脚本或快捷方式。");
        tool.Executable = Path.GetFullPath(tool.Executable);
    }

    public static bool SameExecutable(string first, string second) => string.Equals(Path.GetFullPath(first), Path.GetFullPath(second), StringComparison.OrdinalIgnoreCase);
    public static string ConfigurationKey(string configuration) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Path.GetFullPath(configuration).ToUpperInvariant())))[..16];

    public static ImageSource? ReadIcon(ToolDefinition tool)
    {
        try
        {
            if (tool.BuiltIn)
            {
                var bitmap = new BitmapImage(new Uri(Path.Combine(AppContext.BaseDirectory, "assets", "dialog-mover.png")));
                bitmap.Freeze();
                return bitmap;
            }
            using var icon = System.Drawing.Icon.ExtractAssociatedIcon(tool.Executable);
            if (icon is null) return null;
            var image = Imaging.CreateBitmapSourceFromHIcon(icon.Handle, System.Windows.Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
            image.Freeze();
            return image;
        }
        catch (Exception exception) when (exception is IOException or ArgumentException or System.ComponentModel.Win32Exception) { return null; }
    }
}
