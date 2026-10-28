using System;
using System.IO;
using System.Linq;

namespace AIFirst.Workspace;

internal static class ReleaseHighlightsTests
{
    internal static void Run(Action<string, Action> check, Action<bool> require)
    {
        check("Bundled release highlights match this application version and contain bounded plain text", () =>
        {
            var notes = ReleaseHighlights.Load(Path.Combine(AppContext.BaseDirectory,"assets","whats-new.json"),UpdateClient.CurrentVersion);
            require(notes is not null && notes.Items.Count is >=1 and <=3 && notes.Url == UpdateClient.Repository + "/releases/tag/v" + UpdateClient.CurrentVersion);
        });
        var directory = Path.Combine(Path.GetTempPath(),"ai-first-highlights-"+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(directory);
        try
        {
            check("Release acknowledgement survives restart, retains older versions and permits a new version", () =>
            {
                var state = new ReleaseHighlightsState(directory,"0.3.19"); require(state.ShouldShow && state.Acknowledge());
                require(!new ReleaseHighlightsState(directory,"0.3.19").ShouldShow);
                var next = new ReleaseHighlightsState(directory,"0.3.20"); require(next.ShouldShow && next.Acknowledge());
                require(!new ReleaseHighlightsState(directory,"0.3.19").ShouldShow && !new ReleaseHighlightsState(directory,"0.3.20").ShouldShow);
            });
            check("Unknown, malformed and oversized acknowledgement files suppress interruption and remain unchanged", () =>
            {
                var file = Path.Combine(directory,"whats-new.json");
                foreach(var json in new[]{"broken", "{\"schema\":2,\"seen\":[]}", "{\"schema\":1,\"seen\":[],\"path\":\"other\"}","{\"schema\":1,\"seen\":[\"../other\"]}",new string('x',17000)})
                { File.WriteAllText(file,json); var state = new ReleaseHighlightsState(directory,"0.3.19"); require(!state.ShouldShow && !state.Acknowledge() && File.ReadAllText(file)==json); }
                File.Delete(file); Directory.CreateDirectory(file);
                var blocked = new ReleaseHighlightsState(directory,"0.3.19"); require(!blocked.ShouldShow && !blocked.Acknowledge() && Directory.Exists(file)); Directory.Delete(file);
            });
            check("Missing or mismatched highlights cannot substitute another release or execute HTML", () =>
            {
                var file=Path.Combine(directory,"notes.json");
                var original=File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"assets","whats-new.json"));
                foreach(var json in new[]{"broken",original.Replace("\"schema\": 1","\"schema\": 2"),original.Replace(UpdateClient.CurrentVersion,"9.9.9"),original.Replace("\"items\": [","\"items\": null,\"items\": [")})
                { File.WriteAllText(file,json); require(ReleaseHighlights.Load(file,UpdateClient.CurrentVersion) is null); }
                File.WriteAllText(file,original.Replace("更新内容，一眼看懂","<script>do_not_run()</script>"));
                require(ReleaseHighlights.Load(file,UpdateClient.CurrentVersion)?.Items.First().Title.Contains("<script>")==true);
            });
        }
        finally { foreach(var name in new[]{"whats-new.json","notes.json"}) File.Delete(Path.Combine(directory,name)); Directory.Delete(directory); }
    }
}
