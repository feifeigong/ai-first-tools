using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;

namespace AIFirst.Workspace;

internal static class AutoResumeTests
{
    private sealed class FakeControl : IAutoResumeControl
    {
        internal AutoResumeStatus Value = new(true, true, true, 1);
        internal bool Fail;
        internal List<string> Calls = new();
        internal Func<string, CancellationToken, Task<AutoResumeStatus>>? Handler;
        public Task<AutoResumeStatus> ExecuteAsync(string action, CancellationToken cancellation)
        {
            Calls.Add(action);
            if (Handler is not null) return Handler(action, cancellation);
            if (Fail) throw new System.IO.IOException("模拟状态读取失败");
            Value = action switch
            {
                "stop" => Value with { Running = false, Autostart = false, WatcherCount = 0 },
                "start" => Value with { Running = true, WatcherCount = 1 },
                "autostart-off" => Value with { Autostart = false },
                "autostart-on" => Value with { Autostart = true },
                _ => Value
            };
            return Task.FromResult(Value);
        }
    }

    internal static void Run(Action<string, Action> check, Action<bool> require)
    {
        check("Auto resume page reads service state without enabling anything", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            require(((ToggleButton)page.FindName("RunningSwitch")).IsChecked == true);
            require(((ToggleButton)page.FindName("AutostartSwitch")).IsChecked == true);
            require(fake.Calls.Count == 1 && fake.Calls[0] == "status");
        });
        check("Power switch stops auto resume and displays disabled autostart", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            var power = (ToggleButton)page.FindName("RunningSwitch");
            power.IsChecked = false;
            power.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            require(fake.Calls[^1] == "stop" && !fake.Value.Running && !fake.Value.Autostart);
            require(((ToggleButton)page.FindName("AutostartSwitch")).IsChecked == false);
        });
        check("Autostart switch keeps the current watcher running", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            var startup = (ToggleButton)page.FindName("AutostartSwitch");
            startup.IsChecked = false;
            startup.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            require(fake.Calls[^1] == "autostart-off" && fake.Value.Running && !fake.Value.Autostart);
            require(((ToggleButton)page.FindName("RunningSwitch")).IsChecked == true);
        });
        check("Uncertain service state locks switches until a successful refresh", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            fake.Fail = true;
            page.RefreshAsync().GetAwaiter().GetResult();
            require(!((ToggleButton)page.FindName("RunningSwitch")).IsEnabled && !((ToggleButton)page.FindName("AutostartSwitch")).IsEnabled);
            require(((TextBlock)page.FindName("StateTitle")).Text == "状态暂时无法确认");
            require(((ToggleButton)page.FindName("RunningSwitch")).IsChecked is null);
            require(fake.Calls.Count == 2); // A failed read does not silently retry or change anything.
            fake.Fail = false;
            page.RefreshAsync().GetAwaiter().GetResult();
            require(((ToggleButton)page.FindName("RunningSwitch")).IsEnabled && ((ToggleButton)page.FindName("RunningSwitch")).IsChecked == true);
        });
        check("Failed start rechecks the actual state and allows another click", () =>
        {
            var fake = new FakeControl { Value = new(true, false, false, 0) };
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            fake.Handler = (action, _) => action == "start"
                ? Task.FromException<AutoResumeStatus>(new System.IO.IOException("内部异常不应展示给用户"))
                : Task.FromResult(fake.Value);
            var power = (ToggleButton)page.FindName("RunningSwitch");
            power.IsChecked = true;
            power.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            require(fake.Calls.Count == 3 && fake.Calls[1] == "start" && fake.Calls[2] == "status");
            require(power.IsEnabled && power.IsChecked == false && !page.IsBusy);
            require(((Border)page.FindName("MessageCard")).Visibility == Visibility.Visible);
            require(!((TextBlock)page.FindName("MessageText")).Text.Contains("内部异常"));
            fake.Handler = null;
            power.IsChecked = true;
            power.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
            require(fake.Calls[^1] == "start" && power.IsChecked == true && power.IsEnabled);
            require(((Border)page.FindName("MessageCard")).Visibility == Visibility.Collapsed);
        });
        check("Partially completed stop shows freshly read values instead of cached switches", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            fake.Handler = (action, _) =>
            {
                if (action == "stop")
                {
                    fake.Value = fake.Value with { Running = false, WatcherCount = 0 };
                    return Task.FromException<AutoResumeStatus>(new System.IO.IOException("模拟开机设置保存失败"));
                }
                return Task.FromResult(fake.Value);
            };
            page.ExecuteAsync("stop").GetAwaiter().GetResult();
            require(fake.Calls[^2] == "stop" && fake.Calls[^1] == "status");
            require(((ToggleButton)page.FindName("RunningSwitch")).IsChecked == false);
            require(((ToggleButton)page.FindName("AutostartSwitch")).IsChecked == true);
            require(((ToggleButton)page.FindName("AutostartSwitch")).IsEnabled);
        });
        check("Failed change and failed confirmation leave the state unknown", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            fake.Fail = true;
            page.ExecuteAsync("stop").GetAwaiter().GetResult();
            require(fake.Calls.Count == 3 && fake.Calls[1] == "stop" && fake.Calls[2] == "status");
            require(!((ToggleButton)page.FindName("RunningSwitch")).IsEnabled);
            require(((ToggleButton)page.FindName("RunningSwitch")).IsChecked is null);
            require(((Button)page.FindName("RefreshButton")).IsEnabled);
        });
        check("Cancelled action propagates cancellation without querying or reporting success", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            fake.Handler = (_, _) => Task.FromCanceled<AutoResumeStatus>(new CancellationToken(true));
            var cancelled = false;
            try { page.ExecuteAsync("stop").GetAwaiter().GetResult(); }
            catch (OperationCanceledException) { cancelled = true; }
            require(cancelled && fake.Calls.Count == 2 && fake.Calls[^1] == "stop");
            require(!page.IsBusy && !((ToggleButton)page.FindName("RunningSwitch")).IsEnabled);
        });
        check("The page has no focus frame while interactive controls retain keyboard focus", () =>
        {
            using var page = new AutoResumePage(new FakeControl());
            require(page.Content is ScrollViewer scroll && !scroll.Focusable);
            var power = (ToggleButton)page.FindName("RunningSwitch");
            require(power.Focusable && power.FocusVisualStyle is not null);
            require(((Button)page.FindName("RefreshButton")).Focusable);
        });
        check("Missing installation disables actions and disposing sends no stop", () =>
        {
            var fake = new FakeControl { Value = new(false, false, false, 0) };
            var page = new AutoResumePage(fake);
            page.RefreshAsync().GetAwaiter().GetResult();
            require(!((ToggleButton)page.FindName("RunningSwitch")).IsEnabled);
            page.Dispose();
            require(fake.Calls.Count == 1 && fake.Calls[0] == "status");
        });
        check("Reset news renders cached posts alongside a failed refresh without starting auto resume", () =>
        {
            var fake = new FakeControl();
            using var page = new AutoResumePage(fake);
            var item = new ResetNewsItem("synthetic-reset-1", "有一条重置相关消息", "Synthetic announcement used only in this isolated test.", "upcoming", DateTimeOffset.Parse("2026-10-22T06:20:00Z"), "https://x.com/thsottiaux/status/12345");
            page.PaintResetNews(new ResetNewsSnapshot(true, "暂时连不上 X", "最新消息还没查到，下面保留上次看到的内容。", DateTimeOffset.Parse("2026-10-22T06:30:00Z"), new[] { item }));
            require(((TextBlock)page.FindName("ResetStatusText")).Text == "暂时连不上 X");
            require(((Border)page.FindName("ResetStatusCard")).Visibility == Visibility.Visible);
            require(((ResetCalendarView)page.FindName("ResetCalendar")).VisibleEvents.Count == 1);
            require(((ToggleButton)page.FindName("ResetEnabledSwitch")).IsChecked == true);
            require(fake.Calls.Count == 0);
        });
        check("Reset notice only reports pause success after the callback confirms it", () =>
        {
            var calls = 0;
            var item = new ResetNewsItem("synthetic-reset-2", "Codex 重置预告", "Synthetic test only.", "upcoming", DateTimeOffset.Parse("2026-10-22T06:20:00Z"), "https://x.com/thsottiaux/status/12346");
            var notice = new ResetNoticeWindow(item, () => Task.FromResult(++calls > 1));
            notice.PauseAsync().GetAwaiter().GetResult();
            require(calls == 1 && !notice.PauseSucceeded);
            require(((Button)notice.FindName("PauseButton")).IsEnabled);
            require(((TextBlock)notice.FindName("NoticeResultText")).Text.Contains("没有关闭成功"));
            notice.PauseAsync().GetAwaiter().GetResult();
            require(calls == 2 && notice.PauseSucceeded);
            require(!((Button)notice.FindName("PauseButton")).IsEnabled);
            require(((Button)notice.FindName("DismissButton")).Content.Equals("完成"));
            notice.Close();
        });
        check("Closing a reset notice leaves auto resume unchanged", () =>
        {
            var calls = 0;
            var item = new ResetNewsItem("synthetic-reset-3", "Codex 重置消息", "Synthetic test only.", "announced", DateTimeOffset.Parse("2026-10-22T06:20:00Z"), "https://x.com/thsottiaux/status/12347");
            var notice = new ResetNoticeWindow(item, () => { calls++; return Task.FromResult(true); });
            require(((TextBlock)notice.FindName("NoticeGuidance")).Text.Contains("不代表你的额度已经到账"));
            notice.Close();
            require(calls == 0 && !notice.PauseSucceeded);
        });
    }
}
