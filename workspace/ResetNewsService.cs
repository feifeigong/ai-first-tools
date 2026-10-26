using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Xml;
using System.Xml.Linq;

namespace AIFirst.Workspace;

internal sealed record ResetNewsItem(string Id, string Summary, string Text, string Kind, DateTimeOffset PublishedAt, string Url,
    string SourceLabel = "Tibo · X", string SourceUrl = "https://x.com/thsottiaux", string GroupId = "", bool Historical = false);

internal sealed record ResetNewsSnapshot(bool Enabled, string StatusText, string DetailText, DateTimeOffset? LastCheckedAt,
    IReadOnlyList<ResetNewsItem> Items, bool Fresh = false, DateTimeOffset? LastSuccess = null, DateTimeOffset? NextCheck = null, bool Partial = false);

internal sealed partial class ResetNewsService : IDisposable
{
    internal const string FeedUrl = "https://codex-reset.com/api/feed";
    private const int MaxBytes = 1024 * 1024;
    private static readonly TimeSpan Freshness = TimeSpan.FromMinutes(15);
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, MaxDepth = 32 };
    private readonly HttpClient http;
    private readonly Func<DateTimeOffset> clock;
    private readonly bool ownsHttp;
    private readonly bool includeHistory;
    private readonly CancellationTokenSource lifetime = new();
    private string previousSnapshot = "";
    private bool disposed;

    private sealed class Saved
    {
        public Saved() { }
        public int Version { get; set; } = 1;
        public bool Enabled { get; set; } = true;
        public bool Initialized { get; set; }
        public DateTimeOffset? AlertSince { get; set; }
        public DateTimeOffset? LastCheckedAt { get; set; }
        public DateTimeOffset? LastSuccess { get; set; }
        public DateTimeOffset? FetchedAt { get; set; }
        public DateTimeOffset? NextCheck { get; set; }
        public bool Fresh { get; set; }
        public bool Partial { get; set; }
        public int Failures { get; set; }
        public List<ResetNewsItem> Items { get; set; } = new();
        public List<string> Pending { get; set; } = new();
        public Dictionary<string, DateTimeOffset> Seen { get; set; } = new();
        public Dictionary<string, DateTimeOffset> SeenStages { get; set; } = new();
        public List<Candidate> HistoryQueue { get; set; } = new();
        public Dictionary<string, DateTimeOffset> HistoryChecked { get; set; } = new();
        public int HistoryOffset { get; set; }
        public DateTimeOffset? HistoryNextPage { get; set; }
        public string? HistoryFrom { get; set; }
    }

    private sealed record Candidate(string Id, string Text, DateTimeOffset At, string? Parent, bool Historical = false, bool RelatedHint = false);
    private sealed record Feed(DateTimeOffset FetchedAt, List<Candidate> Candidates, List<Candidate> History);
    private sealed record Verified(string Id, string Text, bool Complete = true);

    internal static string DefaultDirectory => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AI一手工具工作台", App.IsDevelopmentPreview ? "memory-preview" : "", "reset-notices");
    internal string DataDirectory { get; }
    internal ResetNewsSnapshot Snapshot { get; private set; } = new(true, "正在查看重置消息", "只在发现明确的新消息时提醒。", null, Array.Empty<ResetNewsItem>());
    internal event Action<ResetNewsSnapshot>? Changed;

    internal ResetNewsService() : this(DefaultDirectory, CreateClient(), () => DateTimeOffset.UtcNow, true, true) { }
    internal ResetNewsService(string dataDirectory, HttpClient httpClient, Func<DateTimeOffset> clock, bool includeHistory = true) : this(dataDirectory, httpClient, clock, false, includeHistory) { }
    private ResetNewsService(string dataDirectory, HttpClient httpClient, Func<DateTimeOffset> clock, bool ownsHttp, bool includeHistory)
    {
        DataDirectory = Path.GetFullPath(dataDirectory);
        http = httpClient;
        this.clock = clock;
        this.ownsHttp = ownsHttp;
        this.includeHistory = includeHistory;
        ReadCached();
    }

    private static HttpClient CreateClient() => new(new HttpClientHandler
    {
        UseCookies = false, UseDefaultCredentials = false, Credentials = null, AllowAutoRedirect = false,
        AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate
    }) { Timeout = Timeout.InfiniteTimeSpan };

    private string StateFile => Path.Combine(DataDirectory, "state.json");
    private static void Plain(string path)
    {
        if (File.Exists(path) || Directory.Exists(path))
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("提醒设置暂时无法读取。");
    }

    private FileStream? TryLock(string name)
    {
        Plain(DataDirectory);
        Directory.CreateDirectory(DataDirectory);
        var path = Path.Combine(DataDirectory, name);
        Plain(path);
        try { return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
        catch (IOException) { return null; }
    }

    private FileStream StateLock()
    {
        for (var attempt = 0; attempt < 80; attempt++)
        {
            var stream = TryLock("state.lock");
            if (stream is not null) return stream;
            Thread.Sleep(10);
        }
        throw new IOException("提醒设置正在更新，请稍后重试。");
    }

    private Saved Load()
    {
        Plain(DataDirectory);
        Plain(StateFile);
        if (!File.Exists(StateFile)) return new Saved();
        if (new FileInfo(StateFile).Length > MaxBytes) throw new InvalidDataException();
        var result = JsonSerializer.Deserialize<Saved>(File.ReadAllText(StateFile, Encoding.UTF8), Json) ?? throw new InvalidDataException();
        if (result.Version != 1 || result.Items is null || result.Pending is null || result.Seen is null || result.SeenStages is null
            || result.Items.Count > 120 || result.Seen.Count > 4000 || result.SeenStages.Count > 4000
            || result.HistoryQueue is null || result.HistoryQueue.Count > 300 || result.HistoryChecked is null || result.HistoryChecked.Count > 600
            || result.HistoryOffset is < 0 or > 2000 || result.HistoryQueue.Any(item => !ValidCandidate(item))
            || result.Items.Any(item => !ValidItem(item))) throw new InvalidDataException();
        return result;
    }

    private void Save(Saved value)
    {
        var temporary = Path.Combine(DataDirectory, "state." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            Plain(StateFile);
            var encoded = JsonSerializer.SerializeToUtf8Bytes(value, Json);
            // Never write a cache that the bounded reader would be unable to open again.
            while (encoded.Length > MaxBytes && (value.HistoryQueue.Count > 0 || value.Items.Count > 1))
            {
                if (value.HistoryQueue.Count > 0) value.HistoryQueue.RemoveAt(value.HistoryQueue.Count - 1);
                else value.Items.RemoveAt(value.Items.Count - 1);
                encoded = JsonSerializer.SerializeToUtf8Bytes(value, Json);
            }
            if (encoded.Length > MaxBytes) throw new InvalidDataException();
            File.WriteAllBytes(temporary, encoded);
            File.Move(temporary, StateFile, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private bool IsFresh(Saved value, DateTimeOffset now) => value.Fresh && value.FetchedAt is { } fetched
        && value.LastSuccess is { } success && now - fetched <= Freshness && now - success <= Freshness
        && fetched <= now.AddMinutes(2) && success <= now.AddMinutes(2);

    private void Publish(Saved value)
    {
        if (disposed) return;
        var fresh = IsFresh(value, clock());
        var title = !value.Enabled ? "重置消息提醒已关闭" : fresh ? value.Partial ? "部分消息还没确认，稍后继续查" : "正在留意 Tibo 的重置消息" : value.LastCheckedAt is null ? "正在获取重置消息" : "暂时没取到最新消息，正在自动重试";
        var detail = !value.Enabled ? "旧消息仍可查看，重新开启后继续提醒。" : fresh
            ? value.Partial ? "本次只提醒已经核实的消息，其余消息稍后再查。由你决定是否关闭续跑。" : "发现新的重置预告或完成消息时提醒你，由你决定是否关闭续跑。"
            : value.LastCheckedAt is null ? "有重置预告或完成消息时，会弹窗提醒。" : value.Items.Count > 0 ? "下方是上次保存的消息，发布时间已标出。" : "取到最新消息后会在这里显示，无需一直点刷新。";
        Snapshot = new(value.Enabled, title, detail, value.LastCheckedAt, value.Items.ToArray(), fresh, value.LastSuccess, value.NextCheck, value.Partial);
        var encoded = JsonSerializer.Serialize(Snapshot, Json);
        if (encoded == previousSnapshot) return;
        previousSnapshot = encoded;
        Changed?.Invoke(Snapshot);
    }

    internal void ReadCached()
    {
        if (disposed) return;
        try { Publish(Load()); }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or InvalidDataException)
        {
            Snapshot = Snapshot with { Fresh = false, StatusText = "消息暂时无法更新", DetailText = "已保存的设置未改动，请稍后重试。" };
            Changed?.Invoke(Snapshot);
        }
    }

    internal Task SetEnabledAsync(bool enabled)
    {
        if (disposed) return Task.CompletedTask;
        Saved saved;
        using (StateLock())
        {
            saved = Load();
            saved.Enabled = enabled;
            if (!enabled) saved.Pending.Clear();
            Save(saved);
        }
        Publish(saved);
        return Task.CompletedTask;
    }

    internal Task RefreshAsync() => RefreshAsync(true);
    internal async Task RefreshAsync(bool manual)
    {
        if (disposed) return;
        using var networkLock = TryLock("request.lock");
        if (networkLock is null) { ReadCached(); return; }
        var now = clock();
        Saved starting;
        var skipped = false;
        using (StateLock())
        {
            var saved = starting = Load();
            if (!saved.Enabled || (saved.LastCheckedAt is { } last && now - last < (manual ? TimeSpan.FromSeconds(30) : TimeSpan.FromMinutes(5)))
                || (!manual && saved.NextCheck is { } next && now < next)) skipped = true;
            else
            {
                saved.LastCheckedAt = now;
                saved.NextCheck = now.AddMinutes(5);
                Save(saved);
            }
        }
        if (skipped) { Publish(starting); return; }
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(45));
        try
        {
            var feed = ParseFeed(await ReadJsonAsync(new Uri(FeedUrl), timeout.Token).ConfigureAwait(false), now);
            var scan = await ScanAsync(feed, starting, now, timeout.Token).ConfigureAwait(false);
            var items = scan.Items;
            var partial = scan.Partial;
            if (partial && items.Count == 0) throw new InvalidDataException();
            if (disposed) return;
            Saved updated;
            using (StateLock())
            {
                var saved = updated = Load(); // Preserve preference/seen changes made while HTTP was in flight.
                var finished = clock();
                if (!saved.Initialized) { saved.Initialized = true; saved.AlertSince = finished.AddHours(-6); }
                saved.Items = items.GroupBy(item => item.Id).Select(group => group.First()).Concat(saved.Items.Where(old => items.All(item => item.Id != old.Id)))
                    .Where(item => finished - item.PublishedAt < TimeSpan.FromDays(30)).OrderByDescending(item => item.PublishedAt).Take(120).ToList();
                saved.Pending = saved.Enabled ? saved.Pending.Concat(items.Where(item => Eligible(item, saved, finished)).Select(item => item.Id)).Distinct().ToList() : new();
                saved.HistoryQueue = scan.Queue;
                saved.HistoryChecked = scan.Checked;
                saved.HistoryOffset = scan.Offset;
                saved.HistoryFrom = scan.From;
                saved.HistoryNextPage = scan.NextPage;
                saved.LastSuccess = finished;
                saved.FetchedAt = feed.FetchedAt;
                saved.Fresh = finished - feed.FetchedAt <= Freshness;
                saved.Partial = partial;
                if (!saved.Fresh) saved.Pending.Clear();
                saved.Failures = 0;
                saved.NextCheck = now.AddMinutes(5);
                PruneSeen(saved, finished);
                Save(saved);
            }
            Publish(updated);
        }
        catch (Exception exception) when (VerificationFailure(exception))
        {
            if (disposed || lifetime.IsCancellationRequested) return;
            Scan? history = null;
            if (includeHistory && !timeout.IsCancellationRequested)
                try { history = await ScanAsync(new(now, new(), new()), starting, now, timeout.Token).ConfigureAwait(false); }
                catch (Exception historyFailure) when (VerificationFailure(historyFailure)) { }
            if (disposed || lifetime.IsCancellationRequested) return;
            Saved failed;
            using (StateLock())
            {
                var saved = failed = Load();
                if (history is not null)
                {
                    saved.Items = history.Items.Concat(saved.Items).DistinctBy(item => item.Id)
                        .Where(item => clock() - item.PublishedAt < TimeSpan.FromDays(30)).OrderByDescending(item => item.PublishedAt).Take(120).ToList();
                    saved.HistoryQueue = history.Queue;
                    saved.HistoryChecked = history.Checked;
                    saved.HistoryOffset = history.Offset;
                    saved.HistoryFrom = history.From;
                    saved.HistoryNextPage = history.NextPage;
                }
                saved.Fresh = false;
                saved.Partial = false;
                saved.Pending.Clear();
                saved.Failures = Math.Min(saved.Failures + 1, 4);
                saved.NextCheck = clock().AddMinutes(Math.Min(5 * Math.Pow(2, saved.Failures - 1), 60));
                Save(saved);
            }
            Publish(failed);
        }
    }

    private static string Stage(ResetNewsItem item) => (string.IsNullOrEmpty(item.GroupId) ? item.Id : item.GroupId) + ":" + item.Kind;
    private static bool Eligible(ResetNewsItem item, Saved saved, DateTimeOffset now) => !item.Historical && item.Kind != "uncertain" && item.PublishedAt <= now.AddMinutes(2)
        && now - item.PublishedAt <= TimeSpan.FromHours(24) && item.PublishedAt >= saved.AlertSince
        && !ElapsedPreview(item, now)
        && !saved.Seen.ContainsKey(item.Id) && !saved.SeenStages.ContainsKey(Stage(item));
    private static bool ElapsedPreview(ResetNewsItem item, DateTimeOffset now)
    {
        if (item.Kind != "upcoming") return false;
        var view = ResetNewsPresentation.From(item, now);
        return view.ExpectedAt is { } expected && expected <= now && (view.AlternativeAt is null || view.AlternativeAt <= now);
    }
    private static void PruneSeen(Saved saved, DateTimeOffset now)
    {
        saved.Seen = saved.Seen.Where(pair => now - pair.Value < TimeSpan.FromDays(90)).OrderByDescending(pair => pair.Value).Take(2000).ToDictionary(pair => pair.Key, pair => pair.Value);
        saved.SeenStages = saved.SeenStages.Where(pair => now - pair.Value < TimeSpan.FromDays(90)).OrderByDescending(pair => pair.Value).Take(2000).ToDictionary(pair => pair.Key, pair => pair.Value);
    }

    internal bool TryTakeAlert(out ResetNewsItem? item)
    {
        item = null;
        if (disposed) return false;
        try
        {
            Saved saved;
            using (StateLock())
            {
                saved = Load();
                var now = clock();
                if (saved.Enabled && IsFresh(saved, now))
                {
                    item = saved.Items.Where(value => saved.Pending.Contains(value.Id) && Eligible(value, saved, now)).OrderByDescending(value => value.PublishedAt).FirstOrDefault();
                    if (item is not null)
                    {
                        var stage = Stage(item);
                        saved.Seen[item.Id] = now;
                        saved.SeenStages[stage] = now;
                        // Same phase in a reply chain is one announcement; edits never renew a seen post.
                        foreach (var related in saved.Items.Where(value => Stage(value) == stage)) saved.Seen[related.Id] = now;
                        saved.Pending.RemoveAll(id => saved.Seen.ContainsKey(id));
                        Save(saved);
                    }
                }
            }
            Publish(saved);
            return item is not null;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException or InvalidDataException) { ReadCached(); item = null; return false; }
    }

    private async Task<string> ReadJsonAsync(Uri address, CancellationToken cancellation)
    {
        if (address.Scheme != "https" || !address.IsDefaultPort || address.UserInfo.Length != 0
            || !((address.Host == "codex-reset.com" && address.AbsolutePath == "/api/feed")
                || (address.Host == "www.codexreset-news.com" && address.AbsolutePath == "/api/v1/tibo/history")
                || (address.Host == "cdn.syndication.twimg.com" && address.AbsolutePath == "/tweet-result")
                || (address.Host == "publish.x.com" && address.AbsolutePath == "/oembed"))) throw new InvalidDataException();
        using var request = new HttpRequestMessage(HttpMethod.Get, address);
        request.Headers.Accept.ParseAdd("application/json");
        request.Headers.UserAgent.ParseAdd("AI-First-Tools/0.3.16");
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellation).ConfigureAwait(false);
        if ((int)response.StatusCode is < 200 or >= 300 || response.Content.Headers.ContentLength > MaxBytes) throw new HttpRequestException();
        await using var source = await response.Content.ReadAsStreamAsync(cancellation).ConfigureAwait(false);
        using var output = new MemoryStream();
        var buffer = new byte[8192];
        int count;
        while ((count = await source.ReadAsync(buffer, cancellation).ConfigureAwait(false)) != 0)
        {
            if (output.Length + count > MaxBytes) throw new InvalidDataException();
            output.Write(buffer, 0, count);
        }
        return new UTF8Encoding(false, true).GetString(output.ToArray());
    }

    private static string String(JsonElement value, string key) => value.TryGetProperty(key, out var property) && property.ValueKind == JsonValueKind.String ? property.GetString()! : throw new InvalidDataException();
    private static DateTimeOffset Time(string value) => DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var stamp) ? stamp.ToUniversalTime() : throw new InvalidDataException();
    private static DateTimeOffset IdTime(string id)
    {
        if (!Regex.IsMatch(id, @"^[1-9][0-9]{14,19}$") || !ulong.TryParse(id, out var number)) throw new InvalidDataException();
        return DateTimeOffset.FromUnixTimeMilliseconds(checked((long)(number >> 22) + 1288834974657));
    }
    private static string PostUrl(string id) => "https://x.com/thsottiaux/status/" + id;
    private static bool PostAddress(string address, string id) => Uri.TryCreate(address, UriKind.Absolute, out var uri) && uri.Scheme == "https" && uri.IsDefaultPort && uri.UserInfo.Length == 0
        && uri.Host is "x.com" or "twitter.com" && uri.AbsolutePath.TrimEnd('/') == "/thsottiaux/status/" + id;
    private static bool AuthorAddress(string address) => Uri.TryCreate(address, UriKind.Absolute, out var uri) && uri.Scheme == "https" && uri.IsDefaultPort && uri.UserInfo.Length == 0
        && uri.Host is "x.com" or "twitter.com" && uri.AbsolutePath.TrimEnd('/') == "/thsottiaux";
    private static bool ValidItem(ResetNewsItem item) => item is not null && item.Kind is "upcoming" or "announced" or "banked" or "uncertain"
        && item.Id is not null && Regex.IsMatch(item.Id, @"^[1-9][0-9]{14,19}$") && PostAddress(item.Url, item.Id)
        && item.Text is { Length: > 0 and < 30000 } && item.Summary is { Length: > 0 and < 300 }
        && item.SourceUrl == "https://x.com/thsottiaux";

    private static Feed ParseFeed(string text, DateTimeOffset now)
    {
        using var document = JsonDocument.Parse(text, new JsonDocumentOptions { MaxDepth = 32 });
        var root = document.RootElement;
        if (root.GetProperty("version").GetInt32() != 1 || root.GetProperty("stale").ValueKind != JsonValueKind.False
            || String(root.GetProperty("profile"), "handle") != "thsottiaux" || String(root, "source") != "x-api" || String(root, "source_scope") != "timeline") throw new InvalidDataException();
        var fetched = Time(String(root, "fetched_at"));
        if (now - fetched > Freshness || fetched > now.AddMinutes(2)) throw new InvalidDataException();
        var rows = root.GetProperty("tweets");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 200) throw new InvalidDataException();
        var result = new List<Candidate>();
        foreach (var row in rows.EnumerateArray())
        {
            var id = String(row, "id");
            var body = String(row, "text");
            var at = Time(String(row, "at"));
            if (!PostAddress(String(row, "url"), id) || body.Length > 12000 || at > now.AddMinutes(2) || Math.Abs((IdTime(id) - at).TotalMinutes) > 5) throw new InvalidDataException();
            string? parent = null;
            if (row.TryGetProperty("is_reply", out var reply) && reply.ValueKind == JsonValueKind.True)
            {
                parent = String(row, "in_reply_to_tweet_id");
                if (IdTime(parent) > at || parent == id) throw new InvalidDataException();
            }
            if (now - at <= TimeSpan.FromDays(30)) result.Add(new(id, body, at, parent));
        }
        if (result.GroupBy(item => item.Id).Any(group => group.Select(item => item.Text).Distinct().Count() > 1)) throw new InvalidDataException();
        var history = new List<Candidate>();
        if (root.TryGetProperty("events", out var events) && events.ValueKind == JsonValueKind.Array && events.GetArrayLength() <= 300)
            foreach (var entry in events.EnumerateArray())
                try
                {
                    var id = String(entry, "id");
                    // Event summaries, completion labels and operator observation times are not original evidence.
                    var at = IdTime(id);
                    if (PostAddress(String(entry, "url"), id) && at <= now && now - at < TimeSpan.FromDays(30))
                        history.Add(new(id, "", at, null, true, true));
                }
                catch (Exception exception) when (VerificationFailure(exception)) { }
        return new(fetched, result.DistinctBy(item => item.Id).ToList(), history);
    }

    private static Verified ParseEmbed(string json, string id) => ParseEmbedCore(json, id, false);
    private static Verified ParseEmbedCore(string json, string id, bool allowIncomplete)
    {
        using var document = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 16 });
        var root = document.RootElement;
        if (String(root, "type") != "rich" || !AuthorAddress(String(root, "author_url")) || !PostAddress(String(root, "url"), id)) throw new InvalidDataException();
        var html = String(root, "html");
        var quote = Regex.Match(html, @"<blockquote\b[^>]*>.*?</blockquote>", RegexOptions.Singleline | RegexOptions.IgnoreCase);
        if (!quote.Success) throw new InvalidDataException();
        var fragment = Regex.Replace(quote.Value, @"<br\s*/?>", "<br/>", RegexOptions.IgnoreCase);
        fragment = Regex.Replace(fragment, @"&[A-Za-z][A-Za-z0-9]+;", match => string.Concat(WebUtility.HtmlDecode(match.Value).Select(character => "&#" + (int)character + ";")));
        using var reader = XmlReader.Create(new StringReader(fragment), new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null });
        var element = XElement.Load(reader);
        var paragraphs = element.Elements("p").ToArray();
        if (paragraphs.Length != 1) throw new InvalidDataException();
        var paragraph = paragraphs[0];
        if (!element.Elements("a").Any(anchor => PostAddress((string?)anchor.Attribute("href") ?? "", id))) throw new InvalidDataException();
        foreach (var lineBreak in paragraph.Descendants("br").ToArray()) lineBreak.ReplaceWith(new XText("\n"));
        foreach (var anchor in paragraph.Descendants("a").ToArray())
        {
            var label = anchor.Value;
            if (Regex.IsMatch(label, @"^(?:https?://|pic\.twitter\.com/)", RegexOptions.IgnoreCase)) anchor.Remove();
        }
        var body = Regex.Replace(paragraph.Value, @"\s+", " ").Trim();
        var complete = !body.EndsWith("…", StringComparison.Ordinal);
        if (body.Length is 0 or > 12000 || (!complete && !allowIncomplete)) throw new InvalidDataException();
        return new(id, body, complete);
    }

    private static string Normalize(string value) => Regex.Replace(Regex.Replace(WebUtility.HtmlDecode(value), @"https?://\S+", "", RegexOptions.IgnoreCase), @"\s+", " ").Trim();
    private static bool TimingReply(string value) => Regex.IsMatch(value, @"\b(?:lands?|landing|coming|tomorrow|tonight|before\s+\d|later\s+today)\b", RegexOptions.IgnoreCase);
    private static bool VerificationFailure(Exception exception) => exception is HttpRequestException or IOException or JsonException or InvalidDataException
        or OperationCanceledException or FormatException or OverflowException or XmlException or InvalidOperationException or KeyNotFoundException or ArgumentException;
    internal static string? Classify(string text)
    {
        var value = Normalize(text).ToLowerInvariant().Replace('’', '\'');
        if (Regex.IsMatch(value, @"\b(?:password|factory|device|router|database|server)\s+reset\b|\breset\s+(?:password|router|database|server)\b")) return null;
        // Banked credits are a separate event, even when the post says "see you tomorrow".
        if (Regex.IsMatch(value, @"\bbanked\s+reset\b"))
            return Regex.IsMatch(value, @"\b(?:loading|loaded|granting|granted|adding|added|giving|give|issuing|issued)\b.{0,100}\bbanked\s+reset\b")
                && !value.Contains('?') && !Regex.IsMatch(value, @"\b(?:not|no|if|wish|hope|please|should|don't|won't|can't)\b.{0,100}\bbanked\s+reset\b") ? "banked" : null;
        if (Regex.IsMatch(value, @"\bresets?\s+(?:are\s+|have\s+been\s+)?(?:all\s+)?propagated\b|\bput\s+the\s+reset\s+in\s+the\s+bag[.!]\s*all\s+propagated\b|\breset\s+has\s+been\s+processed\b")
            && !value.Contains('?') && !Regex.IsMatch(value, @"\b(?:not|no|will|going\s+to|if|when|hope|please|wish|should)\b.{0,100}\b(?:propagated|processed)\b")) return "announced";
        if (Regex.IsMatch(value, @"\b(?:please|wish|hope|hopefully|if|should|don't|won't|cannot|can't)\b.{0,90}\breset\b|\b(?:not|no)\s+(?:a\s+|yet\s+)?reset\b|\bnot\s+(?:done|complete)\b")) return null;
        if (!value.Contains('?') && Regex.IsMatch(value, @"\bglobal\s+reset\s+(?:landing\s+)?by\s+EOD\b", RegexOptions.IgnoreCase)) return "upcoming";
        if (!Regex.IsMatch(value, @"\b(?:codex|quota|usage|limits?|reset\s+day|side\s+of\s+reset)\b") && !Regex.IsMatch(value, @"\bday\s+\d+\s*/")) return null;
        if (Regex.IsMatch(value, @"\breset\b") && Regex.IsMatch(value, @"\bit'?s\s+done[.!]")) return "announced";
        if (value.Contains('?')) return null;
        if (Regex.IsMatch(value, @"\bthat'?s\s+a\s+reset[.!]"))
            return Regex.IsMatch(value, @"\b(?:tomorrow|tonight|soon|later|will|going\s+to)\b") ? "upcoming" : "announced";
        if (Regex.IsMatch(value, @"\bday\s+\d+\s*/\s*(?:le\s+limit\s+)?reset\b")) return "upcoming";
        if (Regex.IsMatch(value, @"\b(?:will|going\s+to|about\s+to|plan\s+to)\b.{0,90}\breset\b|\breset\b.{0,90}\b(?:tomorrow|tonight|soon|later|today)\b|\breset\s+day\b")) return "upcoming";
        if (Regex.IsMatch(value, @"\b(?:have|has|just|already)\s+(?:been\s+)?reset\b|\b(?:limits?|quota)\b.{0,50}\b(?:are|is|were|was|have\s+been|has\s+been)\s+reset\b|\breset\s+(?:is\s+)?(?:done|complete|completed)\b|\band\s+reset[.!]|\breset[.!]\s*(?:enjoy|done)\b")) return "announced";
        return null;
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        lifetime.Cancel();
        lifetime.Dispose();
        if (ownsHttp) http.Dispose();
    }
}
