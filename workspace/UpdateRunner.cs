using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;

namespace AIFirst.Workspace;

internal sealed record UpdatePlan(string Target, int ParentId, long ParentStarted, string PreviousVersion, string Version, bool Installed, string PackageName, long PackageSize, string PackageHash, string? Configuration = null, string? Tool = null);

internal static class UpdateRunner
{
    internal static string CacheRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AI一手工具工作台", "updates");
    internal static string InstalledRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "AI First Tools");
    internal const string RegistryKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIFirstTools";
    internal static string GuardName(string target) => "Local\\AI_FIRST_TOOLS_UPDATING_" + ToolRepository.ConfigurationKey(Path.Combine(target, UpdatePackage.AppExecutable));
    internal static string ReceiptPath(string target) => Path.Combine(CacheRoot, "result-" + ToolRepository.ConfigurationKey(Path.Combine(target, UpdatePackage.AppExecutable)) + ".json");

    internal static bool IsUpdating(string target)
    {
        if (!Mutex.TryOpenExisting(GuardName(target), out var guard)) return false;
        guard.Dispose();
        return true;
    }

    internal static bool IsInstalled(string target)
    {
        if (!SameDirectory(target, InstalledRoot)) return false;
        if (File.Exists(Path.Combine(target, "Uninstall.exe"))) return true;
        using var key = Registry.CurrentUser.OpenSubKey(RegistryKey);
        return key?.GetValue("InstallLocation") is string location && SameDirectory(target, location);
    }

    private static bool SameDirectory(string first, string second) => string.Equals(Path.GetFullPath(first).TrimEnd('\\'), Path.GetFullPath(second).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);

    internal static async Task<string> PrepareAsync(UpdateClient client, UpdateRelease release, IProgress<double> progress, CancellationToken cancellation, string? configuration = null, string? tool = null)
    {
        var target = Path.GetFullPath(AppContext.BaseDirectory).TrimEnd('\\');
        var existing = UpdatePackage.Read(target, UpdateClient.CurrentVersion);
        if (UpdateClient.ParseVersion(release.Version) <= UpdateClient.ParseVersion(existing.Version)) throw new InvalidDataException("当前已经是此版本或更新的版本。");
        var job = Path.Combine(CacheRoot, Guid.NewGuid().ToString("N"));
        UpdatePackage.EnsureNoLinks(job);
        Directory.CreateDirectory(job);
        var installed = IsInstalled(target);
        var asset = installed ? release.Installer : release.Portable;
        var package = Path.Combine(job, asset.Name);
        await client.DownloadAsync(release, asset, package, progress, cancellation);
        progress.Report(-1);
        await Task.Run(() =>
        {
            cancellation.ThrowIfCancellationRequested();
            if (!installed) UpdatePackage.Extract(package, Path.Combine(job, "staged"), release.Version, cancellation);
            var runner = Path.Combine(job, "runner");
            Directory.CreateDirectory(runner);
            foreach (var file in existing.Files.Where(IsRunnerFile))
            {
                cancellation.ThrowIfCancellationRequested();
                var source = UpdatePackage.Resolve(target, file.Path);
                UpdatePackage.Verify(source, file.Size, file.Sha256);
                var destination = UpdatePackage.Resolve(runner, file.Path);
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                File.Copy(source, destination);
            }
            using var parent = Process.GetCurrentProcess();
            var plan = new UpdatePlan(target, parent.Id, parent.StartTime.ToUniversalTime().Ticks, existing.Version, release.Version, installed, asset.Name, asset.Size, asset.Digest, configuration, tool);
            File.WriteAllText(Path.Combine(job, "plan.json"), JsonSerializer.Serialize(plan, UpdatePackage.Json));
        }, cancellation);
        return job;
    }

    internal static bool IsRunnerFile(PackageFile file) => file.Path == UpdatePackage.AppExecutable || file.Path == "assets/ai-first-logo.ico" || file.Path.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) && !file.Path.StartsWith("tools/", StringComparison.OrdinalIgnoreCase) || file.Path.EndsWith(".runtimeconfig.json", StringComparison.Ordinal) || file.Path.EndsWith(".deps.json", StringComparison.Ordinal);

    internal static async Task StartAsync(string job)
    {
        var planPath = Path.Combine(job, "plan.json");
        var plan = ValidatePlan(planPath, Path.Combine(job, "runner"));
        if (IsUpdating(plan.Target)) throw new InvalidOperationException("已有更新正在准备，请稍等。");
        var ready = Path.Combine(job, "runner-ready");
        var cancelled = Path.Combine(job, "cancelled");
        if (File.Exists(ready)) File.Delete(ready);
        if (File.Exists(cancelled)) File.Delete(cancelled);
        var start = new ProcessStartInfo(UpdatePackage.Resolve(Path.Combine(job, "runner"), UpdatePackage.AppExecutable)) { UseShellExecute = false, WorkingDirectory = job, WindowStyle = ProcessWindowStyle.Hidden };
        start.ArgumentList.Add("--apply-update");
        start.ArgumentList.Add(Path.Combine(job, "plan.json"));
        using var runner = Process.Start(start) ?? throw new InvalidOperationException("没有启动更新，请再试一次。");
        for (var attempt = 0; attempt < 300; attempt++)
        {
            if (runner.HasExited) throw new InvalidOperationException("更新未能启动，当前版本可以继续使用。");
            if (File.Exists(ready)) return;
            await Task.Delay(100);
        }
        File.WriteAllText(cancelled, "cancelled");
        throw new TimeoutException("准备更新用时较长，请等片刻再试。");
    }

    internal static UpdatePlan ValidatePlan(string planPath, string runnerDirectory)
    {
        var path = Path.GetFullPath(planPath);
        var job = Path.GetDirectoryName(path)!;
        if (!SameDirectory(Path.GetDirectoryName(job)!, CacheRoot) || !Regex.IsMatch(Path.GetFileName(job), "^[a-f0-9]{32}$") || Path.GetFileName(path) != "plan.json" || !SameDirectory(runnerDirectory, Path.Combine(job, "runner"))) throw new InvalidDataException("更新必须由工作台发起。");
        UpdatePackage.EnsureNoLinks(path);
        if (new FileInfo(path).Length > 16384) throw new InvalidDataException("更新指令无效。");
        var plan = JsonSerializer.Deserialize<UpdatePlan>(File.ReadAllText(path), UpdatePackage.Json) ?? throw new InvalidDataException("更新指令无效。");
        if (!Path.IsPathFullyQualified(plan.Target) || plan.ParentId <= 0 || plan.ParentStarted <= 0 || plan.PreviousVersion != UpdateClient.CurrentVersion || UpdateClient.ParseVersion(plan.Version) <= UpdateClient.ParseVersion(plan.PreviousVersion)) throw new InvalidDataException("更新版本或目标无效。");
        UpdatePackage.EnsureNoLinks(plan.Target);
        UpdatePackage.Read(plan.Target, plan.PreviousVersion);
        CheckExecutableVersion(plan.Target, plan.PreviousVersion);
        if (!File.Exists(UpdatePackage.Resolve(plan.Target, UpdatePackage.AppExecutable)) || plan.Installed != IsInstalled(plan.Target)) throw new InvalidDataException("工作台位置已改变，请重新下载更新。");
        var name = plan.Installed ? "AI-First-Tools-Setup-" + plan.Version + ".exe" : "AI-First-Tools-Portable-" + plan.Version + "-win-x64.zip";
        UpdateClient.ValidateAsset(new UpdateAsset(plan.PackageName, UpdateClient.Repository + "/releases/download/v" + plan.Version + "/" + plan.PackageName, plan.PackageSize, plan.PackageHash), plan.Version, name);
        UpdatePackage.Verify(UpdatePackage.Resolve(job, name), plan.PackageSize, plan.PackageHash);
        if (plan.Configuration is not null && !Path.IsPathFullyQualified(plan.Configuration)) throw new InvalidDataException("开发配置位置无效。");
        if (plan.Tool is not null) ToolRepository.Validate(new ToolDefinition { Name = "更新后的工具", Executable = plan.Tool });
        return plan;
    }

    private static void CheckExecutableVersion(string target, string expected)
    {
        var information = FileVersionInfo.GetVersionInfo(UpdatePackage.Resolve(target, UpdatePackage.AppExecutable));
        if (new Version(information.FileMajorPart, information.FileMinorPart, information.FileBuildPart) != UpdateClient.ParseVersion(expected)) throw new InvalidDataException("程序版本没有完整更新。");
    }

    internal static async Task<int> RunAsync(string planPath)
    {
        UpdatePlan? plan = null;
        Window? window = null;
        Mutex? guard = null;
        var parentExited = false;
        try
        {
            plan = ValidatePlan(planPath, AppContext.BaseDirectory);
            guard = new Mutex(false, GuardName(plan.Target), out var isNew);
            if (!isNew) throw new InvalidOperationException("已有更新正在进行。");
            using var parent = Process.GetProcessById(plan.ParentId);
            if (parent.StartTime.ToUniversalTime().Ticks != plan.ParentStarted || !SameDirectory(Path.GetDirectoryName(parent.MainModule!.FileName)!, plan.Target)) throw new InvalidDataException("发起更新的工作台不匹配。");
            var job = Path.GetDirectoryName(planPath)!;
            File.WriteAllText(Path.Combine(job, "runner-ready"), "ready");
            var deadline = DateTime.UtcNow.AddMinutes(2);
            while (!parent.HasExited)
            {
                if (File.Exists(Path.Combine(job, "cancelled"))) return 2;
                if (DateTime.UtcNow >= deadline) throw new TimeoutException("工作台尚未关闭，本次更新已停止。");
                await Task.Delay(100);
            }
            parentExited = true;
            window = ProgressWindow();
            window.Show();
            await Task.Run(async () =>
            {
                await AutoResumeRuntime.PrepareAsync(plan.Target);
                await WaitForFilesAsync(plan.Target);
                var backup = Path.Combine(job, "backup");
                if (plan.Installed)
                {
                    if (Mutex.TryOpenExisting("Local\\AI_FIRST_TOOLS_RUNNING", out var running))
                    {
                        running.Dispose();
                        throw new InvalidOperationException("请先关闭其他工作台窗口，再更新。");
                    }
                    var old = UpdatePackage.Read(plan.Target, plan.PreviousVersion);
                    UpdatePackage.Backup(plan.Target, backup, old.Files.Select(file => file.Path).Append(UpdatePackage.ManifestName).Append("Uninstall.exe"));
                    try
                    {
                        var start = new ProcessStartInfo(UpdatePackage.Resolve(job, plan.PackageName)) { UseShellExecute = false, WorkingDirectory = job };
                        start.ArgumentList.Add("/S");
                        using var installer = Process.Start(start) ?? throw new InvalidOperationException("没有启动安装程序。");
                        await installer.WaitForExitAsync();
                        if (installer.ExitCode != 0) throw new InvalidOperationException("安装未完成，请关闭其他工作台窗口后重试。");
                        var installedManifest = UpdatePackage.Read(plan.Target, plan.Version);
                        CheckExecutableVersion(plan.Target, plan.Version);
                        var newFiles = installedManifest.Files.Select(file => file.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
                        foreach (var file in old.Files.Where(file => !newFiles.Contains(file.Path)))
                        {
                            var path = UpdatePackage.Resolve(plan.Target, file.Path);
                            if (!File.Exists(path)) continue;
                            try { UpdatePackage.Verify(path, file.Size, file.Sha256); }
                            catch (InvalidDataException) { continue; }
                            File.Delete(path);
                        }
                    }
                    catch
                    {
                        await AutoResumeRuntime.PrepareAsync(plan.Target);
                        var paths = old.Files.Select(file => file.Path).Append(UpdatePackage.ManifestName).Append("Uninstall.exe");
                        UpdatePackage.Restore(plan.Target, backup, paths);
                        using var key = Registry.CurrentUser.OpenSubKey(RegistryKey, true);
                        key?.SetValue("DisplayVersion", plan.PreviousVersion);
                        throw;
                    }
                }
                else
                {
                    var staged = Path.Combine(job, "staged");
                    UpdatePackage.Read(staged, plan.Version);
                    CheckExecutableVersion(staged, plan.Version);
                    var written = UpdatePackage.Apply(plan.Target, staged, backup);
                    try { CheckExecutableVersion(plan.Target, plan.Version); }
                    catch { UpdatePackage.Restore(plan.Target, backup, written); throw; }
                }
            });
            File.WriteAllText(ReceiptPath(plan.Target), JsonSerializer.Serialize(new { version = plan.Version, success = true }, UpdatePackage.Json));
            File.WriteAllText(Path.Combine(job, "completed"), DateTimeOffset.UtcNow.ToString("O"));
            await Task.Run(() => RemoveTemporaryFiles(job));
            if (window is not null)
            {
                window.Closing -= (CancelEventHandler)window.Tag;
                window.Close();
                window = null;
            }
            guard.Dispose();
            guard = null;
            OpenWorkbench(plan);
            return 0;
        }
        catch (Exception exception)
        {
            App.Log(exception);
            guard?.Dispose();
            guard = null;
            MessageBox.Show("这次更新没有完成，未操作任何对话记录。\n" + exception.Message + "\n请重新打开工作台后再试。", "AI一手 · 更新", MessageBoxButton.OK, MessageBoxImage.Information);
            if (plan is not null && parentExited)
            {
                try { CheckExecutableVersion(plan.Target, plan.PreviousVersion); OpenWorkbench(plan); }
                catch (Exception restartError) { App.Log(restartError); }
            }
            return 1;
        }
        finally
        {
            guard?.Dispose();
            if (window is not null)
            {
                window.Closing -= (CancelEventHandler)window.Tag;
                window.Close();
            }
        }
    }

    private static void OpenWorkbench(UpdatePlan plan)
    {
        var start = new ProcessStartInfo(UpdatePackage.Resolve(plan.Target, UpdatePackage.AppExecutable)) { UseShellExecute = false, WorkingDirectory = plan.Target };
        if (plan.Configuration is not null) { start.ArgumentList.Add("--config"); start.ArgumentList.Add(plan.Configuration); }
        if (plan.Tool is not null) { start.ArgumentList.Add("--tool"); start.ArgumentList.Add(plan.Tool); }
        Process.Start(start);
    }

    private static async Task WaitForFilesAsync(string target)
    {
        var deadline = DateTime.UtcNow.AddSeconds(15);
        var files = UpdatePackage.Read(target).Files.Where(file => file.Path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || file.Path.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)).ToArray();
        while (true)
        {
            try
            {
                foreach (var file in files)
                {
                    var path = UpdatePackage.Resolve(target, file.Path);
                    if (!File.Exists(path)) continue;
                    using var unlocked = File.Open(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
                }
                return;
            }
            catch (IOException) when (DateTime.UtcNow < deadline) { await Task.Delay(250); }
        }
    }

    internal static void CleanupCompletedJobs()
    {
        if (!Directory.Exists(CacheRoot)) return;
        try
        {
            UpdatePackage.EnsureNoLinks(CacheRoot);
            foreach (var job in Directory.GetDirectories(CacheRoot))
            {
                if (!Regex.IsMatch(Path.GetFileName(job), "^[a-f0-9]{32}$")) continue;
                var completed = Path.Combine(job, "completed");
                if (!File.Exists(completed) || DateTime.UtcNow - File.GetLastWriteTimeUtc(completed) < TimeSpan.FromMinutes(5)) continue;
                try { DeleteCacheTree(job); }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
    }

    private static void DeleteCacheTree(string directory)
    {
        var path = Path.GetFullPath(directory);
        if (!path.StartsWith(Path.GetFullPath(CacheRoot).TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("更新清理超出了缓存目录。");
        UpdatePackage.EnsureNoLinks(path);
        foreach (var child in Directory.GetDirectories(path)) DeleteCacheTree(child);
        foreach (var file in Directory.GetFiles(path)) { UpdatePackage.EnsureNoLinks(file); File.Delete(file); }
        Directory.Delete(path);
    }

    private static void RemoveTemporaryFiles(string job)
    {
        try
        {
            UpdatePackage.EnsureNoLinks(job);
            foreach (var name in new[] { "staged", "backup" })
            {
                var directory = UpdatePackage.Resolve(job, name);
                if (!Directory.Exists(directory)) continue;
                DeleteCacheTree(directory);
            }
            foreach (var file in Directory.GetFiles(job).Where(path => path.EndsWith(".zip", StringComparison.OrdinalIgnoreCase) || path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))) File.Delete(file);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { App.Log(exception); }
    }

    private static Window ProgressWindow()
    {
        var panel = new StackPanel { Margin = new Thickness(28) };
        panel.Children.Add(new TextBlock { Text = "正在更新工具工作台", FontSize = 20, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = "完成后自动重新打开，请稍等…", Margin = new Thickness(0, 10, 0, 20), FontSize = 13 });
        panel.Children.Add(new ProgressBar { Height = 4, IsIndeterminate = true });
        var window = new Window { Title = "AI一手工具工作台", Icon = BrandAssets.LoadWindowIcon(), Content = panel, Width = 420, Height = 200, ResizeMode = ResizeMode.NoResize, WindowStartupLocation = WindowStartupLocation.CenterScreen, FontFamily = new System.Windows.Media.FontFamily("Microsoft YaHei UI") };
        CancelEventHandler closing = (_, args) => args.Cancel = true;
        window.Closing += closing;
        window.Tag = closing;
        return window;
    }
}
