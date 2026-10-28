using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media.Imaging;

namespace AIFirst.Workspace;

public partial class WhatsNewWindow : Window
{
    private readonly ReleaseHighlights highlights;
    internal WhatsNewWindow(ReleaseHighlights highlights, Action acknowledge)
    {
        InitializeComponent(); this.highlights = highlights;
        ReleaseVersion.Text = "AI一手工具箱 · v" + highlights.Version;
        Heading.Text = highlights.Title; Description.Text = highlights.Description; HighlightsList.ItemsSource = highlights.Items;
        Icon = BrandAssets.LoadWindowIcon();
        var logo = Path.Combine(AppContext.BaseDirectory, "assets", "ai-first-app-icon.png");
        if (File.Exists(logo)) BrandImage.Source = new BitmapImage(new Uri(logo));
        Loaded += (_, _) => { MaxHeight = Math.Max(340, SystemParameters.WorkArea.Height - 40); HighlightsScroll.MaxHeight = Math.Max(70, MaxHeight - 340); DismissButton.Focus(); };
        Closed += (_, _) => acknowledge();
    }
    private void DismissClick(object sender, RoutedEventArgs args) => Close();
    private void DialogKeyDown(object sender, KeyEventArgs args) { if (args.Key == Key.Escape) { args.Handled = true; Close(); } }
    private void FullNotesClick(object sender, RoutedEventArgs args)
    {
        try { Process.Start(new ProcessStartInfo(highlights.Url) { UseShellExecute = true }); }
        catch (Exception e) when (e is Win32Exception or InvalidOperationException) { /* Keep the local notes usable offline. */ }
    }
}
