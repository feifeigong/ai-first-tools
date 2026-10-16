using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;

namespace AIFirst.Workspace;

public partial class AutoResumePage : UserControl, IDisposable
{
    private readonly IAutoResumeControl control;
    private readonly CancellationTokenSource lifetime = new();
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(30) };
    private AutoResumeStatus? status;
    private bool disposed;
    internal bool IsBusy { get; private set; }

    public AutoResumePage() : this(new AutoResumeControl()) { }
    internal AutoResumePage(IAutoResumeControl control)
    {
        this.control = control;
        InitializeComponent();
        timer.Tick += async (_, _) => { if (IsVisible) await RefreshAsync(); };
        IsVisibleChanged += async (_, _) => { if (IsVisible) await RefreshAsync(); };
        timer.Start();
    }

    internal static ImageSource CreateIcon()
    {
        var group = new DrawingGroup();
        group.Children.Add(new GeometryDrawing(new SolidColorBrush(Color.FromRgb(231, 241, 252)), null, new RectangleGeometry(new Rect(0, 0, 28, 28), 7, 7)));
        var pen = new Pen(new SolidColorBrush(Color.FromRgb(0, 115, 230)), 1.8) { StartLineCap = PenLineCap.Round, EndLineCap = PenLineCap.Round, LineJoin = PenLineJoin.Round };
        group.Children.Add(new GeometryDrawing(null, pen, Geometry.Parse("M20,10 A7,7 0 0 0 7,11 M7,7 V11 H11 M8,18 A7,7 0 0 0 21,17 M21,21 V17 H17")));
        var image = new DrawingImage(group); image.Freeze(); return image;
    }

    internal Task RefreshAsync() => ExecuteAsync("status");
    private async void RefreshClick(object sender, RoutedEventArgs args) => await RefreshAsync();
    private async void RunningClick(object sender, RoutedEventArgs args) => await ExecuteAsync(RunningSwitch.IsChecked == true ? "start" : "stop");
    private async void AutostartClick(object sender, RoutedEventArgs args) => await ExecuteAsync(AutostartSwitch.IsChecked == true ? "autostart-on" : "autostart-off");

    private async Task ExecuteAsync(string action)
    {
        if (IsBusy || disposed) return;
        IsBusy = true;
        RunningSwitch.IsEnabled = AutostartSwitch.IsEnabled = RefreshButton.IsEnabled = false;
        if (action != "status") StateTitle.Text = action == "stop" ? "正在关闭…" : action == "start" ? "正在开启…" : "正在保存开机设置…";
        try
        {
            status = await control.ExecuteAsync(action, lifetime.Token);
            if (disposed) return;
            PaintStatus(status);
            MessageCard.Visibility = Visibility.Collapsed;
        }
        catch (OperationCanceledException) { }
        catch (Exception exception)
        {
            if (disposed) return;
            // A failed mutation may have partially succeeded. Do not display cached switches as current.
            status = null;
            RunningSwitch.IsChecked = AutostartSwitch.IsChecked = false;
            StateTitle.Text = "状态暂时无法确认";
            StateDescription.Text = "请刷新确认。开关恢复可用前不会继续操作。";
            MessageText.Text = exception.Message;
            MessageCard.Visibility = Visibility.Visible;
        }
        finally
        {
            IsBusy = false;
            if (!disposed)
            {
                RefreshButton.IsEnabled = true;
                RunningSwitch.IsEnabled = AutostartSwitch.IsEnabled = status?.Installed == true;
            }
        }
    }

    private void PaintStatus(AutoResumeStatus value)
    {
        RunningSwitch.IsChecked = value.Running;
        AutostartSwitch.IsChecked = value.Autostart;
        StateTitle.Text = !value.Installed ? "没有找到已安装的续跑程序" : value.Running ? "自动续跑已开启" : "自动续跑已关闭";
        StateDescription.Text = !value.Installed ? "请先安装 Codex Auto Resume，再回来刷新状态。" : value.Running ? "后台程序正在运行，额度恢复后会按现有配置继续原对话。" : value.Autostart ? "当前没有运行；下次登录电脑会自动开启。" : "后台程序没有运行，开机也不会自动开启。";
        StateCard.Background = new SolidColorBrush(value.Running ? Color.FromRgb(239, 248, 244) : Color.FromRgb(243, 247, 252));
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        timer.Stop();
        lifetime.Cancel();
        lifetime.Dispose();
    }
}
