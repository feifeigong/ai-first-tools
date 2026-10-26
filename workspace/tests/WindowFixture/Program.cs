using System;
using System.Drawing;
using System.IO;
using System.Text.Json;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        var form = new Form { Text = "工具箱窗口测试 · 不读写真实记录", Width = 950, Height = 650, BackColor = Color.FromArgb(245, 248, 241), Font = new Font("Microsoft YaHei UI", 12) };
        var panel = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, Padding = new Padding(36), WrapContents = false };
        panel.Controls.Add(new Label { Text = "隔离窗口兼容性测试", AutoSize = true, Font = new Font("Microsoft YaHei UI", 24), Margin = new Padding(0, 0, 0, 25) });
        panel.Controls.Add(new Label { Text = "切换工具后，下面的文本应保留。关闭工具箱时工具应正常关闭。", AutoSize = true });
        panel.Controls.Add(new TextBox { Name = "StateText", Width = 650, Text = "初始文本", Margin = new Padding(0, 20, 0, 25) });
        var popup = new Button { Text = "测试弹窗", AutoSize = true };
        popup.Click += (_, _) => MessageBox.Show(form, "测试弹窗可以正常关闭。没有执行搬运或模型调用。", "隔离测试", MessageBoxButtons.OK);
        panel.Controls.Add(popup);
        var busy = new CheckBox { Name = "BusyBox", Text = "模拟任务未完成（勾选后阻止关闭）", AutoSize = true, Margin = new Padding(0, 24, 0, 0) };
        panel.Controls.Add(busy);
        form.FormClosing += (_, args) => args.Cancel = busy.Checked || File.Exists(Path.Combine(AppContext.BaseDirectory, "busy-fixture.flag"));
        form.Controls.Add(panel);
        var ready = Environment.GetEnvironmentVariable("AI_FIRST_WORKSPACE_READY_FILE");
        if (string.IsNullOrEmpty(ready)) { Application.Run(form); return; }
        form.ShowInTaskbar = false;
        var handle = form.Handle;
        File.WriteAllText(ready + ".tmp", JsonSerializer.Serialize(new { processId = Environment.ProcessId, window = handle.ToInt64() }));
        File.Move(ready + ".tmp", ready);
        form.FormClosed += (_, _) => Application.ExitThread();
        using var recovery = new System.Windows.Forms.Timer { Interval = 100 };
        recovery.Tick += (_, _) =>
        {
            if (Directory.Exists(Path.GetDirectoryName(ready))) return;
            recovery.Stop();
            form.ShowInTaskbar = true;
            form.Show();
        };
        recovery.Start();
        Application.Run();
    }
}
