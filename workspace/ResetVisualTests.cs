using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace AIFirst.Workspace;

internal static class ResetVisualTests
{
    private sealed class FixtureControl : IAutoResumeControl
    {
        internal readonly List<string> Calls = new();
        public Task<AutoResumeStatus> ExecuteAsync(string action, CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            Calls.Add(action);
            if (action != "status") throw new InvalidOperationException("Visual fixtures must not change auto resume.");
            return Task.FromResult(new AutoResumeStatus(true, true, true, 1));
        }
    }

    private sealed class RejectNetworkHandler : HttpMessageHandler
    {
        internal int Requests;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requests++;
            throw new InvalidOperationException("Network access is disabled for visual fixtures.");
        }
    }

    internal static int Render(string outputDirectory)
    {
        var directory = Path.GetFullPath(outputDirectory);
        Directory.CreateDirectory(directory);
        var report = Path.Combine(directory, "render-report.json");
        try
        {
            var now = new DateTimeOffset(2026, 10, 24, 5, 0, 0, TimeSpan.FromHours(8));
            var item = new ResetNewsItem("synthetic-visual-reset", "Tibo 发布了新的重置预告",
                "Day 18/ Synthetic Codex update. But yes… that’s a reset!\n\nLanding tomorrow before 10am PST together with a small ship.",
                "upcoming", new DateTimeOffset(2026, 10, 23, 12, 47, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000000", GroupId: "synthetic-day18");
            var older = new[]
            {
                new ResetNewsItem("synthetic-day18", "已宣布完成", "Day 18/ Synthetic Codex update. But yes… that’s a reset!", "announced", new DateTimeOffset(2026, 10, 23, 12, 46, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000009"),
                new ResetNewsItem("synthetic-history-1", "已宣布完成", "Codex quota has reset. Enjoy.", "announced", new DateTimeOffset(2026, 10, 20, 14, 33, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000001"),
                new ResetNewsItem("synthetic-history-2", "已宣布完成", "Codex quota has reset. Enjoy.", "announced", new DateTimeOffset(2026, 10, 13, 13, 6, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000002"),
                new ResetNewsItem("synthetic-history-3", "已宣布完成", "Codex quota has reset. Enjoy.", "announced", new DateTimeOffset(2026, 10, 11, 12, 1, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000004"),
                new ResetNewsItem("synthetic-history-4", "已宣布完成", "Codex quota has reset. Enjoy.", "announced", new DateTimeOffset(2026, 10, 15, 14, 28, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000005"),
                new ResetNewsItem("synthetic-banked", "发放重置卡", "Loading a banked reset in paid accounts.", "banked", new DateTimeOffset(2026, 10, 8, 3, 19, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000006"),
                new ResetNewsItem("synthetic-incomplete", "待核实", "Codex reset has been…", "uncertain", new DateTimeOffset(2026, 10, 7, 11, 35, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000007"),
                new ResetNewsItem("synthetic-context-needed", "待核实", "Done", "uncertain", new DateTimeOffset(2026, 10, 18, 5, 12, 0, TimeSpan.FromHours(8)), "https://x.com/thsottiaux/status/1000000000000000008")
            };
            var snapshot = new ResetNewsSnapshot(true, "正在留意 Tibo 的重置消息", "有新消息时会弹窗提醒，是否自动用卡由你决定。",
                now, new[] { item }.Concat(older).ToArray(), true, now, now.AddMinutes(5));
            using var handler = new RejectNetworkHandler();
            using var http = new HttpClient(handler);
            // This fresh child is the only state directory the fixture service can inspect.
            var fixtureDirectory = Path.Combine(directory, "fixture-" + Guid.NewGuid().ToString("N"));
            using var service = new ResetNewsService(fixtureDirectory, http, () => now);
            var control = new FixtureControl();
            var compactCanScroll = false;
            using (var page = new AutoResumePage(control, service))
            {
                page.ResetClock = () => now;
                page.RefreshAsync().GetAwaiter().GetResult();
                page.PaintResetNews(snapshot);
                RenderElement(page, Path.Combine(directory, "page.png"), 1020, 1050);
                RenderElement(page, Path.Combine(directory, "page-compact.png"), 760, 850);
                var scroll = (ScrollViewer)page.Content;
                if (scroll.ScrollableWidth > 0.5) throw new InvalidOperationException("The compact page has horizontal overflow.");
                if (scroll.ScrollableHeight > 0.5)
                {
                    scroll.ScrollToEnd();
                    DrainLayout(page);
                    compactCanScroll = scroll.VerticalOffset > 0;
                    if (!compactCanScroll) throw new InvalidOperationException("The compact page cannot reach content below the fold.");
                    scroll.ScrollToTop();
                }
                var calendar = new ResetCalendarView { Clock = () => now };
                calendar.SetItems(snapshot.Items);
                calendar.SelectDate(new DateTime(2026, 10, 23));
                var surface = new Border { Background = Brushes.White, Padding = new Thickness(26), Child = calendar };
                RenderElement(surface, Path.Combine(directory, "calendar.png"), 900, 610);
                calendar.SelectDate(new DateTime(2026, 10, 24));
                RenderElement(surface, Path.Combine(directory, "calendar-latest-forecast.png"), 900, 610);
                calendar.SelectDate(new DateTime(2026, 10, 20));
                RenderElement(surface, Path.Combine(directory, "calendar-completed.png"), 900, 610);
                calendar.SelectDate(new DateTime(2026, 10, 8));
                RenderElement(surface, Path.Combine(directory, "calendar-banked.png"), 900, 610);
                calendar.SelectDate(new DateTime(2026, 10, 7));
                RenderElement(surface, Path.Combine(directory, "calendar-unconfirmed.png"), 900, 610);
                var future = new ResetNewsItem("synthetic-future", "预告", "Codex reset tomorrow before 10am PT.", "upcoming", now.AddMinutes(-5), "https://x.com/thsottiaux/status/1000000000000000003");
                calendar.SetItems(snapshot.Items.Concat(new[] { future }).ToArray());
                calendar.SelectDate(ResetCalendarModel.Events(new[] { future }, now).Single().Date);
                RenderElement(surface, Path.Combine(directory, "calendar-upcoming.png"), 900, 610);
                calendar.SetItems(Array.Empty<ResetNewsItem>());
                RenderElement(surface, Path.Combine(directory, "calendar-empty.png"), 900, 610);
                var weekend = new ResetCalendarView { Clock = () => DateTimeOffset.Parse("2026-10-26T07:00:00Z") };
                weekend.SetItems(new[]
                {
                    new ResetNewsItem("synthetic-weekend-completion", "", "It is all propagated. Enjoy some mad codexing tomorrow.", "announced", DateTimeOffset.Parse("2026-10-25T06:06:16Z"), "https://x.com/thsottiaux/status/1000000000000000010"),
                    new ResetNewsItem("synthetic-monday-preview", "", "Day 21/ But today is a reset.", "upcoming", DateTimeOffset.Parse("2026-10-26T05:21:22Z"), "https://x.com/thsottiaux/status/1000000000000000011")
                });
                var weekendSurface = new Border { Background = Brushes.White, Padding = new Thickness(26), Child = weekend };
                weekend.SelectDate(new DateTime(2026,10,25));
                RenderElement(weekendSurface, Path.Combine(directory,"calendar-weekend-completed.png"),900,610);
                weekend.SelectDate(new DateTime(2026,10,26));
                RenderElement(weekendSurface, Path.Combine(directory,"calendar-today-preview.png"),900,610);
                page.PaintResetNews(snapshot with { Fresh = false, StatusText = "暂时没取到最新消息，正在自动重试", DetailText = "下方是上次保存的消息，发布时间已标出。" });
                RenderElement(page, Path.Combine(directory, "page-offline.png"), 1020, 1050);
            }

            var pauseCalls = 0;
            var notice = new ResetNoticeWindow(item, () => { pauseCalls++; return Task.FromResult(true); });
            var content = (FrameworkElement)notice.Content;
            notice.Content = null;
            var noticeSurface = new Border { Background = Brushes.White, Child = content };
            noticeSurface.Measure(new Size(520, double.PositiveInfinity));
            var noticeHeight = Math.Ceiling(noticeSurface.DesiredSize.Height);
            RenderElement(noticeSurface, Path.Combine(directory, "notice.png"), 520, noticeHeight);
            noticeSurface.Child = null;
            notice.Content = content;
            notice.Close();

            if (handler.Requests != 0 || pauseCalls != 0 || control.Calls.Any(action => action != "status"))
                throw new InvalidOperationException("Visual rendering attempted a non-read-only operation.");
            File.WriteAllText(report, JsonSerializer.Serialize(new
            {
                passed = true,
                synthetic = true,
                networkRequests = handler.Requests,
                pauseRequests = pauseCalls,
                compactCanScroll,
                horizontalOverflow = false,
                images = new[] { "page.png", "page-compact.png", "page-offline.png", "calendar.png", "calendar-latest-forecast.png", "calendar-completed.png", "calendar-banked.png", "calendar-unconfirmed.png", "calendar-upcoming.png", "calendar-empty.png", "calendar-weekend-completed.png", "calendar-today-preview.png", "notice.png" },
                renderDpi = 96
            }, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
        }
        catch (Exception exception)
        {
            File.WriteAllText(report, JsonSerializer.Serialize(new { passed = false, error = exception.ToString() }, new JsonSerializerOptions { WriteIndented = true }));
            return 1;
        }
    }

    private static void RenderElement(FrameworkElement element, string path, double width, double height)
    {
        element.Measure(new Size(width, height));
        element.Arrange(new Rect(0, 0, width, height));
        DrainLayout(element);
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(width), (int)Math.Ceiling(height), 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(element);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var output = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None);
        encoder.Save(output);
    }

    private static void DrainLayout(FrameworkElement element)
    {
        element.UpdateLayout();
        var frame = new DispatcherFrame();
        Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.ContextIdle, new Action(() => frame.Continue = false));
        Dispatcher.PushFrame(frame);
        element.UpdateLayout();
    }
}
