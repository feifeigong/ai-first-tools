using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Interop;
using System.Windows.Threading;

namespace AIFirst.Workspace;

public partial class MainWindow : Window
{
    public static readonly DependencyProperty IsSidebarCollapsedProperty = DependencyProperty.Register(nameof(IsSidebarCollapsed), typeof(bool), typeof(MainWindow), new PropertyMetadata(false, (owner, _) => ((MainWindow)owner).UpdateSidebar()));
    public bool IsSidebarCollapsed { get => (bool)GetValue(IsSidebarCollapsedProperty); set => SetValue(IsSidebarCollapsedProperty, value); }
    private readonly ObservableCollection<ToolDefinition> tools = new();
    private readonly Dictionary<string, ToolSession> sessions = new();
    private readonly HashSet<string> opening = new();
    private readonly CancellationTokenSource lifetime = new();
    private readonly WorkspacePreferences preferences;
    private readonly DispatcherTimer monitor = new() { Interval = TimeSpan.FromSeconds(1) };
    private readonly string? healthReport;
    private ToolWindowHost? host;
    private ToolDefinition? selected;
    private bool released;
    private bool closing;
    private bool allowClose;
    private readonly UpdateClient updates;
    private readonly string updateSettings;
    private readonly string? updateConfiguration;
    private readonly string? updateTool;
    private readonly DispatcherTimer updateTimer = new() { Interval = TimeSpan.FromHours(6) };
    private CancellationTokenSource? downloading;
    private UpdateRelease? availableUpdate;
    private string? preparedUpdate;
    private string? preparedVersion;
    private bool checkingUpdates;
    private bool restartingForUpdate;

    public MainWindow(string configuration, string? toolOverride, string? report = null, bool developmentTools = false) : this(configuration, toolOverride, report, developmentTools, new UpdateClient()) { }

