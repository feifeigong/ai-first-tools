using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace AIFirst.Workspace;

internal sealed record ResetCalendarEvent(string Id, DateTime Date, DateTimeOffset PublishedAt, string State,
    string Badge, string Heading, string Detail, string TimeText, string Note, string Url)
{
    internal bool Completed => State == "completed";
}

internal static class ResetCalendarModel
{
    internal static DateTime BeijingDate(DateTimeOffset time) => time.ToOffset(TimeSpan.FromHours(8)).Date;

    internal static IReadOnlyList<ResetCalendarEvent> Events(IEnumerable<ResetNewsItem> items, DateTimeOffset now)
    {
        // A completion supersedes its preceding previews. A later forecast in that thread
        // must not erase the earlier completion or inherit its completed status.
        return items.GroupBy(item => string.IsNullOrEmpty(item.GroupId) ? item.Id : item.GroupId)
            .SelectMany(group =>
            {
                var ordered = group.OrderByDescending(item => item.PublishedAt).ThenByDescending(item => item.Kind == "announced").ToArray();
                var latest = ordered[0];
                var completion = latest.Kind == "upcoming" ? ordered.FirstOrDefault(item => item.Kind == "announced") : null;
                return completion is null ? new[] { latest } : new[] { latest, completion };
            })
            .Select(item => Event(item, now)).OrderByDescending(item => item.Date).ThenByDescending(item => item.Completed)
            .ThenByDescending(item => item.PublishedAt).ToArray();
    }

    private static ResetCalendarEvent Event(ResetNewsItem item, DateTimeOffset now)
    {
        var view = ResetNewsPresentation.From(item, now);
        if (item.Kind == "banked")
            return new(item.Id, BeijingDate(item.PublishedAt), item.PublishedAt, "banked", "发放重置卡", "Tibo 发布了重置卡消息",
                view.Description, "公告发布于 " + ResetNewsPresentation.BeijingStamp(item.PublishedAt), "", item.Url);
        if (item.Kind == "uncertain")
            return new(item.Id, BeijingDate(item.PublishedAt), item.PublishedAt, "uncertain", "待核实", "这条历史消息还待核实",
                view.Description, "原帖发布于 " + ResetNewsPresentation.BeijingStamp(item.PublishedAt), "", item.Url);
        if (item.Kind == "announced")
            return new(item.Id, BeijingDate(item.PublishedAt), item.PublishedAt, "completed", "完成公告", "Tibo 已宣布完成重置",
                "按完成公告的发布日记录，实际额度以 Codex 显示为准。", "公告发布于 " + ResetNewsPresentation.BeijingStamp(item.PublishedAt), "", item.Url);
        var hasDate = view.ExpectedAt is { } target && (view.AlternativeAt is null || BeijingDate(target) == BeijingDate(view.AlternativeAt.Value));
        if (!hasDate)
            return new(item.Id, BeijingDate(item.PublishedAt), item.PublishedAt, "undated", "时间待定", "已发布预告，时间待确认",
                "这一天发布了预告，还不能确定重置日期。", view.ExpectedAt is null ? "尚未公布明确时间" : view.TimeText, view.TimeNote, item.Url);
        var passed = view.ExpectedAt <= now && (view.AlternativeAt is null || view.AlternativeAt <= now);
        var note = view.TimeNote.Replace(" 原计划时间已过，实际额度以 Codex 显示为准。", "", StringComparison.Ordinal);
        return new(item.Id, BeijingDate(view.ExpectedAt!.Value), item.PublishedAt, passed ? "past-preview" : "upcoming",
            passed ? "历史预告" : "重置预告", passed ? "历史重置预告" : "Tibo 发布了重置预告",
            passed ? "原计划时间已过，实际额度以 Codex 显示为准。" : "这是预计安排，收到完成消息后会继续更新。",
            (passed ? "原计划 · " : "预计 · ") + view.TimeText.Replace("北京时间 ", "", StringComparison.Ordinal), note, item.Url);
    }

    internal static IReadOnlyList<DateTime> MonthDays(DateTime month)
    {
        var first = new DateTime(month.Year, month.Month, 1);
        var start = first.AddDays(-(((int)first.DayOfWeek + 6) % 7));
        return Enumerable.Range(0, 42).Select(offset => start.AddDays(offset)).ToArray();
    }

    internal static string DayLabel(DateTime date, DateTime today) => date.ToString("M 月 d 日", CultureInfo.InvariantCulture)
        + (date == today ? " · 今天" : " · 周" + "日一二三四五六"[(int)date.DayOfWeek]);
}
