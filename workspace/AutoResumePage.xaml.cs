using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace AIFirst.Workspace;

public partial class AutoResumePage : UserControl, IDisposable
{
    private readonly IAutoResumeControl control;
    private readonly ResetNewsService? resetNews;
    private readonly CancellationTokenSource lifetime = new();
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(30) };
    private AutoResumeStatus? status;
    private bool disposed;
    private bool resetBusy;
    internal bool IsBusy { get; private set; }
    internal Func<DateTimeOffset> ResetClock { get; set; } = () => DateTimeOffset.UtcNow;

    public AutoResumePage() : this(new AutoResumeControl(), null) { }
    internal AutoResumePage(ResetNewsService resetNews) : this(new AutoResumeControl(), resetNews) { }
    internal AutoResumePage(IAutoResumeControl control, ResetNewsService? resetNews = null)
    {
        this.control = control;
        this.resetNews = resetNews;
        InitializeComponent();
        CodexLogo.Source = CreateIcon();
        ResetCalendar.Clock = () => ResetClock();
        if (resetNews is not null)
        {
            resetNews.Changed += ResetNewsChanged;
            PaintResetNews(resetNews.Snapshot);
        }
        timer.Tick += async (_, _) => { if (IsVisible) { await ExecuteFromUiAsync("status"); ResetCalendar.RefreshTime(); } };
        IsVisibleChanged += async (_, _) => { if (IsVisible) await ExecuteFromUiAsync("status"); };
        timer.Start();
    }

    internal static ImageSource CreateIcon()
    {
        var image = new BitmapImage();
        image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.UriSource = new Uri(Path.Combine(AppContext.BaseDirectory, "assets", "codex.png"));
        image.EndInit();
        image.Freeze();
        return image;
    }

    private void ResetNewsChanged(ResetNewsSnapshot value)
    {
        if (disposed || Dispatcher.HasShutdownStarted) return;
        if (Dispatcher.CheckAccess()) PaintResetNews(value);
        else Dispatcher.BeginInvoke(new Action(() => { if (!disposed) PaintResetNews(value); }));
    }

    internal void PaintResetNews(ResetNewsSnapshot value)
    {
        ResetEnabledSwitch.IsChecked = value.Enabled;
        ResetEnabledSwitch.IsEnabled = ResetRefreshButton.IsEnabled = resetNews is not null && !resetBusy;
        ResetStatusText.Text = value.StatusText;
        ResetDetailText.Text = value.DetailText;
        ResetStatusCard.Visibility = value.Enabled && value.Fresh && !value.Partial && value.Items.Count > 0 ? Visibility.Collapsed : Visibility.Visible;
        ResetCheckedText.Text = value.LastSuccess is { } success ? $"消息更新于（北京）{ResetNewsPresentation.BeijingStamp(success)}"
            : value.LastCheckedAt is { } checkedAt ? $"最近尝试（北京）{ResetNewsPresentation.BeijingStamp(checkedAt)}" : "尚未检查";
        ResetCalendar.SetItems(value.Items);
    }

    private async void ResetEnabledClick(object sender, RoutedEventArgs args) => await ExecuteResetFromUiAsync(ResetEnabledSwitch.IsChecked == true);
    private async void ResetRefreshClick(object sender, RoutedEventArgs args) => await ExecuteResetFromUiAsync(null);

    private async Task ExecuteResetFromUiAsync(bool? enabled)
    {
        if (resetNews is null || resetBusy || disposed) return;
        resetBusy = true;
        ResetEnabledSwitch.IsEnabled = ResetRefreshButton.IsEnabled = false;
        ResetRefreshButton.Content = enabled is null ? "检查中…" : "刷新";
        try
        {
            if (enabled is { } choice) await resetNews.SetEnabledAsync(choice);
            else await resetNews.RefreshAsync();
            if (!disposed) PaintResetNews(resetNews.Snapshot);
        }
        catch (OperationCanceledException) when (disposed) { }
        catch (OperationCanceledException) { throw; }
        catch (Exception)
        {
            if (disposed) return;
            PaintResetNews(resetNews.Snapshot);
            ResetStatusCard.Visibility = Visibility.Visible;
            ResetStatusText.Text = enabled is null ? "这次没能检查最新消息" : "提醒设置暂时没有保存成功";
            ResetDetailText.Text = enabled is null ? "这不代表没有新消息，稍后可以再点刷新。" : "请稍后再试，当前开关显示的是已保存的选择。";
        }
        finally
        {
            resetBusy = false;
            if (!disposed)
            {
                ResetEnabledSwitch.IsChecked = resetNews.Snapshot.Enabled;
                ResetEnabledSwitch.IsEnabled = ResetRefreshButton.IsEnabled = true;
                ResetRefreshButton.Content = "刷新";
            }
        }
    }

    private void OpenResetPostClick(object sender, RoutedEventArgs args)
    {
        if (sender is Button { Tag: string url } && !ResetNoticeWindow.TryOpenPost(url))
        {
            ResetDetailText.Text = "暂时没能打开原帖，请稍后再试。";
            ResetStatusCard.Visibility = Visibility.Visible;
        }
    }

    internal async Task<bool> PauseForResetAsync()
    {
        if (IsBusy || disposed) return false;
        await ExecuteAsync("credit-off");
        return status is { Installed: true, AutoRedeem: false };
    }

    internal Task RefreshAsync() => ExecuteAsync("status");
    private async void RefreshClick(object sender, RoutedEventArgs args) => await ExecuteFromUiAsync("status");
    private async void RunningClick(object sender, RoutedEventArgs args) => await ExecuteFromUiAsync(RunningSwitch.IsChecked == true ? "resume-on" : "resume-off");
    private async void CreditClick(object sender, RoutedEventArgs args) => await ExecuteFromUiAsync(CreditSwitch.IsChecked == true ? "credit-on" : "credit-off");
    private async void TimerClick(object sender, RoutedEventArgs args) => await ExecuteFromUiAsync(TimerSwitch.IsChecked == true ? "timer-on" : "timer-off");
    private async void AutostartClick(object sender, RoutedEventArgs args) => await ExecuteFromUiAsync(AutostartSwitch.IsChecked == true ? "autostart-on" : "autostart-off");

    private async Task ExecuteFromUiAsync(string action)
    {
        try { await ExecuteAsync(action); }
        catch (OperationCanceledException) when (disposed) { } // Closing the page cancels its own pending UI request.
    }

    internal async Task ExecuteAsync(string action)
    {
        if (IsBusy || disposed) return;
        IsBusy = true;
        RunningSwitch.IsEnabled = CreditSwitch.IsEnabled = TimerSwitch.IsEnabled = AutostartSwitch.IsEnabled = RefreshButton.IsEnabled = false;
        if (action != "status")
        {
            StateTitle.Text = "正在保存…";
            StateDescription.Text = "请稍等。";
            StateBadge.Background = new SolidColorBrush(Color.FromRgb(232, 242, 254));
            StateTitle.Foreground = new SolidColorBrush(Color.FromRgb(0, 104, 217));
        }
        try
        {
            status = await control.ExecuteAsync(action, lifetime.Token);
            if (disposed) return;
            PaintStatus(status);
            MessageCard.Visibility = Visibility.Collapsed;
        }
        catch (OperationCanceledException)
        {
            if (!disposed) { status = null; PaintUnknownStatus(); }
            throw;
        }
        catch (Exception)
        {
            if (disposed) return;
            // A failed change may have partially succeeded. Re-read rather than reusing cached switches.
            status = null;
            if (action != "status")
            {
                try { status = await control.ExecuteAsync("status", lifetime.Token); }
                catch (OperationCanceledException)
                {
                    if (!disposed) PaintUnknownStatus();
                    throw;
                }
                catch (Exception) { }
                if (disposed) return;
            }
            if (status is not null) PaintStatus(status);
            else PaintUnknownStatus();
            MessageText.Text = status is null ? "暂时没能确认状态，请点“刷新状态”再试。" : action switch
            {
                "start" when status.Running => "已重新确认：自动续跑已开启。",
                "start" => "这次没有开启成功，请再点一次开关。",
                "stop" when !status.Running && !status.Autostart => "已重新确认：自动续跑已关闭。",
                "stop" when !status.Running => "续跑已关闭，但开机自动开启还未关闭。请关闭“开机自动开启”。",
                "stop" => "这次没有关闭成功，请再点一次开关。",
                _ => "这次设置没有顺利完成，已重新确认当前状态，请按需要再试。"
            };
            MessageCard.Visibility = Visibility.Visible;
        }
        finally
        {
            IsBusy = false;
            if (!disposed)
            {
                RefreshButton.IsEnabled = true;
                RunningSwitch.IsEnabled = TimerSwitch.IsEnabled = AutostartSwitch.IsEnabled = status?.Installed == true;
                CreditSwitch.IsEnabled = status?.Installed == true && status.ResumeActive;
            }
        }
    }

    private void PaintUnknownStatus()
    {
        RunningSwitch.IsChecked = CreditSwitch.IsChecked = TimerSwitch.IsChecked = AutostartSwitch.IsChecked = null;
        TimerDescription.Text = "状态暂时无法确认，请刷新后再试。";
        StateTitle.Text = "状态暂时无法确认";
        StateDescription.Text = "确认后就可以继续使用开关。";
        StateBadge.Background = new SolidColorBrush(Color.FromRgb(238, 242, 247));
        StateTitle.Foreground = new SolidColorBrush(Color.FromRgb(91, 107, 126));
    }

    private void PaintStatus(AutoResumeStatus value)
    {
        RunningSwitch.IsChecked = value.ResumeActive;
        CreditSwitch.IsChecked = value.AutoRedeem;
        TimerSwitch.IsChecked = value.AutoStartWindow;
        AutostartSwitch.IsChecked = value.Autostart;
        StateTitle.Text = !value.Installed ? "自动续跑暂时不可用" : value.ResumeActive ? "已开启" : "已关闭";
        StateDescription.Text = !value.Installed ? "暂时无法开启，请稍后刷新再试。" : "5 小时或周额度用完后等待恢复，到账后接着原来的任务继续。是否用卡，由下面的开关决定。";
        StateBadge.Background = new SolidColorBrush(value.ResumeActive ? Color.FromRgb(234, 245, 239) : Color.FromRgb(238, 242, 247));
        StateTitle.Foreground = new SolidColorBrush(value.ResumeActive ? Color.FromRgb(22, 106, 75) : Color.FromRgb(91, 107, 126));
        TimerDescription.Text = TimerText(value);
    }

    internal static string TimerText(AutoResumeStatus value)
    {
        if (!value.AutoStartWindow) return "已关闭，不会自动发送计时请求。";
        if (!value.Running) return "暂未运行，请重新开启此功能。";
        var stamp = value.NextResetAt > 0 ? DateTimeOffset.FromUnixTimeSeconds(value.NextResetAt).ToOffset(TimeSpan.FromHours(8)).ToString("MM-dd HH:mm") : "";
        return value.TimerStatus switch
        {
            "started" => $"本轮计时已开始 · 下次恢复（北京）{stamp}",
            "normal-use" => $"已读取当前计时 · 下次恢复（北京）{stamp}",
            "waiting" when stamp.Length > 0 => $"下次恢复（北京）{stamp} · 到时自动检查，无需重复请求。",
            "activity" => "正在正常工作，本轮不额外发送计时请求。",
            "quota-blocked" => "正在等待额度恢复，不会为计时使用重置卡。",
            "unavailable" => "当前账号、模型或额度信息暂不适用，未确认计时。",
            "pending" => "正在确认本轮计时，请稍候。",
            "unconfirmed" => "本轮计时未确认，已暂停重复请求，避免多次消耗。",
            "error" => "计时记录暂时无法读取，已暂停请求，原记录保留。",
            _ => "已开启，正在检查本轮额度。"
        };
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        if (resetNews is not null) resetNews.Changed -= ResetNewsChanged;
        timer.Stop();
        lifetime.Cancel();
        lifetime.Dispose();
    }
}
