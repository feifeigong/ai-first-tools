using System;
using System.Collections.Generic;
using System.Windows.Media;

namespace AIFirst.Workspace;

/// <summary>
/// 代码里一次性生成的控件（日历格、事件行）没法用 DynamicResource，
/// 这里把浅色稿里的字面色值映射到当前主题，重绘时再取一次即可。
/// </summary>
internal static class ThemePalette
{
    private static readonly Dictionary<string, string> Dark = new(StringComparer.OrdinalIgnoreCase)
    {
        ["#202D3A"] = "#EDEDEE",
        ["#5B6B7E"] = "#8A8B90",
        ["#64748B"] = "#71737A",
        ["#7C8795"] = "#8B8D93",
        ["#0068D9"] = "#A78BFA",
        ["#207A58"] = "#4ADE80",
        ["#7252A3"] = "#C4B5FD",
        ["#7A5A28"] = "#E0C08A",
        ["#EAF3FF"] = "#241E38",
        ["#BDD7F5"] = "#3A2F58",
        ["#5F9DE0"] = "#8B5CF6",
        ["#EAF5EF"] = "#17251F",
        ["#F1ECF8"] = "#241E38",
        ["#FBF0DC"] = "#2E2617",
        ["#EFF2F6"] = "#24262A",
        ["#E9EDF3"] = "#232427",
        ["#FFFFFF"] = "#151618",
    };

    internal static string Resolve(string lightHex) =>
        ThemeManager.IsDark && Dark.TryGetValue(lightHex, out var dark) ? dark : lightHex;

    internal static Brush Ink(string lightHex) =>
        (Brush)new BrushConverter().ConvertFromString(Resolve(lightHex))!;
}
