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
        timer.Tick += async (_, _) => { CheckScheduled(); if (IsVisible) { await ExecuteFromUiAsync("status"); ResetCalendar.RefreshTime(); } };
        IsVisibleChanged += async (_, _) => { if (IsVisible) await ExecuteFromUiAsync("status"); };
        ThemeManager.Changed += ThemeChanged;
        ScheduledDateText.Text = DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)).ToString("yyyy-MM-dd");
        scheduledAt = ReadScheduledFile();
        scheduledLoaded = true;
        UpdateScheduledUi();
        timer.Start();
    }

    private void ThemeChanged(bool dark)
    {
        if (disposed || !Dispatcher.CheckAccess()) return;
        ResetCalendar.RepaintForTheme();
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
            StateBadge.SetResourceReference(Border.BackgroundProperty, "BadgeBusyBg");
            StateTitle.SetResourceReference(TextBlock.ForegroundProperty, "BadgeBusyInk");
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
        StateBadge.SetResourceReference(Border.BackgroundProperty, "BadgeNeutralBg");
        StateTitle.SetResourceReference(TextBlock.ForegroundProperty, "BadgeNeutralInk");
    }

    private void PaintStatus(AutoResumeStatus value)
    {
        RunningSwitch.IsChecked = value.ResumeActive;
        CreditSwitch.IsChecked = value.ResumeActive && value.AutoRedeem;
        TimerSwitch.IsChecked = value.AutoStartWindow;
        AutostartSwitch.IsChecked = value.Autostart;
        StateTitle.Text = !value.Installed ? "自动续跑暂时不可用" : value.ResumeActive ? "已开启" : "已关闭";
        StateDescription.Text = !value.Installed ? "暂时无法开启，请稍后刷新再试。" : value.ResumeActive ? "5 小时或周额度用完后等待恢复，到账后接着原来的任务继续。是否用卡，由下面的开关决定。" : "续跑已关闭，不会继续任务或自动使用重置卡。";
        StateBadge.SetResourceReference(Border.BackgroundProperty, value.ResumeActive ? "BadgeOnBg" : "BadgeNeutralBg");
        StateTitle.SetResourceReference(TextBlock.ForegroundProperty, value.ResumeActive ? "BadgeOnInk" : "BadgeNeutralInk");
        TimerDescription.Text = TimerText(value);
        CreditDescription.Text = value.ResumeActive ? "关闭后只等额度恢复；重新开启续跑不会自动打开用卡。" : "开启续跑后可设置；当前不会自动使用重置卡。";
        AutostartDescription.Text = !value.ResumeActive && value.AutoStartWindow ? "登录后仅运行 5 小时计时，不会续跑或使用重置卡。"
            : value.ResumeActive ? "登录后运行自动续跑" + (value.AutoStartWindow ? "和 5 小时计时。" : "。")
            : "续跑和计时都已关闭，无需登录后自动运行。";
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

    // ---------- 定时用卡 ----------
    private static string ScheduledFile
    {
        get
        {
            var directory = Path.GetDirectoryName(ThemeManager.PreferencesPath ?? Path.Combine(AppContext.BaseDirectory, "preferences.json")) ?? AppContext.BaseDirectory;
            return Path.Combine(directory, "scheduled-redeem.json");
        }
    }

    private DateTimeOffset? scheduledAt;
    private bool scheduledLoaded;

    private DateTimeOffset? ReadScheduledFile()
    {
        try
        {
            if (!File.Exists(ScheduledFile)) return null;
            using var document = System.Text.Json.JsonDocument.Parse(File.ReadAllText(ScheduledFile));
            if (document.RootElement.TryGetProperty("at", out var value) && DateTimeOffset.TryParse(value.GetString(), out var parsed)) return parsed;
        }
        catch (Exception exception) when (exception is IOException or System.Text.Json.JsonException or UnauthorizedAccessException) { App.Log(exception); }
        return null;
    }

    private void SaveScheduledFile(DateTimeOffset? when)
    {
        try
        {
            if (when is null) { if (File.Exists(ScheduledFile)) File.Delete(ScheduledFile); return; }
            Directory.CreateDirectory(Path.GetDirectoryName(ScheduledFile)!);
            File.WriteAllText(ScheduledFile, System.Text.Json.JsonSerializer.Serialize(new { at = when.Value.ToString("O") }));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
    }

    private void UpdateScheduledUi()
    {
        if (scheduledAt is null)
        {
            ScheduledStatus.Visibility = Visibility.Collapsed;
            ScheduledCancelButton.Visibility = Visibility.Collapsed;
            ScheduledSetButton.Visibility = Visibility.Visible;
            return;
        }
        ScheduledStatus.Text = "将在 " + scheduledAt.Value.ToString("M月d日 HH:mm") + " 用掉一张重置卡（只执行一次，软件需保持运行）";
        ScheduledStatus.Visibility = Visibility.Visible;
        ScheduledCancelButton.Visibility = Visibility.Visible;
        ScheduledSetButton.Visibility = Visibility.Collapsed;
    }

    private void ScheduledSetClick(object sender, RoutedEventArgs args)
    {
        var text = (ScheduledDateText.Text ?? "").Trim();
        if (!DateTime.TryParse(text, out var date) || !TimeSpan.TryParse(ScheduledTime.Text, out var time))
        {
            ScheduledStatus.Text = "日期按 2026-11-07 填写，时间按 05:00 填写。";
            ScheduledStatus.Visibility = Visibility.Visible;
            return;
        }
        var when = new DateTimeOffset(date.Date + time, TimeSpan.FromHours(8));
        if (when <= DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)))
        {
            ScheduledStatus.Text = "这个时间已经过去了，请选一个将来的时间。";
            ScheduledStatus.Visibility = Visibility.Visible;
            return;
        }
        scheduledAt = when;
        scheduledLoaded = true;
        SaveScheduledFile(when);
        UpdateScheduledUi();
    }

    private void ScheduledCancelClick(object sender, RoutedEventArgs args)
    {
        scheduledAt = null;
        scheduledLoaded = true;
        SaveScheduledFile(null);
        UpdateScheduledUi();
    }

    private void CheckScheduled()
    {
        if (!scheduledLoaded)
        {
            scheduledLoaded = true;
            scheduledAt = ReadScheduledFile();
            UpdateScheduledUi();
        }
        if (scheduledAt is null) return;
        if (DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)) < scheduledAt) return;
        var when = scheduledAt.Value;
        scheduledAt = null;
        SaveScheduledFile(null);
        UpdateScheduledUi();
        // 错过太久就不补执行，避免第二天开机时莫名其妙用掉一张卡
        if (DateTimeOffset.UtcNow.ToOffset(TimeSpan.FromHours(8)) - when > TimeSpan.FromMinutes(30))
        {
            ScheduledStatus.Text = "已错过设定时间超过 30 分钟，这次没有执行用卡。";
            ScheduledStatus.Visibility = Visibility.Visible;
            return;
        }
        RunRedeem(when);
    }

    private void RunRedeem(DateTimeOffset when)
    {
        try
        {
            var directory = Path.GetDirectoryName(ThemeManager.PreferencesPath ?? Path.Combine(AppContext.BaseDirectory, "preferences.json")) ?? AppContext.BaseDirectory;
            var connectionFile = Path.Combine(directory, "auto-resume-connection.json");
            if (!File.Exists(connectionFile))
            {
                ScheduledStatus.Text = "没有找到续跑程序配置，定时用卡没有执行。";
                ScheduledStatus.Visibility = Visibility.Visible;
                return;
            }
            using var connection = System.Text.Json.JsonDocument.Parse(File.ReadAllText(connectionFile));
            var python = connection.RootElement.TryGetProperty("Python", out var pythonValue) ? pythonValue.GetString() : null;
            var runner = connection.RootElement.TryGetProperty("Runner", out var runnerValue) ? runnerValue.GetString() : null;
            if (string.IsNullOrEmpty(python) || string.IsNullOrEmpty(runner))
            {
                ScheduledStatus.Text = "续跑程序配置不完整，定时用卡没有执行。";
                ScheduledStatus.Visibility = Visibility.Visible;
                return;
            }
            var script = Path.Combine(Path.GetDirectoryName(runner)!, "redeem_now.py");
            if (!File.Exists(script))
            {
                ScheduledStatus.Text = "找不到 redeem_now.py，定时用卡没有执行。";
                ScheduledStatus.Visibility = Visibility.Visible;
                return;
            }
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(python, "\"" + script + "\"")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden
            });
            ScheduledStatus.Text = when.ToString("M月d日 HH:mm") + " 已触发用卡，结果写在 redeem-scheduled.log。";
            ScheduledStatus.Visibility = Visibility.Visible;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or System.Text.Json.JsonException or System.ComponentModel.Win32Exception)
        {
            App.Log(exception);
            ScheduledStatus.Text = "定时用卡没能启动：" + exception.Message;
            ScheduledStatus.Visibility = Visibility.Visible;
        }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        ThemeManager.Changed -= ThemeChanged;
        if (resetNews is not null) resetNews.Changed -= ResetNewsChanged;
        timer.Stop();
        lifetime.Cancel();
        lifetime.Dispose();
    }
}
