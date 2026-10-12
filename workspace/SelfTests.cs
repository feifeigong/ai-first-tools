using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace AIFirst.Workspace;

internal static class SelfTests
{
    internal static int Run(string report)
    {
        var root = Path.Combine(Path.GetTempPath(), "ai-first-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        var results = new List<object>();
        var failures = 0;
        void Check(string name, Action test)
        {
            try { test(); results.Add(new { name, passed = true, error = "" }); }
            catch (Exception exception) { failures++; results.Add(new { name, passed = false, error = exception.ToString() }); }
        }
        void Require(bool condition) { if (!condition) throw new InvalidOperationException("Assertion failed"); }
        var executable = Path.Combine(root, "fixture.exe");
        File.WriteAllText(executable, "fixture only; not executable");
        var path = Path.Combine(root, "settings", "tools.json");
        var store = new ToolRepository(path);
        Check("Bundled brand image and multi-size Windows icon load", () => { Require(new BrandAssets(path).Load() is not null); Require(File.Exists(Path.Combine(AppContext.BaseDirectory, "assets", "ai-first-logo.ico"))); });
        Check("Brand wordmark has a compact horizontal layout", () => { var image = (System.Windows.Media.Imaging.BitmapSource)new BrandAssets(path).Load()!; Require(image.PixelWidth > image.PixelHeight * 1.8 && image.PixelWidth < image.PixelHeight * 2.2); });
        Check("Window icon retains multiple size frames including a high resolution frame", () => { var frame = BrandAssets.LoadWindowIcon(); Require(frame.PixelWidth == 256 && frame.Decoder!.Frames.Count >= 7); Require(frame.Decoder.Frames.Any(image => image.PixelWidth == 32)); });
        Check("Windows icon frames have transparent edges and no enclosing tile", () =>
        {
            foreach (var frame in BrandAssets.LoadWindowIcon().Decoder!.Frames)
            {
                var image = new System.Windows.Media.Imaging.FormatConvertedBitmap(frame, System.Windows.Media.PixelFormats.Bgra32, null, 0);
                var stride = image.PixelWidth * 4;
                var pixels = new byte[stride * image.PixelHeight];
                image.CopyPixels(pixels, stride, 0);
                for (var column = 0; column < image.PixelWidth; column++)
                {
                    Require(pixels[column * 4 + 3] == 0);
                    Require(pixels[(image.PixelHeight - 1) * stride + column * 4 + 3] == 0);
                }
                Require(pixels.Where((_, index) => index % 4 == 3).Any(alpha => alpha > 0));
            }
        });
        Check("Maximized caption uses the restore action and a different glyph", () => { Require(WindowCaption.MaximizeAction(System.Windows.WindowState.Normal) == "最大化"); Require(WindowCaption.MaximizeAction(System.Windows.WindowState.Maximized) == "还原窗口"); Require(WindowCaption.MaximizeGeometry(System.Windows.WindowState.Normal) != WindowCaption.MaximizeGeometry(System.Windows.WindowState.Maximized)); });
        Check("Restore and minimized state keep a frozen maximize glyph", () => { Require(WindowCaption.MaximizeGeometry(System.Windows.WindowState.Normal).IsFrozen && WindowCaption.MaximizeGeometry(System.Windows.WindowState.Maximized).IsFrozen); Require(WindowCaption.MaximizeGeometry(System.Windows.WindowState.Normal) == WindowCaption.MaximizeGeometry(System.Windows.WindowState.Minimized)); });
        Check("Builtin default keeps complete package path", () => { var data = store.Load(executable); Require(data.Count == 1 && data[0].BuiltIn && data[0].Embed && data[0].Executable == executable); });
        Check("Custom tools roundtrip using automatic opening without runtime state", () => { var tool = new ToolDefinition { Name = "测试工具", Executable = Path.Combine(root, "second.exe"), Status = "运行中", Embed = false }; store.Save(new[] { tool }); var loaded = store.Load(executable); Require(loaded.Count == 2 && loaded[1].Name == tool.Name && loaded[1].Embed && loaded[1].Status == "点击使用"); Require(!File.ReadAllText(path).Contains("运行中") && !File.ReadAllText(path).Contains("Embed")); });
        Check("Legacy separate-window preference migrates to automatic opening", () => { File.WriteAllText(path, JsonSerializer.Serialize(new[] { new { Id = "legacy", Name = "旧工具", Executable = Path.Combine(root, "old.exe"), Embed = false } })); Require(store.Load(executable)[1].Embed); });
        Check("Duplicate executables are not repeated", () => { store.Save(new[] { new ToolDefinition { Name = "重复工具", Executable = executable } }); Require(store.Load(executable).Count == 1); });
        Check("Registry rejects shell commands and scripts", () => { foreach (var invalid in new[] { "cmd /c echo", "powershell.exe -command test", Path.Combine(root, "test.bat"), "relative.exe" }) { var rejected = false; try { ToolRepository.Validate(new ToolDefinition { Name = "test", Executable = invalid }); } catch (InvalidDataException) { rejected = true; } Require(rejected); } });
        Check("Registry validation does not overwrite good file", () => { store.Save(Array.Empty<ToolDefinition>()); var before = File.ReadAllBytes(path); try { store.Save(new[] { new ToolDefinition { Name = "", Executable = executable } }); } catch (InvalidDataException) { } Require(before.SequenceEqual(File.ReadAllBytes(path))); });
        Check("Corrupt file is preserved for recovery", () => { File.WriteAllText(path, "not JSON"); var before = File.ReadAllBytes(path); try { store.Load(executable); } catch (JsonException) { } Require(before.SequenceEqual(File.ReadAllBytes(path))); });
        Check("Unreadable registry cannot be overwritten by later edits", () => { var before = File.ReadAllBytes(path); var rejected = false; try { store.Save(Array.Empty<ToolDefinition>()); } catch (InvalidDataException) { rejected = true; } Require(rejected && before.SequenceEqual(File.ReadAllBytes(path))); });
        Check("Path matching is case insensitive", () => Require(ToolRepository.SameExecutable(executable, executable.ToUpperInvariant())));
        Check("Separate configuration has separate instance key", () => Require(ToolRepository.ConfigurationKey(path) != ToolRepository.ConfigurationKey(Path.Combine(root, "other.json"))));
        Check("Maximized bounds exclude the bottom taskbar", () =>
        {
            var limits = new NativeMethods.MinMaxInfo { MinTrackSize = new NativeMethods.Point { X = 1100, Y = 740 } };
            NativeMethods.ApplyWorkArea(ref limits, new NativeMethods.Rectangle { Right = 2048, Bottom = 1280 }, new NativeMethods.Rectangle { Right = 2048, Bottom = 1200 });
            Require(limits.MaxPosition.X == 0 && limits.MaxPosition.Y == 0 && limits.MaxSize.X == 2048 && limits.MaxSize.Y == 1200);
            Require(limits.MinTrackSize.X == 1100 && limits.MinTrackSize.Y == 740);
        });
        Check("Maximized bounds handle negative monitor coordinates and a side taskbar", () =>
        {
            var limits = new NativeMethods.MinMaxInfo();
            NativeMethods.ApplyWorkArea(ref limits, new NativeMethods.Rectangle { Left = -1920, Top = -100, Right = 0, Bottom = 980 }, new NativeMethods.Rectangle { Left = -1872, Top = -100, Right = 0, Bottom = 980 });
            Require(limits.MaxPosition.X == 48 && limits.MaxPosition.Y == 0 && limits.MaxSize.X == 1872 && limits.MaxSize.Y == 1080);
        });
        Check("Invalid logo does not overwrite existing brand asset", () => { var logoDirectory = Path.Combine(root, "brand"); Directory.CreateDirectory(logoDirectory); var saved = Path.Combine(logoDirectory, "brand-logo.image"); File.WriteAllText(saved, "existing image placeholder"); var before = File.ReadAllBytes(saved); var rejected = false; try { new BrandAssets(Path.Combine(logoDirectory, "tools.json")).Save(executable); } catch (Exception) { rejected = true; } Require(rejected && before.SequenceEqual(File.ReadAllBytes(saved))); });
        Check("Production catalog contains the packaged suite tool and icon", () =>
        {
            var version = typeof(App).Assembly.GetName().Version!.ToString(2);
            var loaded = ToolCatalog.Load(AppContext.BaseDirectory, version);
            Require(loaded.Count == 1 && loaded[0].Id == "dialog-mover" && loaded[0].BuiltIn && loaded[0].Icon is not null);
            Require(loaded[0].Executable == Path.Combine(AppContext.BaseDirectory, "tools", "dialog-mover-v" + version, "对话搬家.exe"));
        });
        var catalogRoot = Path.Combine(root, "catalog");
        Directory.CreateDirectory(Path.Combine(catalogRoot, "assets"));
        var catalogPath = Path.Combine(catalogRoot, "assets", "tool-catalog.json");
        void Catalog(params ToolCatalog.Entry[] entries) => File.WriteAllText(catalogPath, JsonSerializer.Serialize(entries));
        void RejectCatalog()
        {
            var rejected = false;
            try { ToolCatalog.Load(catalogRoot, "0.3"); } catch (InvalidDataException) { rejected = true; }
            Require(rejected);
        }
        Check("Suite catalog preserves publisher order and resolves versioned paths", () =>
        {
            Catalog(new() { Id = "second", Name = "第二个", Executable = "tools/second-v{version}/second.exe" }, new() { Id = "first", Name = "第一个", Executable = "tools/first.exe" });
            var loaded = ToolCatalog.Load(catalogRoot, "0.3");
            Require(loaded[0].Id == "second" && loaded[1].Id == "first" && loaded[0].Executable.EndsWith(@"tools\second-v0.3\second.exe"));
        });
        Check("Suite catalog ignores legacy user tools without modifying their file", () =>
        {
            var legacyPath = Path.Combine(catalogRoot, "tools.json");
            File.WriteAllText(legacyPath, "legacy registry intentionally not read");
            var before = File.ReadAllBytes(legacyPath);
            Require(ToolCatalog.Load(catalogRoot, "0.3").Count == 2 && before.SequenceEqual(File.ReadAllBytes(legacyPath)));
        });
        Check("Suite catalog rejects paths outside the package and non-executables", () =>
        {
            foreach (var invalid in new[] { executable, @"..\outside.exe", @"tools\..\..\outside.exe", "tools/tool.bat", "cmd /c tool" })
            {
                Catalog(new ToolCatalog.Entry { Id = "test", Name = "测试", Executable = invalid });
                RejectCatalog();
            }
        });
        Check("Suite catalog rejects duplicate identifiers and executables", () =>
        {
            Catalog(new() { Id = "same", Name = "测试1", Executable = "tools/one.exe" }, new() { Id = "SAME", Name = "测试2", Executable = "tools/two.exe" });
            RejectCatalog();
            Catalog(new() { Id = "one", Name = "测试1", Executable = "tools/same.exe" }, new() { Id = "two", Name = "测试2", Executable = "tools/SAME.exe" });
            RejectCatalog();
        });
        Check("Suite catalog rejects empty, null and invalid entries", () =>
        {
            foreach (var invalid in new[] { "[]", "null", "[null]", "[{\"Id\":\"test\",\"Name\":\"测试\",\"Executable\":null}]", "[{}]" })
            {
                File.WriteAllText(catalogPath, invalid);
                RejectCatalog();
            }
        });
        Check("Suite catalog rejects an icon path outside the package", () =>
        {
            Catalog(new ToolCatalog.Entry { Id = "test", Name = "测试", Executable = "tools/test.exe", Icon = "../outside.png" });
            RejectCatalog();
        });
        var preferencesConfig = Path.Combine(root, "preferences", "tools.json");
        var preferences = new WorkspacePreferences(preferencesConfig);
        Check("Sidebar starts expanded and remembers collapsed or expanded state", () =>
        {
            Require(!preferences.LoadCollapsed());
            preferences.SaveCollapsed(true);
            Require(new WorkspacePreferences(preferencesConfig).LoadCollapsed());
            preferences.SaveCollapsed(false);
            Require(!new WorkspacePreferences(preferencesConfig).LoadCollapsed());
        });
        Check("Sidebar preferences do not write the old tool registry", () =>
        {
            File.WriteAllText(preferencesConfig, "preserve old tool registry");
            var before = File.ReadAllBytes(preferencesConfig);
            preferences.SaveCollapsed(true);
            Require(before.SequenceEqual(File.ReadAllBytes(preferencesConfig)));
            Require(!Directory.GetFiles(Path.GetDirectoryName(preferencesConfig)!, "*.tmp").Any());
        });
        var sidebarWindow = new MainWindow(Path.Combine(root, "sidebar-layout", "tools.json"), executable);
        try
        {
            var sidebar = (System.Windows.Controls.Border)sidebarWindow.FindName("ToolSidebar");
            var column = (System.Windows.Controls.ColumnDefinition)sidebarWindow.FindName("SidebarColumn");
            var toggle = (System.Windows.Controls.Button)sidebarWindow.FindName("SidebarToggle");
            Check("Collapsing sidebar removes the entire pane rather than leaving an icon rail", () =>
            {
                sidebarWindow.IsSidebarCollapsed = true;
                Require(column.Width.Value == 0 && sidebar.Visibility == System.Windows.Visibility.Collapsed);
                Require(toggle.Visibility == System.Windows.Visibility.Visible && (string)toggle.ToolTip == "展开工具侧栏");
            });
            Check("Expanding sidebar restores the original pane and action name", () =>
            {
                sidebarWindow.IsSidebarCollapsed = false;
                Require(column.Width.Value == 184 && sidebar.Visibility == System.Windows.Visibility.Visible);
                Require(System.Windows.Automation.AutomationProperties.GetName(toggle) == "收起工具侧栏");
            });
            Check("Sidebar toggle uses keyboard-only focus feedback without persistent focus triggers", () =>
            {
                Require(toggle.FocusVisualStyle == sidebarWindow.FindResource("KeyboardFocus"));
                Require(toggle.Template.Triggers.Count == 0);
            });
            Check("Sidebar icon changes with the actual expanded or hidden pane", () =>
            {
                var pane = (System.Windows.Shapes.Path)sidebarWindow.FindName("SidebarPane");
                sidebarWindow.IsSidebarCollapsed = true;
                Require(pane.Visibility == System.Windows.Visibility.Collapsed);
                sidebarWindow.IsSidebarCollapsed = false;
                Require(pane.Visibility == System.Windows.Visibility.Visible);
            });
        }
        finally { sidebarWindow.ReleaseTools(); }
        Check("Cooperative startup is explicit in the suite catalog and defaults off for legacy tools", () =>
        {
            Catalog(new ToolCatalog.Entry { Id = "prepared", Name = "本机测试", Executable = "tools/prepared.exe", EmbeddedStartup = true });
            Require(ToolCatalog.Load(catalogRoot, "0.3").Single().EmbeddedStartup);
            Catalog(new ToolCatalog.Entry { Id = "legacy", Name = "兼容测试", Executable = "tools/legacy.exe" });
            Require(!ToolCatalog.Load(catalogRoot, "0.3").Single().EmbeddedStartup);
            Require(!new ToolDefinition().EmbeddedStartup);
        });
        Check("Corrupt sidebar preferences fall back without overwriting the original", () =>
        {
            var preferencesPath = Path.Combine(Path.GetDirectoryName(preferencesConfig)!, "workspace-preferences.json");
            foreach (var invalid in new[] { "broken JSON", "null", "{}", "{\"sidebarCollapsed\":\"true\"}" })
            {
                File.WriteAllText(preferencesPath, invalid);
                var before = File.ReadAllBytes(preferencesPath);
                var damaged = new WorkspacePreferences(preferencesConfig);
                Require(!damaged.LoadCollapsed());
                var rejected = false;
                try { damaged.SaveCollapsed(true); } catch (InvalidDataException) { rejected = true; }
                Require(rejected && before.SequenceEqual(File.ReadAllBytes(preferencesPath)));
            }
        });
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(report))!);
        File.WriteAllText(report, JsonSerializer.Serialize(new { passed = results.Count - failures, failed = failures, tests = results }, new JsonSerializerOptions { WriteIndented = true }));
        return failures == 0 ? 0 : 1;
    }
}
