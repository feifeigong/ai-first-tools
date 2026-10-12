using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows;

namespace AIFirst.Workspace;

public partial class App : Application
{
    private Mutex? instance;
    private Mutex? installationGuard;
    private InstanceActivation? activation;

    protected override async void OnStartup(StartupEventArgs args)
    {
        base.OnStartup(args);
        if (args.Args.Contains("--native-self-test"))
        {
            var report = Option(args.Args, "--report") ?? Path.Combine(AppContext.BaseDirectory, "native-test.json");
            var fixture = Option(args.Args, "--fixture");
            if (fixture is null) { Shutdown(2); return; }
            Shutdown(await NativeSelfTests.Run(fixture, report));
            return;
        }
        if (args.Args.Contains("--self-test"))
        {
            var report = Option(args.Args, "--report") ?? Path.Combine(AppContext.BaseDirectory, "self-test.json");
            var code = SelfTests.Run(report);
            Shutdown(code);
            return;
        }
        var configuration = Option(args.Args, "--config") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI一手工具工作台", "tools.json");
        var key = ToolRepository.ConfigurationKey(configuration);
        instance = new Mutex(true, "Local\\AI_FIRST_TOOL_WORKSPACE_" + key, out var isNew);
        if (!isNew)
        {
            if (!await InstanceActivation.ShowExistingAsync(key)) MessageBox.Show("工作台还在打开，请稍等一下。", "AI一手", MessageBoxButton.OK, MessageBoxImage.Information);
            Shutdown();
            return;
        }
        installationGuard = new Mutex(false, "Local\\AI_FIRST_TOOLS_RUNNING");
        var window = new MainWindow(configuration, Option(args.Args, "--tool"), Option(args.Args, "--health-report"), Option(args.Args, "--config") is not null);
        MainWindow = window;
        activation = new InstanceActivation(key, () => Dispatcher.BeginInvoke(() =>
        {
            window.Show();
            if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
            window.Activate();
            NativeMethods.SetForegroundWindow(new System.Windows.Interop.WindowInteropHelper(window).Handle);
        }));
        DispatcherUnhandledException += (_, error) =>
        {
            window.ReleaseTools();
            Log(error.Exception);
            MessageBox.Show("工作台遇到了异常。已打开的工具会恢复为独立窗口，不会强行停止任务。", "AI一手工具工作台", MessageBoxButton.OK, MessageBoxImage.Warning);
            error.Handled = true;
            Shutdown(1);
        };
        window.Show();
    }

    internal static string? Option(string[] arguments, string name)
    {
        var position = Array.IndexOf(arguments, name);
        return position >= 0 && position + 1 < arguments.Length ? arguments[position + 1] : null;
    }

    internal static void Log(Exception exception)
    {
        try
        {
            var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI一手工具工作台");
            Directory.CreateDirectory(directory);
            File.AppendAllText(Path.Combine(directory, "errors.log"), DateTimeOffset.Now.ToString("u") + " " + exception + Environment.NewLine);
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    protected override void OnExit(ExitEventArgs args)
    {
        activation?.Dispose();
        if (MainWindow is MainWindow window) window.ReleaseTools();
        instance?.Dispose();
        installationGuard?.Dispose();
        base.OnExit(args);
    }
}
