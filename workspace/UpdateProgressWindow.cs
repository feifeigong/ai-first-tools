using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;

namespace AIFirst.Workspace;

internal sealed class UpdateProgressWindow : IDisposable
{
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(1) };
    private readonly string job;
    private readonly TextBlock stage = new() { Margin = new Thickness(0, 14, 0, 8), FontSize = 14 };
    private readonly TextBlock elapsed = new() { FontSize = 13 };
    private bool closing;
    internal Window Window { get; }
    internal string StageText => stage.Text;
    internal long ElapsedSeconds => (long)clock.Elapsed.TotalSeconds;

    internal UpdateProgressWindow(string directory)
    {
        job = directory;
        var panel = new StackPanel { Margin = new Thickness(28) };
        panel.Children.Add(new TextBlock { Text = "正在更新工具箱", FontSize = 20, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(stage);
        panel.Children.Add(elapsed);
        panel.Children.Add(new ProgressBar { Height = 4, IsIndeterminate = true, Margin = new Thickness(0, 16, 0, 0) });
        Window = new Window { Title = "AI一手工具箱 · 更新", Icon = BrandAssets.LoadWindowIcon(), Content = panel,
            Width = 470, Height = 230, ResizeMode = ResizeMode.NoResize, WindowStartupLocation = WindowStartupLocation.CenterScreen,
            FontFamily = new System.Windows.Media.FontFamily("Microsoft YaHei UI") };
        Window.Closing += OnClosing;
        timer.Tick += (_, _) => elapsed.Text = $"已用 {ElapsedSeconds} 秒，完成后自动打开。";
        timer.Start();
        SetStage(1, "准备替换程序");
    }

    internal void SetStage(int number, string label)
    {
        stage.Text = $"{label}（{number}/6）";
        elapsed.Text = $"已用 {ElapsedSeconds} 秒，完成后自动打开。";
        var path = Path.Combine(job, "progress.json");
        UpdatePackage.EnsureNoLinks(path);
        var temporary = path + ".tmp";
        UpdatePackage.EnsureNoLinks(temporary);
        File.WriteAllText(temporary, JsonSerializer.Serialize(new { step = number, phase = label, elapsedSeconds = ElapsedSeconds }, UpdatePackage.Json));
        File.Move(temporary, path, true);
    }

    private void OnClosing(object? sender, CancelEventArgs args) => args.Cancel = !closing;

    internal void Show() { Window.Show(); Window.Activate(); }
    internal void Activate() { Window.Show(); if (Window.WindowState == WindowState.Minimized) Window.WindowState = WindowState.Normal; Window.Activate(); }
    public void Dispose() { timer.Stop(); closing = true; Window.Closing -= OnClosing; Window.Close(); }
}
