using System.Net;
using System.Text.Json;
using AIFirst.Workspace;

namespace AIFirst.Workspace
{
    // The actual state directory is always supplied by the Mac host. This also
    // lets the existing Windows domain sources compile without a WPF dependency.
    internal static class App
    {
        internal static bool IsDevelopmentPreview => false;
        internal static string UserDataRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"AI一手工具工作台");
    }
}

internal static class Program
{
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, MaxDepth = 32 };
    private static string? Option(string[] args, string name)
    {
        var at = Array.IndexOf(args, name);
        return at >= 0 && at + 1 < args.Length ? args[at + 1] : null;
    }
    internal static object View(ResetNewsItem item, DateTimeOffset now)
    {
        var view = ResetNewsPresentation.From(item, now);
        return new { item.Id, item.Kind, item.Url, view.Summary, view.Description, view.TimeText, view.TimeNote,
            item.PublishedAt, publishedLabel = ResetNewsPresentation.BeijingStamp(item.PublishedAt), item.Historical };
    }
    internal static object Snapshot(ResetNewsSnapshot snapshot, DateTimeOffset now, ResetNewsItem? alert = null) => new
    {
        ok = true, snapshot.Enabled, snapshot.StatusText, snapshot.DetailText, snapshot.Fresh, snapshot.Partial,
        snapshot.LastCheckedAt, snapshot.LastSuccess, snapshot.NextCheck,
        lastCheckedLabel = snapshot.LastCheckedAt is { } at ? ResetNewsPresentation.BeijingStamp(at) : "尚未更新",
        checkedText = snapshot.LastSuccess is { } success ? $"消息更新于（北京）{ResetNewsPresentation.BeijingStamp(success)}"
            : snapshot.LastCheckedAt is { } attempt ? $"最近尝试（北京）{ResetNewsPresentation.BeijingStamp(attempt)}" : "尚未检查",
        today = ResetCalendarModel.BeijingDate(now).ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture),
        events = ResetCalendarModel.Events(snapshot.Items, now).Select(item => new
        {
            item.Id, date = item.Date.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture), item.State,
            item.Badge, item.Heading, item.Detail, item.TimeText, item.Note, item.Url, item.PublishedAt,
            publishedLabel = ResetNewsPresentation.BeijingStamp(item.PublishedAt)
        }),
        alert = alert is null ? null : View(alert, now)
    };

    private static int Check(string report)
    {
        var checks = new List<object>();
        var failed = 0;
        void Require(bool value) { if (!value) throw new InvalidOperationException("Synthetic assertion failed"); }
        void CheckOne(string name, Action action)
        {
            try { action(); checks.Add(new { name, passed = true }); }
            catch (Exception error) { failed++; checks.Add(new { name, passed = false, errorType = error.GetType().Name }); }
        }
        ResetNewsTests.Run(CheckOne, Require);
        CheckOne("A failed check never makes old news look newly updated", () =>
        {
            var success = DateTimeOffset.Parse("2026-10-23T00:00:00Z");
            var attempt = success.AddHours(1);
            using var cached = JsonDocument.Parse(JsonSerializer.Serialize(Snapshot(new(true, "", "", attempt,
                Array.Empty<ResetNewsItem>(), false, success), attempt), Json));
            Require(cached.RootElement.GetProperty("checkedText").GetString() == "消息更新于（北京）10-23 08:00");
            using var empty = JsonDocument.Parse(JsonSerializer.Serialize(Snapshot(new(true, "", "", attempt,
                Array.Empty<ResetNewsItem>()), attempt), Json));
            Require(empty.RootElement.GetProperty("checkedText").GetString() == "最近尝试（北京）10-23 09:00");
        });
        CheckOne("Mac bridge uses the same Chinese presentation and Beijing calendar as Windows", () =>
        {
            var now = DateTimeOffset.Parse("2026-10-23T04:00:00Z");
            var item = new ResetNewsItem("2113162413008884099", "", "Lands tomorrow before 10am PST", "upcoming",
                DateTimeOffset.Parse("2026-10-22T06:55:00Z"), "https://x.com/thsottiaux/status/2113162413008884099");
            var eventItem = ResetCalendarModel.Events(new[] { item }, now).Single();
            Require(eventItem.State == "past-preview" && eventItem.Badge == "历史预告");
            Require(eventItem.Date == new DateTime(2026, 10, 23) && eventItem.TimeText.Contains("02:00"));
            var payload = JsonSerializer.Serialize(Snapshot(new(true, "", "", now, new[] { item }), now), Json);
            Require(payload.Contains("2026-10-23") && !payload.Contains("Lands tomorrow"));
        });
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(report))!);
        File.WriteAllText(report, JsonSerializer.Serialize(new { passed = failed == 0, failed, checks, syntheticOnly = true, modelRequests = 0 }, Json));
        return failed == 0 ? 0 : 1;
    }

    public static async Task<int> Main(string[] args)
    {
        Console.InputEncoding = System.Text.Encoding.UTF8;
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);
        if (args.Contains("--self-test"))
            return Option(args, "--report") is { } report ? Check(report) : 2;
        try
        {
            var directory = Option(args, "--state-directory");
            if (directory is null || !Path.IsPathFullyQualified(directory)) throw new InvalidDataException();
            var line = await Console.In.ReadLineAsync();
            if (line is null || line.Length > 16384) throw new InvalidDataException();
            using var request = JsonDocument.Parse(line, new JsonDocumentOptions { MaxDepth = 16 });
            var operation = request.RootElement.GetProperty("operation").GetString();
            if (operation is not ("snapshot" or "refresh" or "enabled" or "take")) throw new InvalidDataException();
            using var handler = new HttpClientHandler
            {
                UseCookies = false, UseDefaultCredentials = false, Credentials = null, AllowAutoRedirect = false,
                AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate
            };
            using var http = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
            using var service = new ResetNewsService(directory, http, () => DateTimeOffset.UtcNow);
            if (operation == "enabled") await service.SetEnabledAsync(request.RootElement.GetProperty("enabled").GetBoolean());
            if (operation == "refresh")
                await service.RefreshAsync(request.RootElement.TryGetProperty("manual", out var manual) && manual.GetBoolean());
            ResetNewsItem? alert = null;
            if (operation == "take") service.TryTakeAlert(out alert);
            Console.WriteLine(JsonSerializer.Serialize(Snapshot(service.Snapshot, DateTimeOffset.UtcNow, alert), Json));
            return 0;
        }
        catch
        {
            Console.WriteLine(JsonSerializer.Serialize(new { error = "重置消息暂时无法更新，请稍后再试。" }, Json));
            return 1;
        }
    }
}
