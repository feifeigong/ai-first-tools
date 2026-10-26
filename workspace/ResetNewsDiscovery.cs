using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal sealed partial class ResetNewsService
{
    private sealed record Scan(List<ResetNewsItem> Items, bool Partial, List<Candidate> Queue,
        Dictionary<string, DateTimeOffset> Checked, int Offset, string? From, DateTimeOffset? NextPage);
    private sealed record HistoryPage(List<Candidate> Items, int? Next);
    private sealed record Resolved(string Kind, string Text, string Group);
    private static bool ValidCandidate(Candidate item) => item is not null && item.Text is { Length: <= 12000 }
        && Regex.IsMatch(item.Id ?? "", @"^[1-9][0-9]{14,19}$")
        && (item.Parent is null || Regex.IsMatch(item.Parent, @"^[1-9][0-9]{14,19}$"));
    private static bool CompletionOnly(string text) => Regex.IsMatch(Normalize(text), @"^(?:done(?:\s+and\s+dusted)?|all\s+propagated)[.!\s]*$", RegexOptions.IgnoreCase);

    private static HistoryPage ParseHistory(string json, DateTimeOffset now, int offset)
    {
        using var document = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 32 });
        var root = document.RootElement;
        if (String(root, "api_version") != "v1" || String(root, "handle") != "thsottiaux"
            || root.GetProperty("available").ValueKind != JsonValueKind.True || root.GetProperty("offset").GetInt32() != offset)
            throw new System.IO.InvalidDataException();
        var rows = root.GetProperty("items");
        if (rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 100) throw new System.IO.InvalidDataException();
        var result = new List<Candidate>();
        foreach (var row in rows.EnumerateArray())
        {
            var id = String(row, "id");
            var text = String(row, "text");
            var at = Time(String(row, "published_at"));
            if (!PostAddress(String(row, "url"), id) || text.Length > 12000 || Math.Abs((IdTime(id) - at).TotalMinutes) > 5
                || at > now.AddMinutes(2)) throw new System.IO.InvalidDataException();
            if (now - at < TimeSpan.FromDays(30))
                result.Add(new(id, text, at, null, true, CompletionOnly(text)));
        }
        int? next = null;
        if (root.TryGetProperty("next_offset", out var value) && value.ValueKind != JsonValueKind.Null)
        {
            next = value.GetInt32();
            if (next <= offset || next > 2000) throw new System.IO.InvalidDataException();
        }
        if (result.GroupBy(item => item.Id).Any(group => group.Select(item => item.Text).Distinct().Count() != 1)) throw new System.IO.InvalidDataException();
        return new(result.DistinctBy(item => item.Id).ToList(), next);
    }

    private async Task<Scan> ScanAsync(Feed feed, Saved saved, DateTimeOffset now, CancellationToken cancellation)
    {
        var checkedAt = saved.HistoryChecked.Where(pair => now - pair.Value < TimeSpan.FromDays(30))
            .OrderByDescending(pair => pair.Value).Take(500).ToDictionary(pair => pair.Key, pair => pair.Value);
        var queue = saved.HistoryQueue.Where(item => now - item.At < TimeSpan.FromDays(30)).ToDictionary(item => item.Id);
        void Add(Candidate item)
        {
            if (!queue.TryGetValue(item.Id, out var old) || item.Text.Length > old.Text.Length || item.Parent is not null)
                queue[item.Id] = item with { Historical = true, Parent = item.Parent ?? old?.Parent, RelatedHint = item.RelatedHint || (old?.RelatedHint ?? false) };
        }
        if (includeHistory) foreach (var candidate in feed.History.Concat(feed.Candidates)) Add(candidate);
        var offset = saved.HistoryOffset;
        var from = saved.HistoryFrom;
        var nextPage = saved.HistoryNextPage;
        // History snapshots may be stale: they only discover old IDs. They never authorize alerts.
        async Task DiscoverHistory()
        {
            if (!includeHistory || (nextPage is not null && now < nextPage)) return;
            if (offset == 0 || from is null) from = now.AddDays(-30).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            try
            {
                var address = new Uri("https://www.codexreset-news.com/api/v1/tibo/history?limit=100&offset="
                    + offset.ToString(CultureInfo.InvariantCulture) + "&from=" + from);
                using var historyTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                historyTimeout.CancelAfter(TimeSpan.FromSeconds(8));
                var page = ParseHistory(await ReadJsonAsync(address, historyTimeout.Token).ConfigureAwait(false), now, offset);
                foreach (var candidate in page.Items) Add(candidate);
                offset = page.Next ?? 0;
                nextPage = page.Next is null ? now.AddHours(6) : now.AddMinutes(5);
            }
            catch (Exception exception) when (VerificationFailure(exception)) { nextPage = now.AddMinutes(30); }
        }

        var candidates = queue.Values.Concat(feed.Candidates).GroupBy(item => item.Id)
            .ToDictionary(group => group.Key, group => group.OrderBy(item => item.Historical).ThenByDescending(item => item.Text.Length).First());
        var verified = new ConcurrentDictionary<string, Lazy<Task<Verified>>>();
        Task<Verified> Verify(string id) => verified.GetOrAdd(id, key => new Lazy<Task<Verified>>(async () =>
        {
            var uri = new Uri("https://publish.x.com/oembed?url=" + Uri.EscapeDataString(PostUrl(key)) + "&omit_script=true&hide_thread=true");
            var result = ParseEmbedCore(await ReadJsonAsync(uri, cancellation).ConfigureAwait(false), key, true);
            if (candidates.TryGetValue(key, out var candidate) && candidate.Text.Length > 0)
            {
                var official = Normalize(result.Text);
                var discovery = Normalize(candidate.Text);
                if (result.Complete ? official != discovery : !discovery.StartsWith(official.TrimEnd('…').TrimEnd(), StringComparison.Ordinal))
                    throw new System.IO.InvalidDataException();
            }
            return result;
        }, LazyThreadSafetyMode.ExecutionAndPublication)).Value;

        async Task<string?> OfficialQuote(string id, Verified post)
        {
            var address = new Uri("https://cdn.syndication.twimg.com/tweet-result?id=" + id + "&lang=en&token=0");
            using var document = JsonDocument.Parse(await ReadJsonAsync(address, cancellation).ConfigureAwait(false));
            var root = document.RootElement;
            if (String(root, "id_str") != id || String(root.GetProperty("user"), "screen_name") != "thsottiaux"
                || Normalize(String(root, "text")) != Normalize(post.Text)
                || Math.Abs((Time(String(root, "created_at")) - IdTime(id)).TotalMinutes) > 5) throw new System.IO.InvalidDataException();
            if (!root.TryGetProperty("quoted_tweet", out var quote) || quote.ValueKind == JsonValueKind.Null) return null;
            if (String(quote.GetProperty("user"), "screen_name") != "thsottiaux") throw new System.IO.InvalidDataException();
            var parent = String(quote, "id_str");
            if (IdTime(parent) >= IdTime(id)) throw new System.IO.InvalidDataException();
            return parent;
        }

        async Task<Resolved?> Resolve(Candidate candidate, int depth = 0)
        {
            if (depth >= 4) throw new System.IO.InvalidDataException();
            var original = await Verify(candidate.Id).ConfigureAwait(false);
            if (!original.Complete)
            {
                // A truncated official paragraph is never accepted as a completed announcement.
                return candidate.Historical && candidate.RelatedHint ? new("uncertain", original.Text, candidate.Id) : throw new System.IO.InvalidDataException();
            }
            var kind = Classify(original.Text);
            var text = original.Text;
            var group = candidate.Id;
            var parent = candidate.Parent;
            if (parent is null && CompletionOnly(text)) parent = await OfficialQuote(candidate.Id, original).ConfigureAwait(false);
            if (parent is not null)
            {
                if (IdTime(parent) >= candidate.At) throw new System.IO.InvalidDataException();
                var context = await Resolve(candidates.TryGetValue(parent, out var known) ? known : new(parent, "", IdTime(parent), null, candidate.Historical), depth + 1).ConfigureAwait(false);
                if (context is null || context.Kind == "uncertain") return null;
                group = context.Group;
                if (CompletionOnly(text)) kind = context.Kind == "banked" ? "banked" : "announced";
                else if (kind is null && context.Kind is "upcoming" or "banked" or "announced" && (TimingReply(text)
                    || Regex.IsMatch(text, @"\b(?:global\s+)?reset\s+by\s+EOD\b", RegexOptions.IgnoreCase)))
                    kind = context.Kind == "announced" ? "upcoming" : context.Kind;
                text = context.Text + "\n\n" + text;
            }
            if (kind is null && CompletionOnly(original.Text) && candidate.Historical && candidate.RelatedHint)
                return new("uncertain", original.Text, candidate.Id);
            return kind is null ? null : new(kind, text, group);
        }

        bool Needs(Candidate candidate) => candidate.Text.Length == 0 || Classify(candidate.Text) is not null || CompletionOnly(candidate.Text)
            || (candidate.Parent is { } parent && TimingReply(candidate.Text) && (!candidates.TryGetValue(parent, out var context) || Classify(context.Text) is not null));
        var items = new ConcurrentBag<ResetNewsItem>();
        var completed = new ConcurrentBag<string>();
        var partial = 0;
        using var concurrency = new SemaphoreSlim(3);
        async Task Process(Candidate candidate)
        {
            await concurrency.WaitAsync(cancellation).ConfigureAwait(false);
            try
            {
                var resolved = await Resolve(candidate).ConfigureAwait(false);
                if (resolved is not null)
                    items.Add(new(candidate.Id, resolved.Kind switch { "banked" => "Tibo 发布了重置卡消息", "announced" => "Tibo 宣布已完成重置", "uncertain" => "这条历史消息还待核实", _ => "Tibo 发布了新的重置预告" },
                        resolved.Text, resolved.Kind, IdTime(candidate.Id), PostUrl(candidate.Id), GroupId: resolved.Group, Historical: candidate.Historical));
                completed.Add(candidate.Id);
            }
            catch (Exception exception) when (VerificationFailure(exception))
            {
                if (!candidate.Historical) Interlocked.Exchange(ref partial, 1);
                if (!cancellation.IsCancellationRequested) completed.Add(candidate.Id);
            }
            finally { concurrency.Release(); }
        }
        // Recent official checks are first. Older records use a persistent, bounded work queue.
        var live = feed.Candidates.Where(item => (!includeHistory || now - item.At <= TimeSpan.FromHours(24)) && Needs(item)).OrderByDescending(item => item.At).Take(12).ToArray();
        await Task.WhenAll(live.Select(Process)).ConfigureAwait(false);
        if (includeHistory && !cancellation.IsCancellationRequested)
        {
            await DiscoverHistory().ConfigureAwait(false);
            foreach (var candidate in queue.Values)
                if (!candidates.ContainsKey(candidate.Id)) candidates[candidate.Id] = candidate;
            var liveIds = live.Select(item => item.Id).ToHashSet();
            var history = queue.Values.Where(item => !liveIds.Contains(item.Id) && Needs(item)
                && (!checkedAt.TryGetValue(item.Id, out var stamp) || now - stamp >= TimeSpan.FromHours(24)))
                .OrderBy(item => checkedAt.ContainsKey(item.Id)).ThenByDescending(item => item.At).Take(24).ToArray();
            try { await Task.WhenAll(history.Select(candidate => Process(feed.Candidates.FirstOrDefault(liveCandidate => liveCandidate.Id == candidate.Id
                && now - liveCandidate.At <= TimeSpan.FromHours(24)) ?? candidate))).ConfigureAwait(false); }
            catch (OperationCanceledException) when (!lifetime.IsCancellationRequested) { }
        }
        foreach (var id in completed) checkedAt[id] = now;
        return new(items.ToList(), partial != 0, queue.Values.OrderByDescending(item => item.At).Take(300).ToList(),
            checkedAt.OrderByDescending(pair => pair.Value).Take(500).ToDictionary(pair => pair.Key, pair => pair.Value), offset, from, nextPage);
    }
}
