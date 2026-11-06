using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;

namespace AIFirst.Workspace;

/// <summary>深/浅主题的唯一开关。颜色本身在 Themes/Dark.xaml、Themes/Light.xaml 里。</summary>
internal static class ThemeManager
{
    private const string DarkValue = "dark";
    private const string LightValue = "light";
    private static string? settingsPath;
    private static bool persistBlocked;

    internal static bool IsDark { get; private set; }

    /// <summary>设置文件位置，同时供对话搬家进程轮询同一份数据。</summary>
    internal static string? PreferencesPath => settingsPath;

    /// <summary>主题变化后通知原生控件；External 用于告知已启动的工具页。</summary>
    internal static event Action<bool>? Changed;

    internal static void Initialize(string configuration)
    {
        settingsPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(configuration))!, "workspace-preferences.json");
        Apply(Read(), persist: false);
    }

    internal static void Toggle() => Apply(!IsDark);

    internal static void Apply(bool dark, bool persist = true)
    {
        IsDark = dark;
        SwapDictionary(dark);
        if (persist) Save(dark);
        Changed?.Invoke(dark);
    }

    private static void SwapDictionary(bool dark)
    {
        var app = Application.Current;
        if (app is null) return;
        var source = new Uri(dark ? "pack://application:,,,/Themes/Dark.xaml" : "pack://application:,,,/Themes/Light.xaml", UriKind.Absolute);
        var theme = new ResourceDictionary { Source = source };
        // 早期版本把颜色写成了应用级直接键，它们会盖住合并字典，导致切主题时顶栏不跟。
        // 先把这些直接键摘掉，再整体换掉合并字典，DynamicResource 才会全量重解析。
        foreach (var key in theme.Keys) app.Resources.Remove(key);
        var merged = app.Resources.MergedDictionaries;
        var previous = merged.FirstOrDefault(item => item.Source is not null && item.Source.OriginalString.Contains("Themes/", StringComparison.OrdinalIgnoreCase));
        merged.Add(theme);
        if (previous is not null) merged.Remove(previous);
    }

    private static bool Read()
    {
        if (settingsPath is null || !File.Exists(settingsPath)) return false;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(settingsPath));
            return document.RootElement.TryGetProperty("theme", out var theme)
                && theme.ValueKind == JsonValueKind.String
                && string.Equals(theme.GetString(), DarkValue, StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or InvalidOperationException)
        {
            persistBlocked = true;
            App.Log(exception);
            return false;
        }
    }

    private static void Save(bool dark)
    {
        if (settingsPath is null || persistBlocked) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(settingsPath)!);
            JsonObject root = new();
            if (File.Exists(settingsPath))
            {
                var text = File.ReadAllText(settingsPath);
                if (!string.IsNullOrWhiteSpace(text))
                {
                    try { root = JsonNode.Parse(text) as JsonObject ?? new JsonObject(); }
                    catch (JsonException) { persistBlocked = true; return; }
                }
            }
            root["theme"] = dark ? DarkValue : LightValue;
            var temporary = settingsPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                File.WriteAllText(temporary, root.ToJsonString());
                File.Move(temporary, settingsPath, true);
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            App.Log(exception);
        }
    }
}
