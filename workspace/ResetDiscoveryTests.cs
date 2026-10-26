using System;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal static partial class ResetNewsTests
{
    private static void RunDiscovery(Action<string, Action> check, Action<bool> require)
    {
        check("Day 18 declaration and its later timing reply are both retained and elapsed timing cannot hide completion", () =>
        {
            using var f = new Fixture();
            f.Now = DateTimeOffset.Parse("2026-10-23T10:00:00Z");
            var root = f.Add("Day 18/ Decisions API is GA, OpenResponses joined the Linux Foundation, we shipped some performance improvements and Uber is going all-in on codex & work. But yes… that’s a reset!", 5);
            var timing = f.Add("Landing tomorrow before 10am PST together with a small ship.", 4, root.Id);
            f.Refresh();
            require(f.Service.Snapshot.Items.Single(item => item.Id == root.Id).Kind == "announced");
            require(f.Service.Snapshot.Items.Single(item => item.Id == timing.Id).Kind == "upcoming");
            var calendar = ResetCalendarModel.Events(f.Service.Snapshot.Items, f.Now);
            require(calendar.Count == 2 && calendar.Any(item => item.Completed && item.Date == new DateTime(2026,10,23))
                && calendar.Any(item => item.State == "upcoming" && item.Date == new DateTime(2026,10,24)));
            f.Now = DateTimeOffset.Parse("2026-10-23T20:00:00Z");
            f.Refresh();
            require(f.Service.TryTakeAlert(out var alert) && alert?.Id == root.Id && alert.Kind == "announced");
            require(!f.Service.TryTakeAlert(out _));
            require(ResetCalendarModel.Events(f.Service.Snapshot.Items,f.Now).Any(item => item.State == "past-preview"));
            foreach (var text in new[] { "Day 18/ Is that a reset?", "Day 18/ That's not a reset.", "Day 18/ I wish that's a reset!" })
                require(ResetNewsService.Classify(text) is null);
            require(ResetNewsService.Classify("Day 18/ Tomorrow that's a reset!") == "upcoming");
        });
        check("Real public reset wording is recognized and banked grants never inherit tomorrow's quota reset", () =>
        {
            foreach (var text in new[] { "Day 6/ Reset", "Day 8/ Reset", "Day 13/ Le limit reset", "The reports of my reset button being lost are greatly exaggerated\nDay 10/ Reset" })
                require(ResetNewsService.Classify(text) == "upcoming");
            foreach (var text in new[] { "Put the reset in the bag. All propagated.", "The reset has been processed. Enjoy!", "Day 15/ Nevermind, we're still cooking... and reset. Enjoy." })
                require(ResetNewsService.Classify(text) == "announced");
            require(ResetNewsService.Classify("Day 3/ Loading a banked reset in everyone's paid accounts. See you again tomorrow!") == "banked");
            require(ResetNewsService.Classify("Codex reset will be all propagated tomorrow.") == "upcoming");
            foreach (var text in new[] { "Done", "Done and dusted", "All propagated", "Has the Codex reset all propagated?", "Please grant a banked reset.", "Are we loading a banked reset?", "Day 13/ No reset today.", "The password reset has been processed.", "The reset icon has propagated to all screens." })
                require(ResetNewsService.Classify(text) is null);
        });
        check("Landing reply and an officially quoted completion resolve the exact reset chain", () =>
        {
            using var f = new Fixture();
            var root = f.Add("Day 10/ Reset", 3);
            var timing = f.Add("Landing within the next 2 hours", 2, root.Id);
            var done = f.Add("Done and dusted", 1);
            f.Quotes[done.Id] = timing.Id;
            f.Refresh();
            require(f.Service.Snapshot.Fresh && f.Service.Snapshot.Items.Count == 3);
            require(f.Service.Snapshot.Items.Single(item => item.Id == done.Id).GroupId == root.Id);
            require(f.Service.TryTakeAlert(out var alert) && alert?.Id == done.Id && alert.Kind == "announced");
        });
        check("Stale historical discovery fills the calendar but never queues old or recent historical alerts", () =>
        {
            using var f = new Fixture(true);
            f.Historical("Day 6/ Reset", 72);
            f.Historical("Codex quota has reset. Enjoy.", 1);
            f.Historical("Day 3/ Loading a banked reset in paid accounts. See you tomorrow!", 96);
            f.Refresh();
            require(f.Service.Snapshot.Fresh && f.Service.Snapshot.Items.Count == 3 && f.Service.Snapshot.Items.All(item => item.Historical));
            require(f.Service.Snapshot.Items.Count(item => item.Kind == "banked") == 1 && !f.Service.TryTakeAlert(out _));
        });
        check("Event discovery uses the original post ID time and ignores operator completion labels", () =>
        {
            using var f = new Fixture(true);
            var post = f.Historical("Day 6/ Reset", 72);
            f.HistoryPosts.Clear();
            f.Posts.Add(post);
            f.EventPosts.Add(post);
            var data = JsonNode.Parse(f.Feed())!;
            data["tweets"] = new JsonArray();
            f.FeedOverride = data.ToJsonString();
            f.Refresh();
            var retained = f.Service.Snapshot.Items.Single();
            require(retained.Kind == "upcoming" && Math.Abs((retained.PublishedAt - post.At).TotalSeconds) < 1 && retained.Historical);
        });
        check("Truncated historical originals are explicitly pending and are never accepted as completed", () =>
        {
            using var f = new Fixture(true);
            var post = f.Historical("Codex quota reset has been processed. Enjoy.");
            f.EventPosts.Add(post);
            f.EmbedOverrides[post.Id] = Embed(post, text: "Codex quota reset has been…");
            f.Refresh();
            require(f.Service.Snapshot.Items.Single().Kind == "uncertain" && !f.Service.TryTakeAlert(out _));
        });
        check("Mismatching historical body and author remain rejected even if archive calls them completed", () =>
        {
            foreach (var mode in new[] { "text", "author" })
            {
                using var f = new Fixture(true);
                var post = f.Historical("Codex quota has reset.");
                f.EmbedOverrides[post.Id] = mode == "text" ? Embed(post, text: "Codex quota will reset tomorrow.") : Embed(post, author: "https://x.com/foreign");
                f.Refresh();
                require(f.Service.Snapshot.Items.Count == 0 && !f.Service.TryTakeAlert(out _));
            }
        });
        check("Standalone Done is pending history, not proof of a reset, and a product quote is irrelevant", () =>
        {
            using var f = new Fixture(true);
            var done = f.Historical("Done", 48);
            var product = f.Add("A new editor feature has shipped.", 50);
            var other = f.Historical("Done and dusted", 47);
            f.Quotes[other.Id] = product.Id;
            f.Refresh();
            require(f.Service.Snapshot.Items.Count == 1 && f.Service.Snapshot.Items.Single().Id == done.Id && f.Service.Snapshot.Items.Single().Kind == "uncertain");
        });
        check("Invalid official quote identity cannot manufacture a reset completion association", () =>
        {
            foreach (var field in new[] { "id_str", "text", "created_at", "author" })
            {
                using var f = new Fixture();
                var root = f.Add("Day 10/ Reset", 2);
                var done = f.Add("Done", 1);
                f.Quotes[done.Id] = root.Id;
                f.Handler.Responder = async (request, cancellation) =>
                {
                    var response = await f.Respond(request, cancellation);
                    if (request.RequestUri!.Host != "cdn.syndication.twimg.com") return response;
                    var json = JsonNode.Parse(await response.Content.ReadAsStringAsync(cancellation))!;
                    if (field == "author") json["quoted_tweet"]!["user"]!["screen_name"] = "foreign";
                    else json[field] = field == "created_at" ? f.Now.ToString("O") : "conflict";
                    return Response(json.ToJsonString());
                };
                f.Refresh();
                require(f.Service.Snapshot.Partial && f.Service.Snapshot.Items.All(item => item.Id != done.Id));
            }
        });
        check("Live evidence is checked before a failing history request and can still notify", () =>
        {
            using var f = new Fixture(true);
            var live = f.Add("Codex quota will reset tomorrow.");
            f.Handler.Responder = (request, cancellation) => request.RequestUri!.Host == "www.codexreset-news.com" ? Task.FromResult(Response("{}", 503)) : f.Respond(request, cancellation);
            f.Refresh();
            require(f.Service.Snapshot.Fresh && f.Service.TryTakeAlert(out var item) && item?.Id == live.Id);
            require(f.Handler.Requests[1].Host == "publish.x.com" && f.Handler.Requests.Last().Host == "www.codexreset-news.com");
        });
        check("An expired live feed does not block verified history or authorize any alert", () =>
        {
            using var f = new Fixture(true) { Stale = true };
            f.Historical("Codex quota has reset. Enjoy.");
            f.Refresh();
            require(!f.Service.Snapshot.Fresh && f.Service.Snapshot.Items.Count == 1 && f.Service.Snapshot.Items.Single().Historical && !f.Service.TryTakeAlert(out _));
        });
        check("Historical work continues across restarts without starving older candidates or notifying", () =>
        {
            using var f = new Fixture(true);
            for (var i = 0; i < 40; i++) f.Historical("Codex quota has reset. Enjoy.", 48 + i);
            f.Refresh();
            require(f.Service.Snapshot.Items.Count == 24);
            f.Now = f.Now.AddMinutes(6);
            using var restarted = f.Another();
            restarted.RefreshAsync().GetAwaiter().GetResult();
            require(restarted.Snapshot.Items.Count == 40 && !restarted.TryTakeAlert(out _));
            require(f.Handler.Requests.Count(uri => uri.Host == "publish.x.com") == 40);
        });
        check("History pagination resumes its stored offset and does not claim earlier history is complete", () =>
        {
            using var f = new Fixture(true) { HistoryPageSize = 2 };
            for (var i = 0; i < 4; i++) f.Historical("Codex quota has reset. Enjoy.", 48 + i);
            f.Refresh();
            require(f.Service.Snapshot.Items.Count == 2);
            f.Now = f.Now.AddMinutes(6);
            using var restarted = f.Another();
            restarted.RefreshAsync().GetAwaiter().GetResult();
            require(restarted.Snapshot.Items.Count == 4 && !restarted.TryTakeAlert(out _));
            require(f.Handler.Requests.Any(uri => uri.Host == "www.codexreset-news.com" && uri.Query.Contains("offset=2")));
        });
        check("History URL injection and nonadvancing pagination cannot add or request arbitrary evidence", () =>
        {
            foreach (var mode in new[] { "url", "offset" })
            {
                using var f = new Fixture(true);
                f.Historical("Codex quota has reset.");
                f.Handler.Responder = async (request, cancellation) =>
                {
                    var response = await f.Respond(request, cancellation);
                    if (request.RequestUri!.Host != "www.codexreset-news.com") return response;
                    var data = JsonNode.Parse(await response.Content.ReadAsStringAsync(cancellation))!;
                    if (mode == "url") data["items"]![0]!["url"] = "https://example.invalid/private";
                    else data["next_offset"] = 0;
                    return Response(data.ToJsonString());
                };
                f.Refresh();
                require(f.Service.Snapshot.Fresh && f.Service.Snapshot.Items.Count == 0 && f.Handler.Requests.All(uri => uri.Host != "publish.x.com"));
            }
        });
    }
}
