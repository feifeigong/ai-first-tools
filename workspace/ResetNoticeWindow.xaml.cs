using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Media;

namespace AIFirst.Workspace;

public partial class ResetNoticeWindow : Window
{
    private readonly Func<Task<bool>> pause;
    private readonly string originalUrl;
    private bool busy;
    internal bool IsBusy => busy;
    internal bool PauseSucceeded { get; private set; }

    internal ResetNoticeWindow(ResetNewsItem item, Func<Task<bool>> pause)
    {
        this.pause = pause;
        originalUrl = item.Url;
        InitializeComponent();
        NoticeLogo.Source = AutoResumePage.CreateIcon();
        Icon = NoticeLogo.Source;
        NoticeHeading.Text = item.Kind == "upcoming" ? "Codex 有重置预告" : "Codex 有重置消息";
        NoticePublished.Text = $"{item.SourceLabel} · 发布于（北京）{ResetNewsPresentation.BeijingStamp(item.PublishedAt)}";
        var chinese = ResetNewsPresentation.From(item);
        NoticeSummary.Text = chinese.Summary;
        NoticeTime.Text = chinese.TimeText;
        NoticeTime.Visibility = chinese.TimeText.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
        if (item.Kind == "announced") NoticeGuidance.Text = "公告不代表你的额度已经到账。关闭自动用卡可以保留卡；自动续跑可以继续开启，等额度恢复后接着做。";
        if (item.Kind == "banked")
        {
            NoticeHeading.Text = "Codex 有重置卡消息";
            NoticeGuidance.Text = "发卡不会直接恢复当前额度。你可以在 Codex 中查看是否收到，按需要再使用。";
            PauseButton.Visibility = Visibility.Collapsed;
        }
        NoticeExcerpt.Text = chinese.Description + (chinese.TimeNote.Length > 0 ? "\n" + chinese.TimeNote : "");
        MaxHeight = Math.Max(300, SystemParameters.WorkArea.Height - 48);
        Width = Math.Min(520, Math.Max(320, SystemParameters.WorkArea.Width - 32));
        Loaded += (_, _) => DismissButton.Focus();
    }

    private async void PauseClick(object sender, RoutedEventArgs args) => await PauseAsync();

    internal async Task PauseAsync()
    {
        if (busy || PauseSucceeded) return;
        busy = true;
        PauseButton.IsEnabled = DismissButton.IsEnabled = false;
        PauseButton.Content = "正在关闭…";
        NoticeResultCard.Visibility = Visibility.Collapsed;
        try
        {
            PauseSucceeded = await pause();
            if (PauseSucceeded)
            {
                NoticeResultCard.Background = new SolidColorBrush(Color.FromRgb(234, 245, 239));
                NoticeResultText.Foreground = new SolidColorBrush(Color.FromRgb(22, 106, 75));
                NoticeResultText.Text = "自动用卡已关闭。续跑和计时开关保持原样。";
                PauseButton.Content = "已关闭自动用卡";
                DismissButton.Content = "完成";
            }
            else ShowPauseFailure();
        }
        catch (Exception) { ShowPauseFailure(); }
        finally
        {
            busy = false;
            PauseButton.IsEnabled = !PauseSucceeded;
            DismissButton.IsEnabled = true;
            NoticeResultCard.Visibility = Visibility.Visible;
        }
    }

    private void ShowPauseFailure()
    {
        NoticeResultCard.Background = new SolidColorBrush(Color.FromRgb(255, 245, 228));
        NoticeResultText.Foreground = new SolidColorBrush(Color.FromRgb(138, 90, 30));
        NoticeResultText.Text = "暂时没有关闭成功，请再试一次。";
        PauseButton.Content = "再试一次";
    }

    private void DismissClick(object sender, RoutedEventArgs args) { if (!busy) Close(); }
    private void OnClosing(object? sender, CancelEventArgs args) { if (busy) args.Cancel = true; }
    private void OpenOriginalClick(object sender, RoutedEventArgs args)
    {
        if (TryOpenPost(originalUrl)) return;
        NoticeResultText.Text = "暂时没能打开原帖，请稍后再试。";
        NoticeResultCard.Visibility = Visibility.Visible;
    }

    internal static bool TryOpenPost(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps ||
            uri.Host is not ("x.com" or "www.x.com" or "twitter.com" or "www.twitter.com") ||
            !string.IsNullOrEmpty(uri.UserInfo)) return false;
        try { Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true }); return true; }
        catch (Exception) { return false; }
    }
}
