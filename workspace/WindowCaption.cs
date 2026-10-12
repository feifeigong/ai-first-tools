using System.Windows;
using System.Windows.Media;

namespace AIFirst.Workspace;

internal static class WindowCaption
{
    private static readonly Geometry maximize = Create("M1,1 H13 V13 H1 Z");
    private static readonly Geometry restore = Create("M4,1 H13 V10 H10 M1,4 H10 V13 H1 Z");

    internal static Geometry MaximizeGeometry(WindowState state) => state == WindowState.Maximized ? restore : maximize;
    internal static string MaximizeAction(WindowState state) => state == WindowState.Maximized ? "还原窗口" : "最大化";

    private static Geometry Create(string value)
    {
        var geometry = Geometry.Parse(value);
        geometry.Freeze();
        return geometry;
    }
}
