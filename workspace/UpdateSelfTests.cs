using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal static class UpdateSelfTests
{
    internal static async Task HandoffAsync(string fixtureDirectory, string configuration, string report)
    {
        var existing = UpdatePackage.Read(AppContext.BaseDirectory, UpdateClient.CurrentVersion);
        if (UpdateRunner.IsInstalled(AppContext.BaseDirectory) || !existing.Files.Any(file => file.Path.EndsWith("/WorkspaceWindowFixture.dll", StringComparison.Ordinal))) throw new InvalidDataException("更新交接测试仅允许隔离的 WindowFixture 工具包。");
        using var client = FixtureClient(fixtureDirectory);
        var release = await client.CheckAsync(CancellationToken.None) ?? throw new InvalidDataException("隔离测试包没有更高版本。");
        var job = await UpdateRunner.PrepareAsync(client, release, new Progress<double>(), CancellationToken.None, configuration);
        await UpdateRunner.StartAsync(job);
        File.WriteAllText(report, JsonSerializer.Serialize(new { handedOff = true, job, target = AppContext.BaseDirectory, previousVersion = existing.Version, version = release.Version }, UpdatePackage.Json));
    }

    internal static UpdateClient FixtureClient(string directory)
    {
        var manifest = UpdatePackage.Read(directory);
        var version = manifest.Version;
        var files = new Dictionary<string, string>
        {
            ["AI-First-Tools-Setup-" + version + ".exe"] = Path.Combine(directory, "..", "fixture-setup.exe"),
            ["AI-First-Tools-Portable-" + version + "-win-x64.zip"] = Path.Combine(directory, "..", "fixture-portable.zip"),
            ["SHA256SUMS.txt"] = Path.Combine(directory, "..", "fixture-checksums.txt")
        };
        var metadata = new[] { new { tag_name = "v" + version, published_at = "2026-10-12T00:00:00Z", draft = false, prerelease = true, assets = files.Select(entry =>
        {
            using var stream = File.OpenRead(entry.Value);
            return new { name = entry.Key, state = "uploaded", browser_download_url = UpdateClient.Repository + "/releases/download/v" + version + "/" + entry.Key, size = new FileInfo(entry.Value).Length, digest = "sha256:" + Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant() };
        }).ToArray() } };
        return new UpdateClient(new FakeHttp(address =>
        {
            if (address == UpdateClient.ReleasesApi) return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(metadata)) };
            var name = Path.GetFileName(new Uri(address).AbsolutePath);
            return files.TryGetValue(name, out var path) ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(File.OpenRead(path)) } : new HttpResponseMessage(HttpStatusCode.NotFound);
        }));
    }

    internal static void Run(Action<string, Action> check, Action<bool> require, string root)
    {
        string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var digest = Hash(Encoding.UTF8.GetBytes("fixture"));
        object Release(string version, bool draft = false, bool preview = false, bool incomplete = false, string? source = null)
        {
            var names = new[] { "AI-First-Tools-Setup-" + version + ".exe", "AI-First-Tools-Portable-" + version + "-win-x64.zip", "SHA256SUMS.txt" };
            return new { tag_name = "v" + version, published_at = "2026-10-12T00:00:00Z", draft, prerelease = preview, assets = names.Take(incomplete ? 2 : 3).Select(name => new { name, state = "uploaded", browser_download_url = (source ?? UpdateClient.Repository) + "/releases/download/v" + version + "/" + name, size = 7, digest = "sha256:" + digest }) };
        }
        UpdateRelease? Select(params object[] releases) => UpdateClient.SelectRelease(JsonSerializer.Serialize(releases), "0.3.7");
        void Reject(Action action)
        {
            var rejected = false;
            try { action(); }
            catch (Exception exception) when (exception is InvalidDataException or ArgumentException or IOException or JsonException) { rejected = true; }
            require(rejected);
        }
        check("Updater compares numeric versions instead of text order", () => require(Select(Release("0.3.8"), Release("0.3.10"))?.Version == "0.3.10"));
        check("Updater detects published preview releases as well as stable releases", () => require(Select(Release("0.3.8", preview: true))?.Version == "0.3.8"));
        check("Updater ignores drafts, same versions, older versions and incomplete uploads", () => require(Select(Release("0.3.6"), Release("0.3.7"), Release("0.3.9", draft: true), Release("0.3.10", incomplete: true)) is null));
        check("Updater rejects release assets from another repository", () => require(Select(Release("0.3.8", source: "https://github.com/other/project")) is null));
        check("Updater skips malformed tags and missing release properties", () => require(Select(Release("1.0.0-beta.1"), Release("00.3.9"), new { tag_name = (string?)null, draft = false, published_at = "today" }) is null));
        check("Updater rejects non-array metadata without installing anything", () => Reject(() => UpdateClient.SelectRelease("{}", "0.3.7")));
        check("Updater ignores duplicate assets and missing SHA256 digests", () =>
        {
            var release = JsonSerializer.SerializeToNode(Release("0.3.8"))!;
            var assets = release["assets"]!.AsArray();
            assets.Add(assets[0]!.DeepClone());
            require(UpdateClient.SelectRelease("[" + release.ToJsonString() + "]", "0.3.7") is null);
            assets.RemoveAt(3);
            assets[0]!["digest"] = null;
            require(UpdateClient.SelectRelease("[" + release.ToJsonString() + "]", "0.3.7") is null);
        });
        check("Updater only follows HTTPS GitHub release download redirects", () =>
        {
            require(UpdateClient.AllowedAddress(new Uri("https://release-assets.githubusercontent.com/file?token=fixture"), true));
            foreach (var address in new[] { "http://github.com/feifeigong/ai-first-tools/releases/download/test", "https://evil.example/file", "https://github.com:8443/feifeigong/ai-first-tools/releases/download/test", "https://user:password@github.com/feifeigong/ai-first-tools/releases/download/test", "https://github.com/other/project/releases/download/test" }) require(!UpdateClient.AllowedAddress(new Uri(address), true));
        });
        check("Updater verifies checksum names and values without accepting duplicates", () =>
        {
            var asset = new UpdateAsset("fixture.zip", "", 7, digest);
            UpdateClient.ValidateChecksums(digest + "  fixture.zip\r\n", asset);
            Reject(() => UpdateClient.ValidateChecksums(digest + "  another.zip", asset));
            Reject(() => UpdateClient.ValidateChecksums(digest + "  fixture.zip\n" + digest + "  fixture.zip", asset));
        });
        var downloads = Path.Combine(root, "update-downloads");
        Directory.CreateDirectory(downloads);
        var payload = Encoding.UTF8.GetBytes("synthetic release payload");
        var version = "0.3.8";
        var portableName = "AI-First-Tools-Portable-" + version + "-win-x64.zip";
        var setupName = "AI-First-Tools-Setup-" + version + ".exe";
        var payloadHash = Hash(payload);
        var checksumBytes = Encoding.UTF8.GetBytes(payloadHash + "  " + portableName + "\n" + payloadHash + "  " + setupName + "\n");
        UpdateAsset Asset(string name, byte[] bytes) => new(name, UpdateClient.Repository + "/releases/download/v" + version + "/" + name, bytes.Length, Hash(bytes));
        var downloadable = new UpdateRelease(version, Asset(setupName, payload), Asset(portableName, payload), Asset("SHA256SUMS.txt", checksumBytes));
        FakeHttp Handler(byte[] data) => new(address => new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(address.EndsWith("SHA256SUMS.txt", StringComparison.Ordinal) ? checksumBytes : data) });
        void Download(UpdateClient client, string filename, CancellationToken cancellation = default) => Task.Run(() => client.DownloadAsync(downloadable, downloadable.Portable, Path.Combine(downloads, filename), null, cancellation)).GetAwaiter().GetResult();
        check("Updater streams and verifies both checksum file and downloaded package", () =>
        {
            using var client = new UpdateClient(Handler(payload));
            Download(client, "good.zip");
            require(File.ReadAllBytes(Path.Combine(downloads, "good.zip")).SequenceEqual(payload));
        });
        check("Updater removes a partial download after a size or hash mismatch", () =>
        {
            using var client = new UpdateClient(Handler(new byte[payload.Length]));
            Reject(() => Download(client, "bad.zip"));
            require(!File.Exists(Path.Combine(downloads, "bad.zip")) && !File.Exists(Path.Combine(downloads, "bad.zip.partial")));
            using var shortClient = new UpdateClient(Handler(payload[..^1]));
            Reject(() => Download(shortClient, "short.zip"));
        });
        check("Updater does not trust a tampered checksum file", () =>
        {
            using var client = new UpdateClient(new FakeHttp(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[checksumBytes.Length]) }));
            Reject(() => Download(client, "checksums-tampered.zip"));
        });
        check("Updater cancellation never leaves an installable package", () =>
        {
            using var cancelled = new CancellationTokenSource();
            cancelled.Cancel();
            using var client = new UpdateClient(Handler(payload));
            var stopped = false;
            try { Download(client, "cancelled.zip", cancelled.Token); } catch (OperationCanceledException) { stopped = true; }
            require(stopped && !File.Exists(Path.Combine(downloads, "cancelled.zip")));
        });
        check("Updater refuses a redirect to an unrelated download host", () =>
        {
            using var client = new UpdateClient(new FakeHttp(_ => new HttpResponseMessage(HttpStatusCode.Found) { Headers = { Location = new Uri("https://evil.example/download") } }));
            Reject(() => Download(client, "redirect.zip"));
        });
        check("Updater reports unavailable and rate limited metadata without downloading", () =>
        {
            using var client = new UpdateClient(new FakeHttp(_ => new HttpResponseMessage(HttpStatusCode.Forbidden)));
            var rejected = false;
            try { Task.Run(() => client.CheckAsync(CancellationToken.None)).GetAwaiter().GetResult(); } catch (HttpRequestException) { rejected = true; }
            require(rejected);
        });
        check("Automatic checks repeat after ten minutes and wake checks are throttled", () =>
        {
            var now = DateTimeOffset.UtcNow;
            var schedule = new UpdateCheckSchedule();
            require(schedule.IsDue(now));
            schedule.Started(now); schedule.Succeeded(now);
            require(!schedule.IsDue(now.AddMinutes(9)) && schedule.IsDue(now.AddMinutes(10)));
            require(!schedule.IsDue(now.AddSeconds(119), true) && schedule.IsDue(now.AddMinutes(2), true));
            require(new UpdateCheckSchedule().IsDue(now.AddSeconds(1)));
        });
        check("Automatic failures retry with backoff and wake never bypasses rate limits", () =>
        {
            var now = DateTimeOffset.UtcNow;
            var schedule = new UpdateCheckSchedule();
            foreach (var minutes in new[] { 1, 5, 15, 60, 60 })
            {
                schedule.Started(now); schedule.Failed(now, false);
                require(!schedule.IsDue(now.AddMinutes(minutes).AddSeconds(-1), true));
                now = now.AddMinutes(minutes);
                require(schedule.IsDue(now));
            }
            schedule.Started(now); schedule.Failed(now, true);
            require(!schedule.IsDue(now.AddMinutes(59), true) && schedule.IsDue(now.AddHours(1)));
            schedule.Succeeded(now); schedule.Started(now); schedule.Failed(now, false);
            require(schedule.IsDue(now.AddMinutes(1)));
        });
        void Wait(Task task)
        {
            if (!task.IsCompleted)
            {
                var frame = new System.Windows.Threading.DispatcherFrame();
                var dispatcher = System.Windows.Threading.Dispatcher.CurrentDispatcher;
                _ = task.ContinueWith(_ => dispatcher.BeginInvoke(() => frame.Continue = false));
                System.Windows.Threading.Dispatcher.PushFrame(frame);
            }
            task.GetAwaiter().GetResult();
        }
        check("New release published while open shows a download prompt without any check click or stale cache", () =>
        {
            var area = Path.Combine(root, "automatic-release");
            Directory.CreateDirectory(Path.Combine(area, "updates"));
            var now = DateTimeOffset.UtcNow;
            File.WriteAllText(Path.Combine(area, "updates", "checked-at.txt"), now.ToString("O"));
            File.WriteAllText(Path.Combine(area, "updates", "latest-release.json"), "null");
            var requests = 0;
            var window = new MainWindow(Path.Combine(area, "tools.json"), null, null, true,
                new UpdateClient(new FakeHttp(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(++requests == 1 ? "[]" : JsonSerializer.Serialize(new[] { Release("0.3.99") })) })), () => now);
            try
            {
                Wait(window.CheckUpdatesAsync(false));
                require(requests == 1);
                now = now.AddMinutes(10);
                Wait(window.CheckUpdatesAsync(false));
                require(requests == 2);
                require(((System.Windows.FrameworkElement)window.FindName("UpdateBanner")).Visibility == System.Windows.Visibility.Visible);
                require(((System.Windows.Controls.TextBlock)window.FindName("UpdateTitle")).Text == "发现新版本 v0.3.99");
                require(((System.Windows.Controls.Button)window.FindName("InstallUpdateButton")).Content.ToString() == "下载并更新");
                ((System.Windows.FrameworkElement)window.FindName("UpdateBanner")).Visibility = System.Windows.Visibility.Collapsed;
                now = now.AddMinutes(10);
                Wait(window.CheckUpdatesAsync(false));
                require(requests == 3 && ((System.Windows.FrameworkElement)window.FindName("UpdateBanner")).Visibility == System.Windows.Visibility.Collapsed);
            }
            finally { window.ReleaseTools(); }
        });
        check("Automatic network failure recovers and displays the new version without a click", () =>
        {
            var now = DateTimeOffset.UtcNow;
            var requests = 0;
            var window = new MainWindow(Path.Combine(root, "automatic-retry", "tools.json"), null, null, true,
                new UpdateClient(new FakeHttp(_ => ++requests == 1 ? new HttpResponseMessage(HttpStatusCode.ServiceUnavailable) : new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new[] { Release("0.3.99") })) })), () => now);
            try
            {
                Wait(window.CheckUpdatesAsync(false));
                require(((System.Windows.Controls.TextBlock)window.FindName("UpdateDescription")).Text.Contains("将自动重试"));
                now = now.AddSeconds(59); Wait(window.CheckUpdatesAsync(false, true)); require(requests == 1);
                now = now.AddSeconds(2); Wait(window.CheckUpdatesAsync(false));
                require(requests == 2 && ((System.Windows.Controls.TextBlock)window.FindName("UpdateTitle")).Text == "发现新版本 v0.3.99");
                require(((System.Windows.Controls.Button)window.FindName("InstallUpdateButton")).IsEnabled);
            }
            finally { window.ReleaseTools(); }
        });

        PackageManifest Fixture(string directory, string fixtureVersion, params (string Name, string Text)[] files)
        {
            Directory.CreateDirectory(directory);
            var manifest = new PackageManifest(fixtureVersion, new List<PackageFile>());
            foreach (var file in files.Prepend((Name: UpdatePackage.AppExecutable, Text: "synthetic exe " + fixtureVersion)))
            {
                var path = UpdatePackage.Resolve(directory, file.Name);
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                File.WriteAllText(path, file.Text);
                var data = File.ReadAllBytes(path);
                manifest.Files.Add(new PackageFile(file.Name, data.Length, Hash(data)));
            }
            File.WriteAllText(Path.Combine(directory, UpdatePackage.ManifestName), JsonSerializer.Serialize(manifest, UpdatePackage.Json));
            return manifest;
        }
        string Area(string name) => Path.Combine(root, "update-" + name);
        check("Portable update replaces publisher files, adds tools and preserves user files", () =>
        {
            var target = Area("replace"); var staged = Area("replace-staged"); var backup = Area("replace-backup");
            Fixture(target, "0.3.7", ("tools/old.txt", "old"));
            Fixture(staged, "0.3.8", ("tools/new.txt", "new"));
            File.WriteAllText(Path.Combine(target, "my-notes.txt"), "user file");
            UpdatePackage.Apply(target, staged, backup);
            require(UpdatePackage.Read(target).Version == "0.3.8" && File.Exists(Path.Combine(target, "tools", "new.txt")) && !File.Exists(Path.Combine(target, "tools", "old.txt")));
            require(File.ReadAllText(Path.Combine(target, "my-notes.txt")) == "user file" && UpdatePackage.Read(backup).Version == "0.3.7");
        });
        check("Portable update rolls back interrupted writes and removes only newly written files", () =>
        {
            var target = Area("rollback"); var staged = Area("rollback-staged"); var backup = Area("rollback-backup");
            Fixture(target, "0.3.7", ("tool.txt", "original"));
            Fixture(staged, "0.3.8", ("new.txt", "new"), ("tool.txt", "changed"));
            File.WriteAllText(Path.Combine(target, "user.txt"), "untouched");
            Reject(() => UpdatePackage.Apply(target, staged, backup, count => { if (count == 3) throw new IOException("synthetic interruption"); }));
            require(UpdatePackage.Read(target).Version == "0.3.7" && File.ReadAllText(Path.Combine(target, "tool.txt")) == "original" && !File.Exists(Path.Combine(target, "new.txt")) && File.ReadAllText(Path.Combine(target, "user.txt")) == "untouched");
        });
        check("Portable updater refuses to overwrite an added user file with a newly introduced name", () =>
        {
            var target = Area("collision"); var staged = Area("collision-staged");
            Fixture(target, "0.3.7"); Fixture(staged, "0.3.8", ("notes.txt", "publisher"));
            File.WriteAllText(Path.Combine(target, "notes.txt"), "user notes");
            Reject(() => UpdatePackage.Apply(target, staged, Area("collision-backup")));
            require(UpdatePackage.Read(target).Version == "0.3.7" && File.ReadAllText(Path.Combine(target, "notes.txt")) == "user notes");
        });
        check("Updater does not delete obsolete publisher files modified by the user", () =>
        {
            var target = Area("modified"); var staged = Area("modified-staged");
            Fixture(target, "0.3.7", ("custom.txt", "original")); Fixture(staged, "0.3.8");
            File.WriteAllText(Path.Combine(target, "custom.txt"), "modified by user");
            UpdatePackage.Apply(target, staged, Area("modified-backup"));
            require(File.ReadAllText(Path.Combine(target, "custom.txt")) == "modified by user");
        });
        check("Updater detects altered staged files before touching the existing program", () =>
        {
            var target = Area("tampered"); var staged = Area("tampered-staged");
            Fixture(target, "0.3.7"); Fixture(staged, "0.3.8");
            File.WriteAllText(Path.Combine(staged, UpdatePackage.AppExecutable), "tampered");
            Reject(() => UpdatePackage.Apply(target, staged, Area("tampered-backup")));
            require(UpdatePackage.Read(target).Version == "0.3.7");
        });
        check("Updater rejects downgrade and same-version replacement", () =>
        {
            var target = Area("downgrade"); var staged = Area("downgrade-staged");
            Fixture(target, "0.3.7"); Fixture(staged, "0.3.6");
            Reject(() => UpdatePackage.Apply(target, staged, Area("downgrade-backup")));
        });
        check("Updater rejects path traversal, Windows reserved names, alternate streams and UNC targets", () =>
        {
            foreach (var path in new[] { "../outside.txt", "tools/../../outside.txt", "C:/file", "tools\\file", "tools/file:stream", "tools/CON.txt", "tools/file.", "tools/file ", "tools//file" }) Reject(() => UpdatePackage.Resolve(root, path));
            Reject(() => UpdatePackage.EnsureNoLinks(@"\\server\share\file"));
        });
        check("Updater rejects duplicate and oversized package manifest entries", () =>
        {
            var manifest = Fixture(Area("manifest"), "0.3.8");
            manifest.Files.Add(manifest.Files[0] with { Path = UpdatePackage.AppExecutable.ToUpperInvariant() });
            Reject(() => UpdatePackage.Validate(root, manifest));
            manifest.Files.RemoveAt(1);
            manifest.Files[0] = manifest.Files[0] with { Size = 2L * 1024 * 1024 * 1024 };
            Reject(() => UpdatePackage.Validate(root, manifest));
        });
        check("Updater extracts only complete verified ZIP packages", () =>
        {
            var staged = Area("zip-source"); Fixture(staged, "0.3.8", ("tools/example.txt", "safe"));
            var zip = Area("good.zip");
            using (var archive = ZipFile.Open(zip, ZipArchiveMode.Create))
                foreach (var file in Directory.GetFiles(staged, "*", SearchOption.AllDirectories)) archive.CreateEntryFromFile(file, "AI-First-Tools/" + Path.GetRelativePath(staged, file).Replace('\\', '/'));
            require(UpdatePackage.Extract(zip, Area("zip-out"), "0.3.8", CancellationToken.None).Version == "0.3.8");
        });
        check("Updater rejects ZIP traversal and case-insensitive duplicate entries before extraction", () =>
        {
            foreach (var kind in new[] { "traversal", "duplicate", "link" })
            {
                var zip = Area(kind + ".zip");
                using (var archive = ZipFile.Open(zip, ZipArchiveMode.Create))
                {
                    var entry = archive.CreateEntry(kind == "traversal" ? "AI-First-Tools/../outside.txt" : "AI-First-Tools/file.txt");
                    if (kind == "duplicate") archive.CreateEntry("AI-First-Tools/FILE.txt");
                    if (kind == "link") entry.ExternalAttributes = 0xA000 << 16;
                }
                Reject(() => UpdatePackage.Extract(zip, Area(kind + "-out"), "0.3.8", CancellationToken.None));
                require(!Directory.Exists(Area(kind + "-out")));
            }
        });
        check("Updater runner copies its runtime and brand but not tools or conversations", () =>
        {
            foreach (var name in new[] { UpdatePackage.AppExecutable, "System.dll", "cs/PresentationFramework.resources.dll", "AI一手工具工作台.runtimeconfig.json", "assets/ai-first-logo.ico" }) require(UpdateRunner.IsRunnerFile(new PackageFile(name, 1, digest)));
            foreach (var name in new[] { "tools/dialog-mover/_internal/python.dll", "auth.json", "sessions/conversation.jsonl", "tools.json" }) require(!UpdateRunner.IsRunnerFile(new PackageFile(name, 1, digest)));
        });
        check("Updater refuses helper instructions outside its private cache", () => Reject(() => UpdateRunner.ValidatePlan(Path.Combine(root, "plan.json"), root)));
        check("Update guard is per installation and blocks relaunch without taking over another directory", () =>
        {
            var target = Area("guard");
            using var guard = new Mutex(false, UpdateRunner.GuardName(target));
            require(UpdateRunner.IsUpdating(target) && !UpdateRunner.IsUpdating(Area("other-guard")));
        });
    }

    private sealed class FakeHttp : HttpMessageHandler
    {
        private readonly Func<string, HttpResponseMessage> respond;
        internal FakeHttp(Func<string, HttpResponseMessage> response) => respond = response;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(respond(request.RequestUri!.AbsoluteUri));
        }
    }
}
