using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;

namespace AIFirst.Workspace;

public partial class ResetCalendarView : UserControl
{
    private IReadOnlyList<ResetNewsItem> items = Array.Empty<ResetNewsItem>();
    private IReadOnlyList<ResetCalendarEvent> events = Array.Empty<ResetCalendarEvent>();
    private DateTime month;
    private DateTime selected;
    private bool initialized;
    private bool selectedByUser;
    private string lastSignature = "";
    internal Func<DateTimeOffset> Clock { get; set; } = () => DateTimeOffset.UtcNow;
    internal DateTime SelectedDate => selected;
    internal IReadOnlyList<ResetCalendarEvent> VisibleEvents => events;

    public ResetCalendarView()
    {
        InitializeComponent();
        month = new DateTime(Clock().ToOffset(TimeSpan.FromHours(8)).Year, Clock().ToOffset(TimeSpan.FromHours(8)).Month, 1);
        selected = ResetCalendarModel.BeijingDate(Clock());
    }

    internal void SetItems(IReadOnlyList<ResetNewsItem> value)
    {
        items = value;
        RefreshTime();
    }

    internal void RefreshTime()
    {
        var now = Clock();
        events = ResetCalendarModel.Events(items, now);
        var today = ResetCalendarModel.BeijingDate(now);
        var signature = today.Ticks + ":" + string.Join("|", events.Select(item => item.ToString()));
        if (initialized && signature == lastSignature) return;
        lastSignature = signature;
        if (!selectedByUser)
        {
            selected = events.Where(item => item.State == "upcoming").OrderBy(item => item.Date).FirstOrDefault()?.Date
                ?? events.FirstOrDefault(item => item.State == "undated" && item.Date == today)?.Date
                ?? events.FirstOrDefault(item => item.Completed)?.Date ?? events.FirstOrDefault()?.Date ?? today;
            month = new DateTime(selected.Year, selected.Month, 1);
        }
        initialized = true;
        Paint();
    }

    private static Brush Ink(string hex) => (Brush)new BrushConverter().ConvertFromString(hex)!;
    private static Brush Color(ResetCalendarEvent item) => Ink(item.Completed ? "#207A58" : item.State == "banked" ? "#7252A3" : item.State is "upcoming" or "undated" ? "#0068D9" : "#5B6B7E");
    private static TextBlock Text(string value, double size = 13, string color = "#202D3A") => new()
    { Text = value, FontSize = size, Foreground = Ink(color), TextWrapping = TextWrapping.Wrap, LineHeight = size + 8 };

