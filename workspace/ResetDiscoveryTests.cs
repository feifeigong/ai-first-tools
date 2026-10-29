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
        check("Historical editorial summaries discover IDs but only the X original determines their meaning", () =>
        {
            using var f = new Fixture(true);
            var reset = f.Historical("The reset has been processed. Enjoy!", 96);
            var card = f.Historical("Loaded one banked reset into every paid Codex account.", 72);
            var unrelated = f.Historical("A new editor feature has shipped.", 48);
            f.HistoryTextOverrides[reset.Id] = "Full reset for users, picked by community vote: the reset has been processed.";
            f.HistoryTextOverrides[card.Id] = "Milestone: one banked reset loaded, alongside a new model.";
            f.HistoryTextOverrides[unrelated.Id] = "Codex quota has reset. Enjoy.";
            f.Refresh();
            require(f.Service.Snapshot.Items.Single(item => item.Id == reset.Id).Kind == "announced");
            require(f.Service.Snapshot.Items.Single(item => item.Id == card.Id).Kind == "banked");
            require(f.Service.Snapshot.Items.All(item => item.Id != unrelated.Id) && !f.Service.TryTakeAlert(out _));
        });
        check("An unfamiliar language flagged by a discovery source keeps verified reset context but never becomes confirmation or an alert", () =>
        {
            using var f = new Fixture();
            var root = f.Add("Day 23/ Today is a reset.", 3);
            var reply = f.Add("C’est fait. À demain pour des nouvelles.", 1, root.Id);
            var feed = JsonNode.Parse(f.Feed())!;
            foreach (var row in feed["tweets"]!.AsArray())
                if (row!["id"]!.GetValue<string>() == reply.Id) row["tibo_lane"] = "reset_related";
            f.FeedOverride = feed.ToJsonString();
            f.Refresh();
            var pending = f.Service.Snapshot.Items.Single(item => item.Id == reply.Id);
            require(pending.Kind == "uncertain" && pending.GroupId == reply.Id && pending.Text.Contains(root.Text) && pending.Text.Contains(reply.Text));
            var calendar = ResetCalendarModel.Events(f.Service.Snapshot.Items, f.Now);
            require(calendar.Count == 2 && calendar.Any(item => item.Id == root.Id && !item.Completed) && calendar.Any(item => item.Id == reply.Id && item.State == "uncertain"));
            require(f.Service.TryTakeAlert(out var alert) && alert?.Id == root.Id && !f.Service.TryTakeAlert(out _));
        });
        check("An And-it-is-done quote confirms its verified reset chain even when tomorrow mentions unrelated good news", () =>
        {
            foreach (var phrase in new[] { "And it's done. See you tomorrow for some good news.", "And it’s done. See you tomorrow for some good news.", "And it is done. See you tomorrow." })
            {
                using var f = new Fixture(true);
                var root = f.Historical("Day 23/ Just kidding, today is a reset.", 3);
                var timing = f.Historical("Lands by midnight PST.", 2);
                var done = f.Historical(phrase, 1);
                f.Parents[timing.Id] = root.Id;
                f.Quotes[done.Id] = timing.Id;
                f.Refresh();
                var result = f.Service.Snapshot.Items.Single(item => item.Id == done.Id);
                require(result.Kind == "announced" && result.GroupId == root.Id && !result.Historical);
                var calendar = ResetCalendarModel.Events(f.Service.Snapshot.Items, f.Now);
                require(calendar.Count == 1 && calendar[0].Completed && calendar[0].Id == done.Id);
                require(f.Service.TryTakeAlert(out var alert) && alert?.Id == done.Id && !f.Service.TryTakeAlert(out _));
                require(ResetNewsService.Classify(phrase) is null);
            }
        });
        check("A completion phrase without a verified reset quote cannot turn a product announcement into a reset", () =>
        {
            foreach (var phrase in new[] { "And it's done. See you tomorrow for some good news.", "And it's not done. See you tomorrow.", "And it’s done? See you tomorrow." })
            {
                using var f = new Fixture();
                var product = f.Add("A new editor feature has shipped.", 3);
                var reply = f.Add(phrase, 1);
                f.Quotes[reply.Id] = product.Id;
                f.Refresh();
                require(f.Service.Snapshot.Items.All(item => item.Id != reply.Id) && !f.Service.TryTakeAlert(out _));
            }
        });
        check("A previously misclassified completion is rechecked after a rule upgrade while notification acknowledgements survive", () =>
        {
            using var f = new Fixture(true);
            var root = f.Historical("Day 23/ Today is a reset.", 3);
            var done = f.Historical("And it's done. See you tomorrow for some good news.", 1);
            f.Quotes[done.Id] = root.Id;
            f.Refresh();
            var saved = JsonNode.Parse(System.IO.File.ReadAllText(f.StateFile))!;
            saved["discoveryRevision"] = 2;
            foreach (var item in saved["items"]!.AsArray())
                if (item!["id"]!.GetValue<string>() == done.Id) item["kind"] = "upcoming";
            saved["historyChecked"] = new JsonObject { [done.Id] = f.Now.ToString("O") };
            saved["historyNextPage"] = f.Now.AddHours(6).ToString("O");
            saved["seen"] = new JsonObject { [done.Id] = f.Now.ToString("O") };
            saved["seenStages"] = new JsonObject { [root.Id + ":upcoming"] = f.Now.ToString("O") };
            saved["pending"] = new JsonArray();
            System.IO.File.WriteAllText(f.StateFile, saved.ToJsonString());
            f.Now = f.Now.AddMinutes(6);
            using var next = f.Another();
            next.RefreshAsync().GetAwaiter().GetResult();
            require(next.Snapshot.Items.Single(item => item.Id == done.Id).Kind == "announced");
            require(ResetCalendarModel.Events(next.Snapshot.Items, f.Now).Single().Completed);
            require(!next.TryTakeAlert(out _));
            var updated = JsonNode.Parse(System.IO.File.ReadAllText(f.StateFile))!;
            require(updated["seen"]![done.Id] is not null && updated["seenStages"]![root.Id + ":upcoming"] is not null);
        });
        check("A discovery reply hint cannot override the officially verified parent relationship", () =>
        {
            foreach (var phrase in new[] { "Lands tomorrow before 10am PST.", "Codex quota has reset. Enjoy." })
            {
                using var f = new Fixture();
                var claimed=f.Add("Day 17/ Reset",3);
                var actual=f.Add("Day 18/ Reset",2);
                var reply=f.Add(phrase,1,claimed.Id);
                f.Parents[reply.Id]=actual.Id;
                f.Refresh();
                require(f.Service.Snapshot.Partial && f.Service.Snapshot.Items.All(item=>item.Id!=reply.Id));
            }
        });
        check("Feed recovery does not lose a recent officially verified secondary-source message or repeat its alert", () =>
        {
            using var f=new Fixture(true) { Status=503 };
            var news=f.Historical("Codex quota has reset. Enjoy.",1);
            f.Refresh();
            require(!f.Service.Snapshot.Fresh && f.Service.Snapshot.Items.Single().Id==news.Id && !f.Service.TryTakeAlert(out _));
            f.Status=200;f.Now=f.Now.AddMinutes(6);
            using var next=f.Another();next.RefreshAsync().GetAwaiter().GetResult();
            require(next.Snapshot.Fresh && next.TryTakeAlert(out var alert) && alert?.Id==news.Id && !next.TryTakeAlert(out _));
        });
        check("Midnight uses the end of the posting Pacific day and retains explicit PST summer ambiguity", () =>
        {
            var item = new ResetNewsItem("2114200291319124163", "", "Day 20/ Rest and reset\n\nBy midnight PST", "upcoming",
                DateTimeOffset.Parse("2026-10-25T03:40:04Z"), Url("2114200291319124163"));
            var view = ResetNewsPresentation.From(item,DateTimeOffset.Parse("2026-10-25T04:00:00Z"));
            require(view.TimeText=="北京时间 10 月 25 日 16:00 前" && view.TimeNote.Contains("15:00 前"));
            var regional = ResetNewsPresentation.From(item with { Text="By midnight PT" },DateTimeOffset.Parse("2026-10-25T04:00:00Z"));
            require(regional.TimeText=="北京时间 10 月 25 日 15:00 前");
            require(ResetNewsPresentation.From(item with { Text="By midnight" }).TimeText=="具体时间待公布");
        });
        check("Legacy failed-check cache is revalidated without erasing prior announcements or seen state", () =>
        {
            using var f = new Fixture(true);
            f.Refresh();
            var news=f.Historical("Day 21/ But today is a reset.",1);
            var state=JsonNode.Parse(System.IO.File.ReadAllText(f.StateFile))!;
            state["discoveryRevision"]=0;
            state["historyChecked"]=new JsonObject { [news.Id]=f.Now.ToString("O") };
            state["historyNextPage"]=f.Now.AddHours(6).ToString("O");
            state["seen"]=new JsonObject { ["2107578625419866469"]=f.Now.ToString("O") };
            System.IO.File.WriteAllText(f.StateFile,state.ToJsonString());
            f.Now=f.Now.AddMinutes(6);
            using var next=f.Another();next.RefreshAsync().GetAwaiter().GetResult();
            require(next.Snapshot.Items.Single().Id==news.Id && next.TryTakeAlert(out var alert) && alert?.Id==news.Id);
            var updated=JsonNode.Parse(System.IO.File.ReadAllText(f.StateFile))!;
            require(updated["seen"]!["2107578625419866469"] is not null);
        });
        check("Weekend completion follows verified quote and reply even when the primary timeline omits it", () =>
        {
            using var f = new Fixture(true);
            var root = f.Historical("Day 20/ Rest and reset", 3);
            var timing = f.Historical("By midnight PST", 2);
            var done = f.Historical("It is all propagated. Enjoy some mad codexing tomorrow. Fun week ahead too.", 1);
            f.Parents[timing.Id] = root.Id;
            f.Quotes[done.Id] = timing.Id;
            f.Refresh();
            require(f.Service.Snapshot.Items.Single(item => item.Id == done.Id).Kind == "announced");
            require(f.Service.Snapshot.Items.Single(item => item.Id == done.Id).GroupId == root.Id);
            require(f.Service.Snapshot.Items.Single(item => item.Id == timing.Id).Kind == "upcoming");
            require(f.Service.TryTakeAlert(out var alert) && alert?.Id == done.Id && !f.Service.TryTakeAlert(out _));
            foreach (var phrase in new[] { "Day 21/ Wonder what happens next. But today is a reset.", "Day 20/ Rest and reset" })
                require(ResetNewsService.Classify(phrase) == "upcoming");
            foreach (var phrase in new[] { "Day 21/ Is today a reset?", "Day 21/ Today is not a reset.", "Day 21/ I wish today is a reset.", "Day 21/ Today is a password reset.", "It is all propagated. Enjoy tomorrow." })
                require(ResetNewsService.Classify(phrase) is null);
        });
        check("One corrupt historical row is quarantined without accepting it or discarding valid official evidence", () =>
        {
            using var f = new Fixture(true);
            var bad = f.Historical("Day 17/ Reset", 8);
            var valid = f.Historical("Codex quota has reset. Enjoy.", 1);
            f.Handler.Responder = async (request, cancellation) =>
            {
                var response = await f.Respond(request, cancellation);
                if (request.RequestUri!.Host != "www.codexreset-news.com") return response;
                var data = JsonNode.Parse(await response.Content.ReadAsStringAsync(cancellation))!;
                data["items"]![0]!["published_at"] = bad.At.AddHours(7).ToString("O");
                return Response(data.ToJsonString());
            };
            f.Refresh();
            require(f.Service.Snapshot.Fresh && f.Service.Snapshot.Partial && f.Service.Snapshot.Items.Single().Id == valid.Id);
            require(!f.Handler.Requests.Any(uri => Uri.UnescapeDataString(uri.Query).Contains("/status/" + bad.Id)));
            require(f.Service.TryTakeAlert(out var alert) && alert?.Id == valid.Id);
        });
        check("Transient official lookup failures retry in minutes across restart rather than being marked checked for a day", () =>
        {
            using var f = new Fixture(true);
            var news = f.Historical("Codex quota has reset. Enjoy.", 1);
            f.Handler.Responder = (request, cancellation) => request.RequestUri!.Host == "publish.x.com" ? Task.FromResult(Response("{}",503)) : f.Respond(request,cancellation);
            f.Refresh();
            require(f.Service.Snapshot.Items.Count == 0 && !f.Service.TryTakeAlert(out _));
            f.Handler.Responder = f.Respond;
            f.Now = f.Now.AddMinutes(6);
            using var next = f.Another();
            next.RefreshAsync().GetAwaiter().GetResult();
            require(next.Snapshot.Fresh && next.Snapshot.Items.Single().Id == news.Id);
            require(next.TryTakeAlert(out var alert) && alert?.Id == news.Id);
        });
        check("Latest discovery page is revisited while older pagination is waiting", () =>
        {
            using var f = new Fixture(true) { HistoryPageSize = 1 };
            f.Historical("Day 6/ Reset",48);
            f.Historical("Day 8/ Reset",49);
            f.Refresh();
            var news = f.Historical("Day 21/ But today is a reset.",1);
            f.HistoryPosts.Remove(news); f.HistoryPosts.Insert(0,news);
            f.Now = f.Now.AddMinutes(6);
            using var next = f.Another();
            next.RefreshAsync().GetAwaiter().GetResult();
            require(next.Snapshot.Items.Any(item => item.Id == news.Id));
            require(next.TryTakeAlert(out var alert) && alert?.Id == news.Id);
        });
        check("Official relation metadata conflicts cannot turn an unrelated completion into a reset", () =>
        {
            foreach (var field in new[] { "text", "created_at", "in_reply_to_status_id_str" })
            {
                using var f = new Fixture(true);
                var root = f.Historical("Day 20/ Rest and reset",3);
                var timing = f.Historical("By midnight PST",2);
                var done = f.Historical("It is all propagated. Enjoy tomorrow.",1);
                f.Parents[timing.Id]=root.Id; f.Quotes[done.Id]=timing.Id;
                f.Handler.Responder = async (request,cancellation) =>
                {
                    var response=await f.Respond(request,cancellation);
                    if (request.RequestUri!.Host!="cdn.syndication.twimg.com" || !request.RequestUri.Query.Contains("id="+timing.Id)) return response;
                    var data=JsonNode.Parse(await response.Content.ReadAsStringAsync(cancellation))!;
                    if (field=="in_reply_to_status_id_str") data[field]=done.Id;
                    else data["parent"]![field]=field=="text" ? "An unrelated product update." : f.Now.ToString("O");
                    return Response(data.ToJsonString());
                };
                f.Refresh();
                require(f.Service.Snapshot.Partial && f.Service.Snapshot.Items.All(item=>item.Id!=done.Id));
            }
        });
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
        check("Discovery source age cannot hide an officially verified recent post; old backfill never alerts", () =>
        {
            using var f = new Fixture(true);
            f.Historical("Day 6/ Reset", 72);
            var recent = f.Historical("Codex quota has reset. Enjoy.", 1);
            f.Historical("Day 3/ Loading a banked reset in paid accounts. See you tomorrow!", 96);
            f.Refresh();
            require(f.Service.Snapshot.Fresh && f.Service.Snapshot.Items.Count == 3 && f.Service.Snapshot.Items.Count(item => item.Historical) == 2);
            require(f.Service.Snapshot.Items.Count(item => item.Kind == "banked") == 1 && f.Service.TryTakeAlert(out var alert) && alert?.Id == recent.Id);
            require(!f.Service.TryTakeAlert(out _));
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
        check("Historical summaries never override the original kind or a wrong original author", () =>
        {
            foreach (var mode in new[] { "text", "author" })
            {
                using var f = new Fixture(true);
                var post = f.Historical("Codex quota has reset.");
                f.EmbedOverrides[post.Id] = mode == "text" ? Embed(post, text: "Codex quota will reset tomorrow.") : Embed(post, author: "https://x.com/foreign");
                f.Refresh();
                require(mode == "text" ? f.Service.Snapshot.Items.Single().Kind == "upcoming" : f.Service.Snapshot.Items.Count == 0);
                require(!f.Service.TryTakeAlert(out _));
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
