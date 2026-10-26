using System;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;

namespace AIFirst.Workspace;

internal sealed record ResetNewsPresentation(string Summary, string Description, string TimeText, string TimeNote,
    DateTimeOffset? ExpectedAt = null, DateTimeOffset? AlternativeAt = null)
{
    private static readonly TimeSpan Beijing = TimeSpan.FromHours(8);
    private static readonly Regex Clock = new(@"\b(?:(?<h>\d{1,2})(?::(?<m>\d{2}))?\s*(?<ap>a\.?m\.?|p\.?m\.?)?|(?<named>midnight|noon))\s*(?<zone>PST|PDT|PT|Pacific\s+Time|EST|EDT|ET|Eastern\s+Time|UTC|GMT)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    internal static string BeijingStamp(DateTimeOffset value) => value.ToOffset(Beijing).ToString("MM-dd HH:mm", CultureInfo.InvariantCulture);
    private static string Display(DateTimeOffset value) => value.ToOffset(Beijing).ToString("M 月 d 日 HH:mm", CultureInfo.InvariantCulture);

    internal static ResetNewsPresentation From(ResetNewsItem item, DateTimeOffset? now = null)
    {
        if (item.Kind == "announced") return new("Tibo 已宣布额度重置", "Tibo 表示已完成重置，是否到账以你的 Codex 实际显示为准。", "", "");
        if (item.Kind == "banked") return new("Tibo 发布了重置卡消息", "这次是发放可留着以后使用的重置卡，不是直接恢复当前额度。是否收到以你的 Codex 显示为准。", "", "");
        if (item.Kind == "uncertain") return new("这条历史消息还待核实", "原文不完整，或还不能确定它对应哪次重置。暂不计为已完成，也不会据此提醒。", "", "");
        var text = item.Text;
        var result = new ResetNewsPresentation("Codex 额度重置预告", "Tibo 预告将进行一次额度重置。", "具体时间待公布", "原帖尚未给出可明确换算的时间，会继续留意后续消息。");
        // Only interpret bounded, explicit time statements. The source text remains in the local cache.
        if (text.Length > 30000) return result;
        var matches = Clock.Matches(text).Cast<Match>().ToArray();
        if (matches.Length == 0)
        {
            var durations = Regex.Matches(text, @"\b(?<bound>in|within(?:\s+the\s+next)?)\s+(?<count>\d{1,3})\s*(?<unit>hours?|hrs?|minutes?|mins?)\b", RegexOptions.IgnoreCase);
            if (durations.Count != 1 || !int.TryParse(durations[0].Groups["count"].Value, out var count) || count == 0 || count > 168) return result;
            var duration = durations[0];
            var targetDuration = duration.Groups["unit"].Value.StartsWith("h", StringComparison.OrdinalIgnoreCase)
                ? item.PublishedAt.AddHours(count) : item.PublishedAt.AddMinutes(count);
            var durationNote = "根据原帖发布时间换算，为预计时间。";
            if (targetDuration < (now ?? DateTimeOffset.UtcNow)) durationNote += " 原计划时间已过，实际额度以 Codex 显示为准。";
            var within = duration.Groups["bound"].Value.StartsWith("within", StringComparison.OrdinalIgnoreCase);
            return result with { TimeText = (within ? "北京时间 " : "北京时间约 ") + Display(targetDuration) + (within ? " 前" : ""), TimeNote = durationNote, ExpectedAt = targetDuration };
        }
        if (matches.Length != 1) return result;
        var match = matches[0];
        if (Regex.IsMatch(text[(match.Index + match.Length)..], @"^\s*[+-]\s*\d")) return result;
        var start = text.LastIndexOfAny(new[] { '\n', '!', '?' }, Math.Max(0, match.Index - 1));
        var sentenceBreak = text.LastIndexOf(". ", match.Index, StringComparison.Ordinal);
        start = Math.Max(start, sentenceBreak < 0 ? -1 : sentenceBreak + 1);
        var end = text.IndexOfAny(new[] { '\n', '!', '?' }, match.Index + match.Length);
        var sentence = text[(start + 1)..(end < 0 ? text.Length : end)];
        var rangeText = Regex.Replace(sentence, @"\b\d{4}-\d{2}-\d{2}\b", "");
        if (Regex.IsMatch(rangeText, @"\b(?:between|until|not\s+before|webinar|meeting|sale|promo|livestream)\b|\bfrom\b.{0,50}\bto\b|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*[-–]\s*\d", RegexOptions.IgnoreCase)) return result;
        var named = match.Groups["named"].Value.ToLowerInvariant();
        var hour = named.Length > 0 ? named == "midnight" ? 0 : 12 : int.Parse(match.Groups["h"].Value, CultureInfo.InvariantCulture);
        var minute = match.Groups["m"].Success ? int.Parse(match.Groups["m"].Value, CultureInfo.InvariantCulture) : 0;
        var ampm = match.Groups["ap"].Value.Replace(".", "").ToLowerInvariant();
        if (minute > 59 || (ampm.Length > 0 ? hour is < 1 or > 12 : hour > 23)) return result;
        if (ampm.Length > 0) hour = hour % 12 + (ampm == "pm" ? 12 : 0);
        var zone = match.Groups["zone"].Value.ToUpperInvariant();
        var pacific = zone is "PST" or "PDT" or "PT" or "PACIFIC TIME";
        var eastern = zone is "EST" or "EDT" or "ET" or "EASTERN TIME";
        TimeZoneInfo? regional = null;
        try
        {
            if (pacific || eastern) regional = TimeZoneInfo.FindSystemTimeZoneById(pacific ? "Pacific Standard Time" : "Eastern Standard Time");
        }
        catch (Exception exception) when (exception is TimeZoneNotFoundException or InvalidTimeZoneException) { return result; }
        TimeSpan? explicitOffset = zone switch
        {
            "PST" => TimeSpan.FromHours(-8), "PDT" => TimeSpan.FromHours(-7),
            "EST" => TimeSpan.FromHours(-5), "EDT" => TimeSpan.FromHours(-4),
            "UTC" or "GMT" => TimeSpan.Zero, _ => null
        };
        var postedLocal = explicitOffset is { } fixedOffset ? item.PublishedAt.ToOffset(fixedOffset)
            : TimeZoneInfo.ConvertTime(item.PublishedAt, regional!);
        if (!TryDate(sentence, postedLocal.Date, out var date))
        {
            // "By midnight" means the end of the posting local day, not
            // 00:00 at its beginning. Other undated clocks stay unresolved.
            if (named != "midnight" || !Regex.IsMatch(sentence, @"\b(?:by|before)\s+midnight\b", RegexOptions.IgnoreCase)) return result;
            date = postedLocal.Date.AddDays(1);
        }
        var local = DateTime.SpecifyKind(date.AddHours(hour).AddMinutes(minute), DateTimeKind.Unspecified);
        if (explicitOffset is null && (regional!.IsInvalidTime(local) || regional.IsAmbiguousTime(local)))
            return result with { TimeNote = "原帖时刻恰逢夏令时切换，暂时无法确定唯一的北京时间。" };
        var offset = explicitOffset ?? regional!.GetUtcOffset(local);
        var target = new DateTimeOffset(local, offset);
        var prefix = text[..match.Index];
        prefix = prefix[Math.Max(0, prefix.Length - 45)..];
        var before = Regex.IsMatch(prefix, @"\b(?:before|by|no\s+later\s+than)\s*$", RegexOptions.IgnoreCase);
        var after = Regex.IsMatch(prefix, @"\bafter\s*$", RegexOptions.IgnoreCase);
        var approximate = Regex.IsMatch(prefix, @"\b(?:around|about|approximately)\s*$", RegexOptions.IgnoreCase);
        var suffix = before ? " 前" : after ? " 后" : "";
        var label = "北京时间 " + (approximate ? "约 " : "") + Display(target) + suffix;
        var note = "按原帖时间换算；这是预计安排，并不代表你的额度已经到账。";
        DateTimeOffset? alternativeAt = null;
        if (regional is not null && explicitOffset is not null && !regional.IsInvalidTime(local) && !regional.IsAmbiguousTime(local)
            && regional.GetUtcOffset(local) != offset)
        {
            var alternative = new DateTimeOffset(local, regional.GetUtcOffset(local));
            alternativeAt = alternative;
            note = $"按原帖 {zone} 换算；若他泛指当时的美{(pacific ? "西" : "东")}时间，则是北京时间 {Display(alternative)}{suffix}。";
        }
        if (target < (now ?? DateTimeOffset.UtcNow)) note += " 原计划时间已过，实际额度以 Codex 显示为准。";
        return result with { TimeText = label, TimeNote = note, ExpectedAt = target, AlternativeAt = alternativeAt };
    }

    private static bool TryDate(string text, DateTime postedDate, out DateTime date)
    {
        date = default;
        var iso = Regex.Match(text, @"\b\d{4}-\d{2}-\d{2}\b");
        if (iso.Success) return DateTime.TryParseExact(iso.Value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out date);
        var absolute = Regex.Match(text, @"\b(?<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?<year>20\d{2}))?\b", RegexOptions.IgnoreCase);
        if (absolute.Success)
        {
            var month = DateTime.ParseExact(absolute.Groups["month"].Value[..3], "MMM", CultureInfo.InvariantCulture).Month;
            var year = absolute.Groups["year"].Success ? int.Parse(absolute.Groups["year"].Value, CultureInfo.InvariantCulture) : postedDate.Year;
            var day = int.Parse(absolute.Groups["day"].Value, CultureInfo.InvariantCulture);
            if (day < 1 || day > DateTime.DaysInMonth(year, month)) return false;
            date = new DateTime(year, month, day);
            return true;
        }
        var days = Regex.Matches(text, @"\b(?:today|tomorrow|tonight)\b", RegexOptions.IgnoreCase).Cast<Match>().Select(match => match.Value.ToLowerInvariant()).Distinct().ToArray();
        if (days.Length != 1) return false;
        date = postedDate.AddDays(days[0] == "tomorrow" ? 1 : 0);
        return true;
    }
}
