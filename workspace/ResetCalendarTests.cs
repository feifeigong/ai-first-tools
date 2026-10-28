using System;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;

namespace AIFirst.Workspace;

internal static class ResetCalendarTests
{
    private static readonly DateTimeOffset Now = DateTimeOffset.Parse("2026-10-23T01:09:00Z");
    private static ResetNewsItem Item(string id, string kind, string text, string at, string group = "") =>
        new(id, "Synthetic", text, kind, DateTimeOffset.Parse(at), "https://x.com/thsottiaux/status/" + id, GroupId: group);
    private static ResetNewsItem Preview() => Item("2113162413008884099", "upcoming", "Codex reset day today.\n\nLands tomorrow before 10am PST.", "2026-10-22T06:55:54Z", "2113162277688070445");

    internal static void Run(Action<string, Action> check, Action<bool> require)
    {
        check("Banked grants and uncertain history have independent calendar labels and are never quota completions", () =>
        {
            var banked = Item("2107913674593644711", "banked", "Loading a banked reset in paid accounts.", "2026-10-07T19:19:17Z");
            var pending = Item("2107676072871600470", "uncertain", "Codex reset has been…", "2026-10-07T03:35:09Z");
            var records = ResetCalendarModel.Events(new[] { banked, pending }, Now);
            require(records.Count == 2 && records.All(item => !item.Completed));
            require(records.Single(item => item.State == "banked").Date == new DateTime(2026, 10, 8));
            require(records.Single(item => item.State == "uncertain").Badge == "待核实");
            require(ResetNewsPresentation.From(banked).Description.Contains("不是直接恢复"));
        });
        check("Within the next two hours retains its deadline meaning on the Beijing calendar", () =>
        {
            var source = Item("2110595554036400151", "upcoming", "Day 10/ Reset\n\nLanding within the next 2 hours", "2026-10-15T04:56:07Z");
            var presentation = ResetNewsPresentation.From(source, Now);
            require(presentation.ExpectedAt == DateTimeOffset.Parse("2026-10-15T06:56:07Z") && presentation.TimeText.EndsWith("前"));
            require(ResetCalendarModel.Events(new[] { source }, Now).Single().Date == new DateTime(2026, 10, 15));
        });
        check("Elapsed forecast stays a historical preview on its Beijing target day, never a completed reset", () =>
        {
            var item = ResetCalendarModel.Events(new[] { Preview() }, Now).Single();
            require(item.Date == new DateTime(2026, 10, 23) && item.State == "past-preview" && !item.Completed);
            require(item.TimeText.StartsWith("原计划") && item.Badge == "预计已生效" && item.Detail.Contains("实际额度以 Codex 显示为准"));
        });
        check("Known upcoming time remains a preview until both timezone interpretations have passed", () =>
        {
            var item = ResetCalendarModel.Events(new[] { Preview() }, DateTimeOffset.Parse("2026-10-22T17:30:00Z")).Single();
            require(item.State == "upcoming" && item.Badge == "等待重置");
        });
        check("A completion supersedes only its own preview chain and records the Beijing publication date", () =>
        {
            var root = Item("2113162277688070445", "upcoming", "Codex quota will reset today.", "2026-10-22T06:55:22Z");
            var completed = Item("2113162413008884100", "announced", "Codex quota has reset. Enjoy.", "2026-10-22T20:01:00Z", root.Id);
            var records = ResetCalendarModel.Events(new[] { root, Preview(), completed }, Now);
            require(records.Count == 1 && records[0].Completed && records[0].Date == new DateTime(2026, 10, 23));
            require(records[0].TimeText.Contains("04:01") && records[0].Detail.Contains("发帖时间") && records[0].Badge == "重置确认");
        });
        check("Independent announcements on the same day are preserved rather than guessed to be the same reset", () =>
        {
            var completion = Item("2113162413008884101", "announced", "Codex quota has reset.", "2026-10-22T20:01:00Z");
            var records = ResetCalendarModel.Events(new[] { Preview(), completion }, Now);
            require(records.Count == 2 && records.Count(item => item.Completed) == 1 && records.Count(item => item.State == "past-preview") == 1);
        });
        check("A later preview in an old thread does not inherit the old completion status", () =>
        {
            var completed = Item("2112432076767289678", "announced", "Codex quota has reset.", "2026-10-20T06:33:48Z");
            var later = Preview() with { GroupId = completed.Id };
            var records = ResetCalendarModel.Events(new[] { completed, later }, Now);
            require(records.Count == 2 && records.Single(item => item.Id == completed.Id).Completed
                && records.Single(item => item.Id == later.Id).State == "past-preview");
        });
        check("Undated previews and cross-day timezone ambiguity are recorded as publication days, without invented reset dates", () =>
        {
            var noTime = Item("2113162413008884102", "upcoming", "Codex reset is coming soon.", "2026-10-22T06:55:22Z");
            var ambiguous = noTime with { Id = "2113162413008884103", Text = "Codex reset tomorrow at 8am PST." };
            foreach (var source in new[] { noTime, ambiguous })
            {
                var record = ResetCalendarModel.Events(new[] { source }, Now).Single();
                require(record.State == "undated" && record.Date == new DateTime(2026, 10, 22));
            }
        });
        check("Month grid has complete Monday-first weeks including year boundaries and leap days", () =>
        {
            var days = ResetCalendarModel.MonthDays(new DateTime(2026, 10, 1));
            require(days.Count == 42 && days[0] == new DateTime(2026, 9, 28) && days[^1] == new DateTime(2026, 11, 8));
            require(ResetCalendarModel.MonthDays(new DateTime(2028, 2, 1)).Contains(new DateTime(2028, 2, 29)));
            require(ResetCalendarModel.MonthDays(new DateTime(2027, 1, 1))[0].Year == 2026);
        });
        check("Calendar clicks select a history day and incoming messages preserve that user selection", () =>
        {
            var view = new ResetCalendarView { Clock = () => Now };
            var old = Item("2112432076767289678", "announced", "Codex quota has reset.", "2026-10-20T06:33:48Z");
            var older = old with { Id = "2112432076767289677", PublishedAt = old.PublishedAt.AddDays(-7) };
            view.SetItems(new[] { Preview(), old, older });
            require(view.SelectedDate == new DateTime(2026, 10, 20));
            var days = (UniformGrid)view.FindName("DaysGrid");
            var day = days.Children.Cast<Button>().Single(button => (DateTime)button.Tag == new DateTime(2026, 10, 13));
            require(day.Focusable && day.FocusVisualStyle is not null && day.MinHeight >= 44);
            day.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            require(view.SelectedDate == new DateTime(2026, 10, 13));
            view.SetItems(new[] { Preview(), old, older, old with { Id = "2112432076767289679", PublishedAt = Now } });
            require(view.SelectedDate == new DateTime(2026, 10, 13));
            require(((StackPanel)view.FindName("SelectedEvents")).Children.Count > 0);
        });
        check("Empty calendar remains useful and crossing midnight refreshes the selected default day", () =>
        {
            var now = DateTimeOffset.Parse("2026-10-22T15:59:00Z");
            var view = new ResetCalendarView { Clock = () => now };
            view.SetItems(Array.Empty<ResetNewsItem>());
            require(view.SelectedDate == new DateTime(2026, 10, 22) && ((UniformGrid)view.FindName("DaysGrid")).Children.Count == 42);
            now = now.AddMinutes(2);
            view.RefreshTime();
            require(view.SelectedDate == new DateTime(2026, 10, 23) && view.VisibleEvents.Count == 0);
        });
    }
}
