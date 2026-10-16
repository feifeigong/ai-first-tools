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
        public Task<AutoResumeStatus> ExecuteAsync(string action, CancellationToken cancellation)
        {
            Calls.Add(action);
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
            fake.Fail = false;
            page.RefreshAsync().GetAwaiter().GetResult();
            require(((ToggleButton)page.FindName("RunningSwitch")).IsEnabled && ((ToggleButton)page.FindName("RunningSwitch")).IsChecked == true);
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
    }
}
