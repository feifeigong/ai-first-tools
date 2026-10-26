using System;
using System.Windows.Controls;

namespace AIFirst.Workspace;

internal static class ResetNewsPresentationTests
{
    private static ResetNewsItem Item(string text, string at = "2026-10-22T06:55:54Z", string kind = "upcoming") =>
        new("2113162413008884099", "old cached English or Chinese summary", text, kind, DateTimeOffset.Parse(at), "https://x.com/thsottiaux/status/2113162413008884099");
    private static readonly DateTimeOffset Before = DateTimeOffset.Parse("2026-10-22T09:00:00Z");

    internal static void Run(Action<string, Action> check, Action<bool> require)
    {
        check("Published Pacific date anchors tomorrow rather than UTC or Beijing date, preserving before and PST ambiguity", () =>
        {
            var item = Item("Day 17/ It is reset day today.\n\nLands tomorrow before 10am PST.");
            var view = ResetNewsPresentation.From(item, Before);
            require(view.TimeText == "北京时间 10 月 23 日 02:00 前");
            require(view.TimeNote.Contains("01:00 前") && view.TimeNote.Contains("PST"));
            require(!view.Description.Contains("Day 17") && !view.Description.Contains("Lands"));
        });
        check("Pacific regional time follows summer and winter offsets, explicit PDT is not treated as PST", () =>
        {
            require(ResetNewsPresentation.From(Item("Lands tomorrow before 10am PT."), Before).TimeText == "北京时间 10 月 23 日 01:00 前");
            require(ResetNewsPresentation.From(Item("Lands tomorrow before 10am PDT."), Before).TimeText == "北京时间 10 月 23 日 01:00 前");
            var winter = ResetNewsPresentation.From(Item("Lands tomorrow before 10am PT.", "2026-12-20T06:00:00Z"), Before);
            require(winter.TimeText == "北京时间 12 月 21 日 02:00 前");
        });
        check("UTC absolute dates, twelve-hour boundaries, explicit month dates and relative year rollover convert correctly", () =>
        {
            foreach (var entry in new[]
            {
                (Item("Reset on 2026-10-23 at 00:30 UTC."), "北京时间 10 月 23 日 08:30"),
                (Item("Reset tomorrow at 12am UTC."), "北京时间 10 月 23 日 08:00"),
                (Item("Reset tomorrow at 12pm UTC."), "北京时间 10 月 23 日 20:00"),
                (Item("Reset on October 23, 2026 before 10am PST."), "北京时间 10 月 24 日 02:00 前"),
                (Item("Reset tomorrow at 10am PT.", "2027-01-01T06:00:00Z"), "北京时间 1 月 2 日 02:00")
            })
            {
                var actual = ResetNewsPresentation.From(entry.Item1, Before).TimeText;
                if (actual != entry.Item2) throw new InvalidOperationException(entry.Item1.Text + " -> " + actual + "; expected " + entry.Item2);
            }
        });
        check("Durations use publication time, and expired estimates never become completed announcements", () =>
        {
            var duration = ResetNewsPresentation.From(Item("Codex reset in 2 hours."), Before);
            require(duration.TimeText == "北京时间约 10 月 22 日 16:55");
            var expired = ResetNewsPresentation.From(Item("Lands tomorrow before 10am PT."), Before.AddDays(2));
            require(expired.TimeNote.Contains("原计划时间已过") && expired.TimeNote.Contains("实际额度以 Codex 显示为准") && expired.Summary.Contains("预告"));
        });
        check("Unclear clocks, time ranges and DST gaps or repeated hours do not invent a unique time", () =>
        {
            foreach (var text in new[] { "Reset soon.", "Reset tomorrow at 10am.", "Reset at 10am PT.", "Reset tomorrow between 9 and 10am PT.",
                "Reset tomorrow at 25:00 UTC.", "Reset tomorrow at 10am PT and 12pm ET.", "Reset tomorrow from 9 to 10am PT.", "Reset tomorrow not before 10am PT.",
                "Reset tomorrow at 10am UTC+2.", "Reset tomorrow; webinar at 10am PT." })
                require(ResetNewsPresentation.From(Item(text), Before).TimeText == "具体时间待公布");
            require(ResetNewsPresentation.From(Item("Reset tomorrow at 2:30am PT.", "2026-03-08T06:00:00Z"), Before).TimeText == "具体时间待公布");
            require(ResetNewsPresentation.From(Item("Reset tomorrow at 1:30am PT.", "2026-11-01T06:00:00Z"), Before).TimeText == "具体时间待公布");
        });
        check("Completed announcements and popup content stay Chinese and do not invent a future reset time", () =>
        {
            var item = Item("Codex quota has reset. Enjoy.", kind: "announced");
            var view = ResetNewsPresentation.From(item, Before);
            require(view.TimeText == "" && view.Description.Contains("实际显示"));
            var window = new ResetNoticeWindow(Item("Lands tomorrow before 10am PST."), () => System.Threading.Tasks.Task.FromResult(false));
            require(((TextBlock)window.FindName("NoticeTime")).Text.Contains("北京时间"));
            require(!((TextBlock)window.FindName("NoticeExcerpt")).Text.Contains("Lands"));
            window.Close();
        });
    }
}
