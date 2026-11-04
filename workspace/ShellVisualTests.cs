using System;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace AIFirst.Workspace;

/// <summary>把主窗口按两套主题各渲染一张，用于人工核对与回归。</summary>
internal static class ShellVisualTests
{
    internal static int Render(string outputDirectory)
    {
        var directory = Path.GetFullPath(outputDirectory);
        Directory.CreateDirectory(directory);
        var report = Path.Combine(directory, "shell-report.json");
        try
        {
            var configuration = Path.Combine(directory, "tools.json");
            if (!File.Exists(configuration)) File.WriteAllText(configuration, "[]");

            var window = new MainWindow(configuration, null, null, true)
            {
                WindowStartupLocation = WindowStartupLocation.Manual,
                Left = -30000,
                Top = -30000,
                ShowInTaskbar = false
            };
            var diagnostics = new System.Collections.Generic.List<string>();
            window.Show();
            window.UpdateLayout();
            try
            {
                ThemeManager.Apply(true, persist: false);
                diagnostics.Add("dark=" + Describe("AppBackground"));
                DrainLayout(window);
                RenderWindow(window, Path.Combine(directory, "shell-dark.png"));
                ThemeManager.Apply(false, persist: false);
                diagnostics.Add("light=" + Describe("AppBackground"));
                DrainLayout(window);
                RenderWindow(window, Path.Combine(directory, "shell-light.png"));
            }
            finally
            {
                window.Hide();
                window.ReleaseTools();
            }

            foreach (var dark in new[] { true, false })
            {
                ThemeManager.Apply(dark, persist: false);
                using var page = new AutoResumePage(new FixtureControl(), null);
                page.RefreshAsync().GetAwaiter().GetResult();
                var surface = new System.Windows.Controls.Border
                {
                    Background = (Brush)Application.Current.Resources["SurfaceCard"],
                    Child = page
                };
                RenderElement(surface, Path.Combine(directory, dark ? "page-dark.png" : "page-light.png"), 960, 1040);
                surface.Child = null;
            }

            File.WriteAllText(report, JsonSerializer.Serialize(new
            {
                passed = true,
                synthetic = true,
                diagnostics,
                images = new[] { "shell-dark.png", "shell-light.png", "page-dark.png", "page-light.png" },
                renderDpi = 96
            }, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        catch (Exception exception)
        {
            File.WriteAllText(report, JsonSerializer.Serialize(new { passed = false, error = exception.ToString() }, new JsonSerializerOptions { WriteIndented = true }));
            return 1;
        }
    }

    private static string Describe(string key)
    {
        var value = Application.Current?.TryFindResource(key);
        return value is SolidColorBrush brush ? brush.Color.ToString() : value?.GetType().Name ?? "missing";
    }

    private static void RenderWindow(Window window, string path)
    {
        var width = (int)Math.Ceiling(window.ActualWidth);
        var height = (int)Math.Ceiling(window.ActualHeight);
        if (width <= 0 || height <= 0) throw new InvalidOperationException("窗口尺寸无效，无法渲染。");
        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(window);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None);
        encoder.Save(output);
    }

    private sealed class FixtureControl : IAutoResumeControl
    {
        public System.Threading.Tasks.Task<AutoResumeStatus> ExecuteAsync(string action, System.Threading.CancellationToken cancellation) =>
            System.Threading.Tasks.Task.FromResult(new AutoResumeStatus(true, true, false, 1));
    }

    private static void RenderElement(FrameworkElement element, string path, double width, double height)
    {
        element.Width = width;
        element.Height = height;
        element.Measure(new Size(width, height));
        element.Arrange(new Rect(0, 0, width, height));
        DrainLayout(element);
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(width), (int)Math.Ceiling(height), 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(element);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None);
        encoder.Save(output);
    }

    private static void DrainLayout(FrameworkElement element)
    {
        element.UpdateLayout();
        var frame = new DispatcherFrame();
        Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.ContextIdle, new Action(() => frame.Continue = false));
        Dispatcher.PushFrame(frame);
        element.UpdateLayout();
    }
}