    internal MainWindow(string configuration, string? toolOverride, string? report, bool developmentTools, UpdateClient updateClient)
    {
        updates = updateClient;
        updateSettings = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(configuration))!, "updates");
        updateConfiguration = developmentTools ? configuration : null;
        updateTool = toolOverride;
        InitializeComponent();
        VersionText.Text = "v" + UpdateClient.CurrentVersion;
        Icon = BrandAssets.LoadWindowIcon();
        StateChanged += (_, _) => UpdateCaption();
        UpdateCaption();
        healthReport = report;
        Width = Math.Min(Width, SystemParameters.WorkArea.Width - 30);
        Height = Math.Min(Height, SystemParameters.WorkArea.Height - 30);
        preferences = new WorkspacePreferences(configuration);
        ShowLogo(new BrandAssets(configuration).Load());
        IsSidebarCollapsed = preferences.LoadCollapsed();
        UpdateSidebar();
        var packageVersion = typeof(App).Assembly.GetName().Version!.ToString(2);
        var bundled = toolOverride ?? Path.Combine(AppContext.BaseDirectory, "tools", "dialog-mover-v" + packageVersion, "对话搬家.exe");
        try
        {
            var available = developmentTools || toolOverride is not null ? new ToolRepository(configuration).Load(bundled) : ToolCatalog.Load(AppContext.BaseDirectory, packageVersion);
            foreach (var tool in available) tools.Add(tool);
        }
        catch (Exception exception) when (exception is IOException or System.Text.Json.JsonException or UnauthorizedAccessException or FileFormatException or NotSupportedException or ArgumentException)
        {
            App.Log(exception);
            ShowBlank("工具包暂时无法打开", "请使用完整的发布目录。" + Environment.NewLine + exception.Message, false);
        }
        ToolsList.ItemsSource = tools;
        Loaded += (_, _) =>
        {
            host = new ToolWindowHost();
            HostSlot.Children.Add(host);
            Dispatcher.BeginInvoke(() => ToolsList.SelectedIndex = 0, DispatcherPriority.Loaded);
            monitor.Start();
            ReadUpdateReceipt();
            _ = CheckAfterOpeningAsync();
            updateTimer.Start();
        };
        monitor.Tick += MonitorSessions;
        updateTimer.Tick += async (_, _) => await CheckUpdatesAsync(false);
    }

    private void ShowLogo(ImageSource? image)
    {
        BrandLogo.Source = image;
        BrandLogo.Visibility = image is null ? Visibility.Collapsed : Visibility.Visible;
        BrandText.Visibility = image is null ? Visibility.Visible : Visibility.Collapsed;
    }

    private void UpdateSidebar()
    {
        if (SidebarColumn is null || SidebarToggle is null || ToolSidebar is null) return;
        SidebarColumn.Width = new GridLength(IsSidebarCollapsed ? 0 : 184);
        ToolSidebar.Visibility = IsSidebarCollapsed ? Visibility.Collapsed : Visibility.Visible;
        var action = IsSidebarCollapsed ? "展开工具侧栏" : "收起工具侧栏";
        SidebarToggle.ToolTip = action;
        SidebarPane.Visibility = IsSidebarCollapsed ? Visibility.Collapsed : Visibility.Visible;
        System.Windows.Automation.AutomationProperties.SetName(SidebarToggle, action);
    }

    private void ToggleSidebarClick(object sender, RoutedEventArgs args)
    {
        IsSidebarCollapsed = !IsSidebarCollapsed;
        if (selected is not null && sessions.TryGetValue(selected.Id, out var session)) ScheduleHealth(selected, session);
        try { preferences.SaveCollapsed(IsSidebarCollapsed); }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            App.Log(exception);
            ShowStatus("侧栏设置暂未保存，本次仍可正常使用。");
        }
    }

    private void ShowStatus(string text)
    {
        FooterStatus.Text = text;
        StatusBanner.Visibility = string.IsNullOrEmpty(text) ? Visibility.Collapsed : Visibility.Visible;
    }

    protected override void OnSourceInitialized(EventArgs args)
    {
        base.OnSourceInitialized(args);
        HwndSource.FromHwnd(new WindowInteropHelper(this).Handle)?.AddHook(WindowMessage);
    }

    private IntPtr WindowMessage(IntPtr window, int message, IntPtr first, IntPtr second, ref bool handled)
    {
        if (message != 0x0024 || second == IntPtr.Zero) return IntPtr.Zero;
        var monitor = NativeMethods.MonitorFromWindow(window, 2);
        var information = new NativeMethods.MonitorInfo { Size = Marshal.SizeOf<NativeMethods.MonitorInfo>() };
        if (monitor == IntPtr.Zero || !NativeMethods.GetMonitorInfo(monitor, ref information)) return IntPtr.Zero;
        var limits = Marshal.PtrToStructure<NativeMethods.MinMaxInfo>(second);
        NativeMethods.ApplyWorkArea(ref limits, information.Monitor, information.WorkArea);
        var scale = VisualTreeHelper.GetDpi(this);
        limits.MinTrackSize.X = Math.Max(limits.MinTrackSize.X, (int)Math.Ceiling(MinWidth * scale.DpiScaleX));
        limits.MinTrackSize.Y = Math.Max(limits.MinTrackSize.Y, (int)Math.Ceiling(MinHeight * scale.DpiScaleY));
        Marshal.StructureToPtr(limits, second, false);
        handled = true;
        return IntPtr.Zero;
    }

    private async void SelectedToolChanged(object sender, SelectionChangedEventArgs args)
    {
        if (ToolsList.SelectedItem is not ToolDefinition tool || host is null || released || closing) return;
        if (selected is not null && sessions.ContainsKey(selected.Id)) selected.Status = "已打开";
        selected = tool;
        ShowStatus("");
        BlankIcon.Source = tool.Icon;
        if (sessions.TryGetValue(tool.Id, out var existing) && !existing.Process.HasExited && existing.Window != IntPtr.Zero)
        {
            Present(tool, existing);
            return;
        }
        host.Use(null);
        ShowBlank(tool.Name, "正在准备，很快就好…", false);
        await OpenToolAsync(tool);
    }

    private void Present(ToolDefinition tool, ToolSession session)
    {
        if (session.UseSeparateWindow)
        {
            host?.Use(null);
            session.OpenManagedWindow(new WindowInteropHelper(this).Handle);
            ShowBlank(tool.Name + "已打开", "直接使用弹出的窗口就好。下次点左边的名字，会回到这个窗口。", true);
            RetryButton.Content = "继续使用";
            tool.Status = "已打开";
            return;
        }
        try
        {
            HostSlot.Visibility = Visibility.Visible;
            host!.Use(session);
            BlankState.Visibility = Visibility.Collapsed;
            LoadingView.Visibility = Visibility.Collapsed;
            tool.Status = "使用中";
            ScheduleHealth(tool, session);
        }
        catch (Exception exception) when (exception is Win32Exception or InvalidOperationException)
        {
            App.Log(exception);
            host?.Use(null);
            session.UseSeparateWindow = true;
            Present(tool, session);
        }
    }

    private async Task OpenToolAsync(ToolDefinition tool)
    {
        if (opening.Contains(tool.Id) || closing || released) return;
        opening.Add(tool.Id);
        try
        {
            if (!sessions.TryGetValue(tool.Id, out var session) || session.Process.HasExited)
            {
                if (session is not null) { sessions.Remove(tool.Id); session.Dispose(); }
                tool.Status = "正在打开…";
                session = new ToolSession(tool);
                sessions.Add(tool.Id, session);
            }
            if (session.Window == IntPtr.Zero) await session.FindWindowAsync(lifetime.Token);
            if (released) return;
            var keepForeground = IsActive || NativeMethods.GetForegroundWindow() == session.Window;
            session.ManageTaskbar(new WindowInteropHelper(this).Handle);
            tool.Status = "已打开";
            if (selected?.Id == tool.Id && !closing)
            {
                Present(tool, session);
                if (keepForeground && session.Attached) NativeMethods.SetForegroundWindow(new WindowInteropHelper(this).Handle);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception exception) when (exception is IOException or Win32Exception or InvalidOperationException or TimeoutException)
        {
            App.Log(exception);
            WriteHealth(tool, null, exception.Message);
            tool.Status = "没打开";
            if (selected?.Id == tool.Id && !closing) ShowBlank(tool.Name + "还没打开", exception.Message, true);
        }
        finally { opening.Remove(tool.Id); }
    }

    private void ScheduleHealth(ToolDefinition tool, ToolSession session)
    {
        if (healthReport is null) return;
        Dispatcher.BeginInvoke(() =>
        {
            if (!released && !closing && selected?.Id == tool.Id && sessions.TryGetValue(tool.Id, out var active) && active == session) WriteHealth(tool, session, null);
        }, DispatcherPriority.ContextIdle);
    }

    private void WriteHealth(ToolDefinition tool, ToolSession? session, string? error)
    {
        if (healthReport is null || !tool.BuiltIn) return;
        try
        {
            var bounds = new NativeMethods.Rectangle();
            if (session is not null) NativeMethods.GetWindowRect(session.Window, out bounds);
            var parent = session is null ? IntPtr.Zero : NativeMethods.GetParent(session.Window);
            NativeMethods.GetWindowThreadProcessId(parent, out var parentProcess);
            var data = new { ready = error is null && session?.Attached == true && parentProcess == Environment.ProcessId, tool = tool.Id, executable = tool.Executable, attached = session?.Attached == true, startupWasHidden = session?.StartupWasHidden, hostProcess = Environment.ProcessId, toolProcess = session?.Process.Id, width = bounds.Right - bounds.Left, height = bounds.Bottom - bounds.Top, error };
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(healthReport))!);
            File.WriteAllText(healthReport, System.Text.Json.JsonSerializer.Serialize(data, new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
    }

    private void ShowBlank(string title, string description, bool retry)
    {
        HostSlot.Visibility = Visibility.Collapsed;
        BlankState.Visibility = retry ? Visibility.Visible : Visibility.Collapsed;
        LoadingView.Visibility = retry ? Visibility.Collapsed : Visibility.Visible;
        LoadingTitle.Text = selected?.Name ?? "对话搬家";
        BlankTitle.Text = title;
        BlankDescription.Text = description;
        RetryButton.Content = "再试一次";
        RetryButton.Visibility = retry ? Visibility.Visible : Visibility.Collapsed;
    }

    private async void RetryClick(object sender, RoutedEventArgs args)
    {
        if (selected is not null) await OpenToolAsync(selected);
    }

    private void MonitorSessions(object? sender, EventArgs args)
    {
        if (closing) return;
        foreach (var entry in sessions.ToList())
        {
            if (opening.Contains(entry.Key) || !entry.Value.Process.HasExited) continue;
            ForgetSession(entry.Key, entry.Value);
        }
    }

    private void ForgetSession(string id, ToolSession session)
    {
        if (host?.Session == session) host.Use(null);
        sessions.Remove(id);
        session.Definition.Status = "点击使用";
        session.Dispose();
        if (selected?.Id == id) ShowBlank(selected.Name + "已关闭", "想继续用，点下面的按钮就好。", true);
    }

    public void ReleaseTools()
    {
        if (released) return;
        released = true;
        lifetime.Cancel();
        monitor.Stop();
        updateTimer.Stop();
        downloading?.Cancel();
        updates.Dispose();
        host?.Use(null);
        foreach (var session in sessions.Values)
        {
            try { session.Dispose(); }
            catch (Win32Exception exception) { App.Log(exception); }
        }
        sessions.Clear();
    }

    private async void OnClosing(object? sender, CancelEventArgs args)
    {
        if (allowClose) { ReleaseTools(); return; }
        args.Cancel = true;
        if (closing) return;
        closing = true;
        ToolsList.IsEnabled = SidebarToggle.IsEnabled = false;
        ShowStatus(restartingForUpdate ? "正在保存并关闭工具，随后自动更新…" : "正在关闭，请稍等…");
        try
        {
            await Dispatcher.Yield(DispatcherPriority.Background);
            while (opening.Count > 0) await Task.Delay(100);
            foreach (var entry in sessions.ToList().OrderByDescending(item => item.Key == selected?.Id))
            {
                var session = entry.Value;
                if (session.Process.HasExited) { ForgetSession(entry.Key, session); continue; }
                selected = session.Definition;
                ToolsList.SelectedItem = selected;
                BlankIcon.Source = selected.Icon;
                if (session.Window != IntPtr.Zero) Present(selected, session);
                if (!await session.TryCloseAsync())
                {
                    Present(selected, session);
                    ShowStatus(selected.Name + "还有事情没结束，完成后再点 × 关闭。");
                    if (restartingForUpdate) ShowUpdateOffer("请先完成工具里的任务，再点更新并重启。不会强制停止搬运。");
                    return;
                }
                ForgetSession(entry.Key, session);
            }
            if (restartingForUpdate && preparedUpdate is not null) await UpdateRunner.StartAsync(preparedUpdate);
            allowClose = true;
            Close();
        }
        catch (Exception exception) when (exception is Win32Exception or InvalidOperationException or IOException or TimeoutException)
        {
            App.Log(exception);
            ShowStatus("暂时没关好。先处理工具里的提示，再点 ×。");
            if (restartingForUpdate) ShowUpdateOffer("没有启动更新，当前版本可以继续使用。稍后再试一次。");
        }
        finally
        {
            closing = false;
            restartingForUpdate = false;
            if (!released) ToolsList.IsEnabled = SidebarToggle.IsEnabled = true;
        }
    }

    private async Task CheckAfterOpeningAsync()
    {
        try { await Task.Delay(3000, lifetime.Token); await Task.Run(UpdateRunner.CleanupCompletedJobs, lifetime.Token); await CheckUpdatesAsync(false); }
        catch (OperationCanceledException) { }
    }

    private async void CheckUpdateClick(object sender, RoutedEventArgs args)
    {
        if (availableUpdate is not null) ShowUpdateOffer();
        else await CheckUpdatesAsync(true);
    }

    private async Task CheckUpdatesAsync(bool manual)
    {
        if (released || closing || checkingUpdates || downloading is not null) return;
        var timestamp = Path.Combine(updateSettings, "checked-at.txt");
        if (!manual)
        {
            try
            {
                if (File.Exists(timestamp) && DateTimeOffset.TryParse(File.ReadAllText(timestamp), out var checkedAt) && checkedAt <= DateTimeOffset.UtcNow && DateTimeOffset.UtcNow - checkedAt < TimeSpan.FromHours(6))
                {
                    var cachedPath = Path.Combine(updateSettings, "latest-release.json");
                    if (File.Exists(cachedPath))
                    {
                        var cached = System.Text.Json.JsonSerializer.Deserialize<UpdateRelease>(File.ReadAllText(cachedPath), UpdatePackage.Json);
                        if (cached is not null && UpdateClient.ParseVersion(cached.Version) > UpdateClient.ParseVersion(UpdateClient.CurrentVersion))
                        {
                            UpdateClient.ValidateAsset(cached.Installer, cached.Version, "AI-First-Tools-Setup-" + cached.Version + ".exe");
                            UpdateClient.ValidateAsset(cached.Portable, cached.Version, "AI-First-Tools-Portable-" + cached.Version + "-win-x64.zip");
                            UpdateClient.ValidateAsset(cached.Checksums, cached.Version, "SHA256SUMS.txt");
                            availableUpdate = cached;
                            ShowUpdateOffer();
                            CheckUpdateButton.Content = "有新版本";
                        }
                    }
                    return;
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or System.Text.Json.JsonException or ArgumentException or NullReferenceException) { App.Log(exception); }
        }
        checkingUpdates = true;
        CheckUpdateButton.IsEnabled = false;
        CheckUpdateButton.Content = "检查中…";
        try
        {
            availableUpdate = await updates.CheckAsync(lifetime.Token);
            if (availableUpdate?.Version != preparedVersion) preparedUpdate = null;
            if (released || closing) return;
            if (availableUpdate is not null) ShowUpdateOffer();
            else if (manual) ShowUpdateMessage("已是最新版本 · v" + UpdateClient.CurrentVersion, "以后发布新工具或新版本，这里会提醒您。", "知道了");
            try
            {
                Directory.CreateDirectory(updateSettings);
                File.WriteAllText(Path.Combine(updateSettings, "latest-release.json"), System.Text.Json.JsonSerializer.Serialize(availableUpdate, UpdatePackage.Json));
                File.WriteAllText(timestamp, DateTimeOffset.UtcNow.ToString("O"));
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
        }
        catch (Exception exception)
        {
            if (!released && manual) ShowUpdateMessage("暂时连不上更新服务", "可以继续使用。请检查网络，稍后点击右上角再试。", "知道了");
            if (!released && exception is not OperationCanceledException) App.Log(exception);
        }
        finally
        {
            checkingUpdates = false;
            if (!released)
            {
                CheckUpdateButton.IsEnabled = true;
                CheckUpdateButton.Content = availableUpdate is null ? "检查更新" : "有新版本";
            }
        }
    }

    internal void ShowUpdateOffer(string? explanation = null)
    {
        if (availableUpdate is null) return;
        UpdateTitle.Text = "发现新版本 v" + availableUpdate.Version;
        UpdateDescription.Text = explanation ?? "点一下即可更新全部工具，完成后自动重新打开。原来的对话与设置保留。";
        InstallUpdateButton.Content = "更新并重启";
        InstallUpdateButton.Visibility = Visibility.Visible;
        InstallUpdateButton.IsEnabled = true;
        DismissUpdateButton.Content = "稍后";
        DismissUpdateButton.IsEnabled = true;
        UpdateProgress.Visibility = Visibility.Collapsed;
        UpdateBanner.Visibility = Visibility.Visible;
    }

    private void ShowUpdateMessage(string title, string description, string dismiss)
    {
        UpdateTitle.Text = title;
        UpdateDescription.Text = description;
        InstallUpdateButton.Visibility = Visibility.Collapsed;
        UpdateProgress.Visibility = Visibility.Collapsed;
        DismissUpdateButton.Content = dismiss;
        UpdateBanner.Visibility = Visibility.Visible;
    }

    private void DismissUpdateClick(object sender, RoutedEventArgs args)
    {
        if (downloading is not null) { downloading.Cancel(); return; }
        UpdateBanner.Visibility = Visibility.Collapsed;
    }

    private async void InstallUpdateClick(object sender, RoutedEventArgs args)
    {
        if (availableUpdate is null || downloading is not null || closing || released) return;
        if (preparedUpdate is not null) { restartingForUpdate = true; Close(); return; }
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        downloading = cancellation;
        CheckUpdateButton.IsEnabled = InstallUpdateButton.IsEnabled = false;
        UpdateTitle.Text = "正在下载 v" + availableUpdate.Version;
        UpdateDescription.Text = "下载时可以继续使用。更新前会等待工具安全关闭。";
        DismissUpdateButton.Content = "取消下载";
        UpdateProgress.Visibility = Visibility.Visible;
        UpdateProgress.IsIndeterminate = false;
        UpdateProgress.Value = 0;
        try
        {
            var progress = new Progress<double>(value =>
            {
                if (released || cancellation.IsCancellationRequested || downloading != cancellation) return;
                UpdateProgress.IsIndeterminate = value < 0;
                if (value < 0) { UpdateTitle.Text = "正在校验并准备更新…"; DismissUpdateButton.Content = "取消"; }
                else { UpdateProgress.Value = value; UpdateTitle.Text = "正在下载 · " + Math.Floor(value) + "%"; }
            });
            preparedUpdate = await UpdateRunner.PrepareAsync(updates, availableUpdate, progress, cancellation.Token, updateConfiguration, updateTool);
            preparedVersion = availableUpdate.Version;
            if (released) return;
            if (closing) { ShowUpdateOffer(); return; }
            cancellation.Token.ThrowIfCancellationRequested();
            DismissUpdateButton.IsEnabled = false;
            restartingForUpdate = true;
            Close();
        }
        catch (OperationCanceledException) { if (!released) ShowUpdateOffer("已取消下载，当前版本可以继续使用。"); }
        catch (Exception exception)
        {
            App.Log(exception);
            if (!released) ShowUpdateOffer(exception is InvalidDataException ? exception.Message + " 当前版本可以继续使用。" : "更新准备没有完成，请检查网络、磁盘空间和文件权限后重试。当前版本仍可使用。");
        }
        finally
        {
            downloading = null;
            if (!released) CheckUpdateButton.IsEnabled = true;
        }
    }

    private void ReadUpdateReceipt()
    {
        var path = UpdateRunner.ReceiptPath(AppContext.BaseDirectory);
        if (!File.Exists(path)) return;
        try
        {
            using var receipt = System.Text.Json.JsonDocument.Parse(File.ReadAllText(path));
            if (receipt.RootElement.GetProperty("success").GetBoolean() && receipt.RootElement.GetProperty("version").GetString() == UpdateClient.CurrentVersion)
                ShowUpdateMessage("已更新到 v" + UpdateClient.CurrentVersion, "全部工具已就绪，原来的对话与设置保留。", "知道了");
            File.Delete(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or System.Text.Json.JsonException or KeyNotFoundException or InvalidOperationException) { App.Log(exception); }
    }

    private void UpdateCaption()
    {
        MaximizeGlyph.Data = WindowCaption.MaximizeGeometry(WindowState);
        var action = WindowCaption.MaximizeAction(WindowState);
        MaximizeButton.ToolTip = action;
        System.Windows.Automation.AutomationProperties.SetName(MaximizeButton, action);
    }

    private void MinimizeClick(object sender, RoutedEventArgs args) => WindowState = WindowState.Minimized;
    private void MaximizeClick(object sender, RoutedEventArgs args) => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
    private void WindowCloseClick(object sender, RoutedEventArgs args) => Close();
}
