using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal static partial class ResetNewsTests
{
    private sealed record Post(string Id, string Text, DateTimeOffset At, string? Parent = null);
    private sealed class Handler : HttpMessageHandler
    {
        internal int Count;
        internal readonly List<Uri> Requests = new();
        internal Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> Responder = (_, _) => throw new InvalidOperationException("No synthetic response configured");
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.Method != HttpMethod.Get || request.RequestUri is not { Scheme: "https" } uri
                || uri.Host is not ("codex-reset.com" or "publish.x.com" or "www.codexreset-news.com" or "cdn.syndication.twimg.com")
                || request.Headers.Authorization is not null || request.Headers.Contains("Cookie")) throw new InvalidOperationException("Unexpected request");
            Count++;
            Requests.Add(uri);
            return Responder(request, cancellationToken);
        }
    }

    private sealed class Fixture : IDisposable
    {
        internal readonly string DirectoryPath = Path.Combine(Path.GetTempPath(), "ai-first-reset-tests-" + Guid.NewGuid().ToString("N"));
        internal DateTimeOffset Now = new(2026, 10, 22, 12, 0, 0, TimeSpan.Zero);
        internal readonly Handler Handler = new();
        internal readonly HttpClient Client;
        internal readonly ResetNewsService Service;
        internal List<Post> Posts = new();
        internal List<Post> HistoryPosts = new();
        internal List<Post> EventPosts = new();
        internal Dictionary<string, string> Quotes = new();
        internal Dictionary<string, string> Parents = new();
        internal int HistoryPageSize = 100;
        private readonly bool includeHistory;
        internal readonly Dictionary<string, string> EmbedOverrides = new();
        internal string? FeedOverride;
        internal bool Stale;
        internal DateTimeOffset? FetchedAt;
        internal int Status = 200;
        internal Fixture(bool includeHistory = false)
        {
            this.includeHistory = includeHistory;
            Client = new HttpClient(Handler);
            Service = new ResetNewsService(DirectoryPath, Client, () => Now, includeHistory);
            Handler.Responder = Respond;
        }
        internal string StateFile => Path.Combine(DirectoryPath, "state.json");
        internal Post Add(string text, double hoursAgo = 1, string? parent = null)
        {
            var at = Now.AddHours(-hoursAgo);
            var id = (((ulong)(at.ToUnixTimeMilliseconds() - 1288834974657) << 22) + (ulong)(Posts.Count + HistoryPosts.Count) + 1).ToString(System.Globalization.CultureInfo.InvariantCulture);
            var result = new Post(id, text, at, parent);
            Posts.Add(result);
            return result;
        }
        internal Task<HttpResponseMessage> Respond(HttpRequestMessage request, CancellationToken cancellation)
        {
            var uri = request.RequestUri!;
            if (uri.Host == "codex-reset.com") return Task.FromResult(Response(FeedOverride ?? Feed(), Status));
            if (uri.Host == "www.codexreset-news.com")
            {
                var offset = int.Parse(System.Text.RegularExpressions.Regex.Match(uri.Query, @"offset=(\d+)").Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture);
                var page = HistoryPosts.Skip(offset).Take(HistoryPageSize).ToArray();
                return Task.FromResult(Response(JsonSerializer.Serialize(new { api_version = "v1", handle = "thsottiaux", available = true, stale = true,
                    offset, next_offset = offset + page.Length < HistoryPosts.Count ? (int?)(offset + page.Length) : null,
                    items = page.Select(value => new { id = value.Id, text = value.Text, published_at = value.At.ToString("O"), url = Url(value.Id) }) })));
            }
            var decoded = Uri.UnescapeDataString(uri.Query);
            var post = Posts.Concat(HistoryPosts).FirstOrDefault(value => decoded.Contains("/status/" + value.Id, StringComparison.Ordinal) || decoded.Contains("id=" + value.Id, StringComparison.Ordinal)) ?? throw new HttpRequestException("Synthetic post missing");
            if (uri.Host == "cdn.syndication.twimg.com")
            {
                var parent = Parents.GetValueOrDefault(post.Id) ?? post.Parent;
                object? Context(string id)
                {
                    var context = Posts.Concat(HistoryPosts).Single(value => value.Id == id);
                    return new { id_str = id, text = NormalizeBody(context.Text), created_at = context.At.ToString("O"), user = new { screen_name = "thsottiaux" } };
                }
                return Task.FromResult(Response(JsonSerializer.Serialize(new { id_str = post.Id, text = NormalizeBody(post.Text), created_at = post.At.ToString("O"),
                    user = new { screen_name = "thsottiaux" }, quoted_tweet = Quotes.TryGetValue(post.Id, out var quote) ? Context(quote) : null,
                    parent = parent is not null ? Context(parent) : null,
                    in_reply_to_status_id_str = parent })));
            }
            return Task.FromResult(Response(EmbedOverrides.TryGetValue(post.Id, out var replacement) ? replacement : Embed(post)));
        }
        internal string Feed() => JsonSerializer.Serialize(new
        {
            version = 1, fetched_at = (FetchedAt ?? Now).ToString("O"), source = "x-api", source_scope = "timeline", stale = Stale,
            profile = new { handle = "thsottiaux" },
            events = EventPosts.Select(value => new { id = value.Id, url = Url(value.Id), announced_at = Now.ToString("O"), announcement_state = "announced", type = "reset" }),
            tweets = Posts.Select(value => new { id = value.Id, text = value.Text, at = value.At.ToString("O"), url = Url(value.Id),
                is_reply = value.Parent is not null, in_reply_to_tweet_id = value.Parent, kind = "reset" }).ToArray()
        });
        internal void Refresh(bool manual = true) => Service.RefreshAsync(manual).GetAwaiter().GetResult();
        internal ResetNewsService Another() => new(DirectoryPath, Client, () => Now, includeHistory);
        internal Post Historical(string text, double hoursAgo = 48)
        {
            var post = Add(text, hoursAgo);
            Posts.Remove(post);
            HistoryPosts.Add(post);
            return post;
        }
        public void Dispose()
        {
            Service.Dispose();
            Client.Dispose();
            // This directory is generated solely for this synthetic fixture.
            if (System.IO.Directory.Exists(DirectoryPath)) System.IO.Directory.Delete(DirectoryPath, true);
        }
    }

    private static string Url(string id) => "https://x.com/thsottiaux/status/" + id;
    private static string NormalizeBody(string text) => System.Text.RegularExpressions.Regex.Replace(System.Text.RegularExpressions.Regex.Replace(text, @"https?://\S+", ""), @"\s+", " ").Trim();
    private static string Embed(Post post, string? author = null, string? text = null, string? url = null, string? html = null) => JsonSerializer.Serialize(new
    {
        type = "rich", author_name = "Tibo", author_url = author ?? "https://x.com/thsottiaux", url = url ?? Url(post.Id),
        html = html ?? "<blockquote class=\"twitter-tweet\"><p lang=\"en\">" + WebUtility.HtmlEncode(text ?? post.Text).Replace("\n", "<br>")
            + "</p>&mdash; Tibo (@thsottiaux) <a href=\"" + Url(post.Id).Replace("x.com", "twitter.com", StringComparison.Ordinal) + "\">October 22, 2026</a></blockquote>"
    });
    private static HttpResponseMessage Response(string text, int status = 200) => new((HttpStatusCode)status) { Content = new StringContent(text, Encoding.UTF8, "application/json") };

    internal static void Run(Action<string, Action> check, Action<bool> require)
    {
        RunDiscovery(check, require);
        check("Reset notices default enabled but constructor does not fetch or create files", () =>
        {
            using var fixture = new Fixture();
            require(fixture.Service.Snapshot.Enabled && fixture.Handler.Count == 0 && !Directory.Exists(fixture.DirectoryPath));
            require(fixture.Service.DataDirectory == fixture.DirectoryPath);
        });
        check("Verified recent reset announcement alerts once across services and restart", () =>
        {
            using var fixture = new Fixture();
            var post = fixture.Add("Codex quota reset is coming tomorrow.");
            fixture.Refresh();
            require(fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Items.Single().Kind == "upcoming");
            using var second = fixture.Another();
            require(second.TryTakeAlert(out var item) && item?.Id == post.Id);
            require(!fixture.Service.TryTakeAlert(out _));
            using var restarted = fixture.Another();
            require(!restarted.TryTakeAlert(out _) && restarted.Snapshot.Items.Count == 1);
            require(fixture.Handler.Count == 2);
        });
        check("First check shows older messages without notifying and ignores posts over 24 hours", () =>
        {
            using var fixture = new Fixture();
            fixture.Add("Codex quota has reset. Enjoy.", 8);
            fixture.Add("Codex quota has reset. Enjoy.", 25);
            fixture.Refresh();
            require(fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Items.Count == 2 && !fixture.Service.TryTakeAlert(out _));
        });
        check("Editing a seen post does not notify again while a new completed post can", () =>
        {
            using var fixture = new Fixture();
            var original = fixture.Add("Codex quota will reset tomorrow.");
            fixture.Refresh();
            require(fixture.Service.TryTakeAlert(out _));
            fixture.Now = fixture.Now.AddMinutes(6);
            fixture.Posts[0] = original with { Text = "Codex quota has reset. Enjoy." };
            fixture.Refresh();
            require(!fixture.Service.TryTakeAlert(out _));
            fixture.Now = fixture.Now.AddMinutes(6);
            var completed = fixture.Add("Codex quota has reset. Enjoy.", 0.01);
            fixture.Refresh();
            require(fixture.Service.TryTakeAlert(out var alert) && alert?.Id == completed.Id && alert.Kind == "announced");
        });
        check("Verified reply uses its exact parent and same phase is only one alert", () =>
        {
            using var fixture = new Fixture();
            var parent = fixture.Add("Day 17/ It is reset day today.", 2);
            var reply = fixture.Add("Lands tomorrow before 10am PST.", 1, parent.Id);
            fixture.Refresh();
            require(fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Items.Count == 2);
            require(fixture.Service.TryTakeAlert(out var alert) && alert?.Id == reply.Id && alert.Text.Contains("10am PST", StringComparison.Ordinal));
            require(!fixture.Service.TryTakeAlert(out _));
            require(fixture.Handler.Count == 4);
        });
        check("Reply without official matching parent cannot notify", () =>
        {
            using var fixture = new Fixture();
            var parent = fixture.Add("Day 17/ It is reset day today.", 2);
            fixture.Add("Lands tomorrow before 10am PST.", 1, parent.Id);
            fixture.EmbedOverrides[parent.Id] = Embed(parent, author: "https://x.com/another_author");
            fixture.Refresh();
            require(!fixture.Service.Snapshot.Fresh && !fixture.Service.TryTakeAlert(out _));
        });
        check("Unrelated reset request does not fetch another author's parent or block a verified announcement", () =>
        {
            using var fixture = new Fixture();
            var news = fixture.Add("Codex quota will reset tomorrow.");
            var parent = fixture.Add("An unrelated public discussion.", 5);
            fixture.Add("Reset him please.", 2, parent.Id);
            fixture.EmbedOverrides[parent.Id] = Embed(parent, author: "https://x.com/another_author");
            fixture.Refresh();
            require(fixture.Service.Snapshot.Fresh && !fixture.Service.Snapshot.Partial && fixture.Handler.Count == 2);
            require(fixture.Service.TryTakeAlert(out var alert) && alert?.Id == news.Id && !fixture.Service.TryTakeAlert(out _));
        });
        check("Failed older candidates do not erase a fully verified new announcement or notify for the failed item", () =>
        {
            foreach (var mode in new[] { "404", "author", "canceled" })
            {
                using var fixture = new Fixture();
                var news = fixture.Add("Codex quota will reset tomorrow.");
                var old = fixture.Add("Codex quota has reset. Enjoy.", 3);
                if (mode == "author") fixture.EmbedOverrides[old.Id] = Embed(old, author: "https://x.com/another_author");
                fixture.Handler.Responder = (request, cancellation) =>
                {
                    if (request.RequestUri!.Host == "publish.x.com" && Uri.UnescapeDataString(request.RequestUri.Query).Contains(old.Id, StringComparison.Ordinal))
                    {
                        if (mode == "404") return Task.FromResult(Response("{}", 404));
                        if (mode == "canceled") return Task.FromException<HttpResponseMessage>(new TaskCanceledException());
                    }
                    return fixture.Respond(request, cancellation);
                };
                fixture.Refresh();
                require(fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Partial && fixture.Service.Snapshot.StatusText.Contains("部分", StringComparison.Ordinal));
                require(fixture.Service.Snapshot.Items.Count == 1 && fixture.Service.TryTakeAlert(out var alert) && alert?.Id == news.Id);
                require(!fixture.Service.TryTakeAlert(out _));
            }
        });
        check("Requests and unrelated text never become reset notices from feed classification", () =>
        {
            using var fixture = new Fixture();
            fixture.Add("Please reset the Codex quota today.");
            fixture.Add("If Codex limits reset tomorrow, I will try again.", 2);
            fixture.Add("Codex quota reset is not done.", 3);
            fixture.Add("Codex model arrives tomorrow. New options are ready.", 4);
            fixture.Refresh();
            require(fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Items.Count == 0 && !fixture.Service.TryTakeAlert(out _));
            require(ResetNewsService.Classify("What would you like with your side of reset? It's done.") == "announced");
            require(ResetNewsService.Classify("Day 15/ Nevermind, we're still cooking... and reset. Enjoy.") == "announced");
            require(ResetNewsService.Classify("Day 17/ Bet you thought we forgot, but no, it’s reset day today.") == "upcoming");
        });
        check("Stale, old, failed, and expired feeds preserve cache but never produce new alerts", () =>
        {
            foreach (var mode in new[] { "stale", "old", "http", "expired" })
            {
                using var fixture = new Fixture();
                fixture.Add("Codex quota will reset tomorrow.");
                fixture.Refresh();
                if (mode == "expired") fixture.Now = fixture.Now.AddMinutes(16);
                else
                {
                    fixture.Now = fixture.Now.AddMinutes(6);
                    if (mode == "stale") fixture.Stale = true;
                    if (mode == "old") fixture.FetchedAt = fixture.Now.AddMinutes(-16);
                    if (mode == "http") fixture.Status = 429;
                    fixture.Refresh();
                }
                fixture.Service.ReadCached();
                require(!fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Items.Count == 1 && !fixture.Service.TryTakeAlert(out _));
            }
        });
        check("Official author, post identity, exact text and full embedded paragraph are required", () =>
        {
            foreach (var mode in new[] { "author", "id", "text", "shell", "truncated", "duplicate" })
            {
                using var fixture = new Fixture();
                var post = fixture.Add("Codex quota will reset tomorrow.");
                fixture.EmbedOverrides[post.Id] = mode switch
                {
                    "author" => Embed(post, author: "https://x.com/impostor"),
                    "id" => Embed(post, url: Url("1234567890123456789")),
                    "text" => Embed(post, text: "Codex quota has reset. Enjoy."),
                    "truncated" => Embed(post, text: "Codex quota will reset…"),
                    "duplicate" => Embed(post, html: "<blockquote><p>Codex quota will reset tomorrow.</p><p>Unverified extra text</p><a href=\"" + Url(post.Id) + "\">date</a></blockquote>"),
                    _ => Embed(post, html: "<blockquote><a href=\"" + Url(post.Id) + "\">Link only</a></blockquote>")
                };
                fixture.Refresh();
                require(!fixture.Service.Snapshot.Fresh && fixture.Service.Snapshot.Items.Count == 0 && !fixture.Service.TryTakeAlert(out _));
            }
        });
        check("Line breaks, HTML entities and link labels verify without turning markup into a notice", () =>
        {
            using var fixture = new Fixture();
            var post = fixture.Add("Day 15/ We're still cooking...\n\nand reset. Enjoy.\nhttps://t.co/testlink");
            fixture.EmbedOverrides[post.Id] = Embed(post, html: "<blockquote><p>Day 15/ We&#39;re still cooking...<br><br>and reset. Enjoy.<br><a href=\"https://t.co/testlink\">https://t.co/testlink</a></p>&mdash; Tibo <a href=\"" + Url(post.Id) + "\">date</a></blockquote>");
            fixture.Refresh();
            require(fixture.Service.Snapshot.Fresh && fixture.Service.TryTakeAlert(out var item) && item?.Kind == "announced");
            require(!fixture.Service.Snapshot.Items.Single().Text.Contains("<", StringComparison.Ordinal));
        });
        check("Cross-service manual checks throttle at 30 seconds and regular checks at 5 minutes", () =>
        {
            using var fixture = new Fixture();
            fixture.Refresh();
            using var other = fixture.Another();
            other.RefreshAsync().GetAwaiter().GetResult();
            fixture.Now = fixture.Now.AddSeconds(29);
            fixture.Refresh();
            require(fixture.Handler.Count == 1);
            fixture.Now = fixture.Now.AddSeconds(1);
            other.RefreshAsync().GetAwaiter().GetResult();
            require(fixture.Handler.Count == 2);
            fixture.Now = fixture.Now.AddMinutes(4);
            fixture.Refresh(false);
            require(fixture.Handler.Count == 2);
            fixture.Now = fixture.Now.AddMinutes(1);
            fixture.Refresh(false);
            require(fixture.Handler.Count == 3);
        });
        check("Concurrent instances share one request lock and disabling during refresh stays disabled", () =>
        {
            using var fixture = new Fixture();
            fixture.Add("Codex quota will reset tomorrow.");
            var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            fixture.Handler.Responder = async (request, cancellation) =>
            {
                if (request.RequestUri!.Host == "codex-reset.com") await gate.Task.WaitAsync(cancellation).ConfigureAwait(false);
                return await fixture.Respond(request, cancellation).ConfigureAwait(false);
            };
            var first = fixture.Service.RefreshAsync();
            using var other = fixture.Another();
            other.RefreshAsync().GetAwaiter().GetResult();
            other.SetEnabledAsync(false).GetAwaiter().GetResult();
            require(fixture.Handler.Count == 1);
            gate.SetResult(true);
            first.GetAwaiter().GetResult();
            require(!fixture.Service.Snapshot.Enabled && fixture.Service.Snapshot.Items.Count == 1 && !fixture.Service.TryTakeAlert(out _));
            other.ReadCached();
            require(!other.Snapshot.Enabled);
        });
        check("Changed callbacks run outside the state lock and can read or change preference", () =>
        {
            using var fixture = new Fixture();
            fixture.Add("Codex quota will reset tomorrow.");
            var changed = false;
            fixture.Service.Changed += snapshot =>
            {
                if (!snapshot.Fresh || changed) return;
                changed = true;
                fixture.Service.SetEnabledAsync(false).GetAwaiter().GetResult();
            };
            fixture.Refresh();
            require(changed && !fixture.Service.Snapshot.Enabled);
        });
        check("Disposing cancels in-flight HTTP without overwriting cache or publishing failure", () =>
        {
            using var fixture = new Fixture();
            fixture.Handler.Responder = async (_, cancellation) =>
            {
                await Task.Delay(Timeout.Infinite, cancellation).ConfigureAwait(false);
                throw new InvalidOperationException();
            };
            var events = 0;
            fixture.Service.Changed += _ => events++;
            var pending = fixture.Service.RefreshAsync();
            var before = File.ReadAllText(fixture.StateFile);
            fixture.Service.Dispose();
            pending.GetAwaiter().GetResult();
            require(events == 0 && File.ReadAllText(fixture.StateFile) == before);
        });
        check("Responses over the size limit and canceled requests cannot become fresh", () =>
        {
            foreach (var mode in new[] { "size", "cancel", "invalid" })
            {
                using var fixture = new Fixture();
                fixture.Handler.Responder = (_, _) => mode == "cancel" ? Task.FromException<HttpResponseMessage>(new TaskCanceledException())
                    : Task.FromResult(Response(mode == "size" ? new string('x', 1024 * 1024 + 1) : "{invalid}"));
                fixture.Refresh();
                require(!fixture.Service.Snapshot.Fresh && !fixture.Service.TryTakeAlert(out _));
            }
        });
        check("Feed URL injection, invalid time and unknown profile are rejected before official lookup", () =>
        {
            foreach (var mode in new[] { "url", "time", "profile", "future" })
            {
                using var fixture = new Fixture();
                var post = fixture.Add("Codex quota will reset tomorrow.");
                var feed = JsonNode.Parse(fixture.Feed())!;
                if (mode == "url") feed["tweets"]![0]!["url"] = "https://example.invalid/private/" + post.Id;
                else if (mode == "profile") feed["profile"]!["handle"] = "another";
                else feed["tweets"]![0]!["at"] = (mode == "future" ? fixture.Now.AddDays(1) : fixture.Now.AddHours(-5)).ToString("O");
                fixture.FeedOverride = feed.ToJsonString();
                fixture.Refresh();
                require(!fixture.Service.Snapshot.Fresh && fixture.Handler.Count == 1 && !fixture.Service.TryTakeAlert(out _));
            }
        });
        check("Corrupt own state is preserved and cannot silently become a fresh notification", () =>
        {
            using var fixture = new Fixture();
            Directory.CreateDirectory(fixture.DirectoryPath);
            File.WriteAllText(fixture.StateFile, "{unreadable settings}");
            var before = File.ReadAllText(fixture.StateFile);
            fixture.Service.ReadCached();
            require(!fixture.Service.Snapshot.Fresh && !fixture.Service.TryTakeAlert(out _));
            var rejected = false;
            try { fixture.Service.SetEnabledAsync(false).GetAwaiter().GetResult(); } catch (JsonException) { rejected = true; }
            require(rejected && File.ReadAllText(fixture.StateFile) == before && fixture.Handler.Count == 0);
        });
    }
}
