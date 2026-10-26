using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows;

namespace AIFirst.Workspace;

public partial class App : Application
{
    internal static bool IsDevelopmentPreview => File.Exists(Path.Combine(AppContext.BaseDirectory, "development-preview.json"));
    private Mutex? instance;
    private Mutex? installationGuard;
    private InstanceActivation? activation;

    protected override async void OnStartup(StartupEventArgs args)
    {
        base.OnStartup(args);
        if (args.Args.Contains("--reset-monitor"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            try
            {
                using var service = new ResetNewsService();
                Shutdown(await ResetMonitorHost.RunAsync(service, new AutoResumeControl()));
            }
            catch (Exception exception) { Log(exception); Shutdown(1); }
            return;
        }
        if (args.Args.Contains("--render-reset-ui"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var output = Option(args.Args, "--render-reset-ui");
            Shutdown(output is null ? 2 : ResetVisualTests.Render(output));
            return;
        }
        if (args.Args.Contains("--check-public-reset-feed"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var output = Option(args.Args, "--check-public-reset-feed");
            Shutdown(output is null ? 2 : await ResetPublicCheck.RunAsync(output));
            return;
        }
        if (args.Args.Contains("--update-handoff-test"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var fixtureDirectory = Option(args.Args, "--update-fixture");
            var report = Option(args.Args, "--report");
            var config = Option(args.Args, "--config");
            if (fixtureDirectory is null || report is null || config is null) { Shutdown(2); return; }
            try { await UpdateSelfTests.HandoffAsync(fixtureDirectory, config, report); Shutdown(); }
            catch (Exception exception) { Log(exception); File.WriteAllText(report, exception.ToString()); Shutdown(1); }
            return;
        }
        if (args.Args.Contains("--apply-update"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var plan = Option(args.Args, "--apply-update");
            Shutdown(plan is null ? 2 : await UpdateRunner.RunAsync(plan));
            return;
        }
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
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var report = Option(args.Args, "--report") ?? Path.Combine(AppContext.BaseDirectory, "self-test.json");
            var code = SelfTests.Run(report);
            Shutdown(code);
            return;
        }
        if (UpdateRunner.IsUpdating(AppContext.BaseDirectory))
        {
            if (!await InstanceActivation.ShowExistingAsync(UpdateRunner.ActivationKey(AppContext.BaseDirectory)))
                MessageBox.Show("正在更新，完成后会自动打开，请在更新窗口查看当前步骤和已用时间。", "AI一手", MessageBoxButton.OK, MessageBoxImage.Information);
            Shutdown();
            return;
        }
        var configuration = Option(args.Args, "--config") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI一手工具工作台", IsDevelopmentPreview ? "memory-preview" : "", "tools.json");
        if (IsDevelopmentPreview)
            Environment.SetEnvironmentVariable("AI_FIRST_MOVER_PREVIEW_DATA", Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI一手工具工作台", "memory-preview", "mover"));
        var key = ToolRepository.ConfigurationKey(configuration);
        instance = new Mutex(true, "Local\\AI_FIRST_TOOL_WORKSPACE_" + key, out var isNew);
        if (!isNew)
        {
            if (!await InstanceActivation.ShowExistingAsync(key)) MessageBox.Show("工作台还在打开，请稍等一下。", "AI一手", MessageBoxButton.OK, MessageBoxImage.Information);
            Shutdown();
            return;
        }
        installationGuard = new Mutex(false, "Local\\AI_FIRST_TOOLS_RUNNING");
        var selection = ResolveToolSelection(args.Args);
        MainWindow window;
        var updateFixture = Option(args.Args, "--update-fixture");
        if (updateFixture is not null)
        {
            if (Option(args.Args, "--config") is null || UpdateRunner.IsInstalled(AppContext.BaseDirectory)) { Shutdown(2); return; }
            window = new MainWindow(configuration, selection.Executable, Option(args.Args, "--health-report"), true, UpdateSelfTests.FixtureClient(updateFixture));
        }
        else window = new MainWindow(configuration, selection.Executable, Option(args.Args, "--health-report"), Option(args.Args, "--config") is not null);
        window.InitialToolId = selection.Page;
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
        try { if (!IsDevelopmentPreview) await AutoResumeRuntime.RestoreAsync(AppContext.BaseDirectory); }
        catch (Exception exception) { Log(exception); window.ShowStatus("后台续跑暂未恢复，请打开“Codex 自动续跑”后重新开启。"); }
    }

    internal static string? Option(string[] arguments, string name)
    {
        var position = Array.IndexOf(arguments, name);
        return position >= 0 && position + 1 < arguments.Length ? arguments[position + 1] : null;
    }

    internal static (string? Executable, string? Page) ResolveToolSelection(string[] arguments)
    {
        var executable = Option(arguments, "--tool");
        var page = Option(arguments, "--page");
        // Built-in IDs select catalog pages. Only executable paths override a tool.
        if (executable is "dialog-mover" or "auto-resume")
        {
            page ??= executable;
            executable = null;
        }
        return (executable, page);
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
