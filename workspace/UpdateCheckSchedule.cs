using System;

namespace AIFirst.Workspace;

// Session state only: a previous launch's negative result must never suppress startup.
internal sealed class UpdateCheckSchedule
{
    private DateTimeOffset? lastAttempt;
    private DateTimeOffset nextAttempt = DateTimeOffset.MinValue;
    private int failures;
    private static readonly int[] RetryMinutes = { 1, 5, 15, 60 };

    internal bool IsDue(DateTimeOffset now, bool wake = false) => lastAttempt is null ||
        now >= nextAttempt || wake && failures == 0 && now - lastAttempt.Value >= TimeSpan.FromMinutes(2);

    internal void Started(DateTimeOffset now) => lastAttempt = now;
    internal void Succeeded(DateTimeOffset now)
    {
        failures = 0;
        nextAttempt = now.AddMinutes(10);
    }
    internal void Failed(DateTimeOffset now, bool rateLimited)
    {
        var minutes = rateLimited ? 60 : RetryMinutes[Math.Min(failures, RetryMinutes.Length - 1)];
        failures++;
        nextAttempt = now.AddMinutes(minutes);
    }
}