    private void Paint()
    {
        var today = ResetCalendarModel.BeijingDate(Clock());
        MonthHeading.Text = month.ToString("yyyy 年 M 月", CultureInfo.InvariantCulture);
        DaysGrid.Children.Clear();
        foreach (var day in ResetCalendarModel.MonthDays(month))
        {
            var records = events.Where(item => item.Date == day).ToArray();
            var record = records.OrderByDescending(item => item.Completed).FirstOrDefault();
            var button = new Button { Style = (Style)FindResource("CalendarDay"), Tag = day };
            var content = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            var number = Text(day.Day.ToString(CultureInfo.InvariantCulture), 15);
            number.TextAlignment = TextAlignment.Center;
            number.FontWeight = day == today || day == selected ? FontWeights.SemiBold : FontWeights.Normal;
            if (day.Month != month.Month) number.Foreground = Ink("#64748B");
            else if (day == today || day == selected) number.Foreground = Ink("#0068D9");
            content.Children.Add(number);
            var marker = Text(record is null ? day == today ? "今天" : "" : record.Completed ? "重置确认" : record.State == "banked" ? "发重置卡" : record.State == "uncertain" ? "待核实" : record.State is "upcoming" or "undated" ? "等待重置" : "预计生效", 11);
            marker.TextAlignment = TextAlignment.Center;
            marker.Foreground = record is null ? Ink("#0068D9") : Color(record);
            marker.MinHeight = 16;
            content.Children.Add(marker);
            button.Content = content;
            if (day == selected) { button.Background = Ink("#EAF3FF"); button.BorderBrush = Ink("#BDD7F5"); }
            else if (day == today) button.BorderBrush = Ink("#5F9DE0");
            System.Windows.Automation.AutomationProperties.SetName(button, day.ToString("yyyy年M月d日", CultureInfo.InvariantCulture) + (day == today ? "，今天" : "") + "，" + (record?.Badge ?? "没有记录"));
            button.Click += (_, _) => SelectDate(day);
            button.PreviewKeyDown += DateKeyDown;
            DaysGrid.Children.Add(button);
        }
        SelectedHeading.Text = ResetCalendarModel.DayLabel(selected, today);
        SelectedEvents.Children.Clear();
        var onDay = events.Where(item => item.Date == selected).OrderByDescending(item => item.Completed).ThenByDescending(item => item.PublishedAt).ToArray();
        if (onDay.Length == 0)
        {
            SelectedEvents.Children.Add(Text("这一天还没有重置消息记录", 15));
            var help = Text("日历会随着收到的预告和确认消息更新。", 12, "#5B6B7E");
            help.Margin = new Thickness(0, 8, 0, 0);
            SelectedEvents.Children.Add(help);
        }
        foreach (var record in onDay)
        {
            var hasOtherCompletion = record.State == "past-preview" && onDay.Any(other => other.Completed);
            var stack = new StackPanel { Margin = new Thickness(0, 0, 0, onDay.Length > 1 ? 18 : 0) };
            var badge = Text(hasOtherCompletion ? "同日预告" : record.Badge, 11);
            badge.Foreground = Color(record);
            stack.Children.Add(new Border { Background = Ink(record.Completed ? "#EAF5EF" : record.State == "banked" ? "#F1ECF8" : record.State is "upcoming" or "undated" ? "#EAF3FF" : "#EFF2F6"), CornerRadius = new CornerRadius(5), Padding = new Thickness(8, 3, 8, 3), HorizontalAlignment = HorizontalAlignment.Left, Child = badge });
            var heading = Text(hasOtherCompletion ? "同日发布过的预告" : record.Heading, 15);
            heading.FontWeight = FontWeights.SemiBold;
            heading.Margin = new Thickness(0, 12, 0, 6);
            stack.Children.Add(heading);
            var time = Text(record.TimeText, 14);
            time.Foreground = record.State == "upcoming" ? Ink("#0068D9") : Ink("#5B6B7E");
            time.Margin = new Thickness(0, 0, 0, 8);
            stack.Children.Add(time);
            stack.Children.Add(Text(hasOtherCompletion ? "这一天另有重置确认，可在上方查看；尚未核实是否为同一次重置。" : record.Detail, 12, "#5B6B7E"));
            if (record.Note.Length > 0)
            {
                var note = Text(record.Note, 11, "#5B6B7E");
                note.Margin = new Thickness(0, 8, 0, 0);
                stack.Children.Add(note);
            }
            var link = new Button { Style = (Style)FindResource("CalendarAction"), Content = "查看原帖 ↗", Foreground = Ink("#0068D9"), HorizontalAlignment = HorizontalAlignment.Left, Margin = new Thickness(-10, 5, 0, 0) };
            link.Click += (_, _) => { if (!ResetNoticeWindow.TryOpenPost(record.Url)) link.Content = "暂时没能打开原帖"; };
            stack.Children.Add(link);
            SelectedEvents.Children.Add(stack);
        }
        RecentEvents.Children.Clear();
        foreach (var record in events.GroupBy(item => item.Date).Select(day => day.OrderByDescending(item => item.Completed).ThenByDescending(item => item.PublishedAt).First()).Take(4))
        {
            var button = new Button { Style = (Style)FindResource("RecentDay"), Tag = record.Date };
            var line = new Grid();
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(76) });
            line.ColumnDefinitions.Add(new ColumnDefinition());
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            line.Children.Add(Text(record.Date.ToString("MM · dd", CultureInfo.InvariantCulture), 13, "#5B6B7E"));
            var label = Text(record.Badge, 12); label.Foreground = Color(record); Grid.SetColumn(label, 1); line.Children.Add(label);
            var arrow = Text("›", 16, "#7C8795"); Grid.SetColumn(arrow, 2); line.Children.Add(arrow);
            button.Content = line;
            button.Click += (_, _) => SelectDate(record.Date);
            RecentEvents.Children.Add(button);
        }
        if (events.Count == 0) RecentEvents.Children.Add(Text("收到消息后会自动记录在这里。", 12, "#5B6B7E"));
    }

    internal void SelectDate(DateTime day, bool showDetail = true)
    {
        selected = day.Date;
        month = new DateTime(day.Year, day.Month, 1);
        selectedByUser = true;
        Paint();
        if (showDetail && ActualWidth > 0 && ActualWidth < 720)
            Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new Action(() => { if (IsVisible) DetailsPanel.BringIntoView(); }));
    }

    private void DateKeyDown(object sender, KeyEventArgs args)
    {
        var offset = args.Key switch { Key.Left => -1, Key.Right => 1, Key.Up => -7, Key.Down => 7, _ => 0 };
        if (offset == 0 || sender is not Button { Tag: DateTime date }) return;
        args.Handled = true;
        SelectDate(date.AddDays(offset), false);
        foreach (Button child in DaysGrid.Children) if (child.Tag is DateTime value && value == selected) { child.Focus(); break; }
    }

    private void BrowseMonth(int offset)
    {
        month = month.AddMonths(offset);
        selected = events.FirstOrDefault(item => item.Date.Year == month.Year && item.Date.Month == month.Month)?.Date ?? month;
        selectedByUser = true;
        Paint();
    }
    private void PreviousMonthClick(object sender, RoutedEventArgs args) => BrowseMonth(-1);
    private void NextMonthClick(object sender, RoutedEventArgs args) => BrowseMonth(1);
    private void TodayClick(object sender, RoutedEventArgs args) => SelectDate(ResetCalendarModel.BeijingDate(Clock()));
    private void CalendarSizeChanged(object sender, SizeChangedEventArgs args)
    {
        var compact = ActualWidth < 720;
        MonthColumn.Width = new GridLength(1, GridUnitType.Star);
        GutterColumn.Width = new GridLength(compact ? 0 : 28);
        DetailColumn.Width = compact ? new GridLength(0) : new GridLength(0.86, GridUnitType.Star);
        Grid.SetColumn(DetailsPanel, compact ? 0 : 2);
        Grid.SetRow(DetailsPanel, compact ? 1 : 0);
        DetailsPanel.Margin = new Thickness(0, compact ? 24 : 0, 0, 0);
    }
}
