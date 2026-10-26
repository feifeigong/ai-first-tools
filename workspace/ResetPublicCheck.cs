using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal static class ResetPublicCheck
{
    // Explicit diagnostic entry point: isolated storage and public HTTP only.
    // It never takes an alert, displays a notification, or controls auto resume.
    internal static async Task<int> RunAsync(string outputDirectory)
    {
        var output = Path.GetFullPath(outputDirectory);
        Directory.CreateDirectory(output);
        var fixture = Path.Combine(output, "newfixture-" + Guid.NewGuid().ToString("N"));
        var report = Path.Combine(output, "public-reset-feed-check.json");
        var temporary = Path.Combine(output, "public-reset-feed-check." + Guid.NewGuid().ToString("N") + ".tmp");
        var snapshot = new ResetNewsSnapshot(false, "公开消息核对未完成", "", null, Array.Empty<ResetNewsItem>());
        try
        {
            using var http = new HttpClient(new HttpClientHandler
            {
                UseCookies = false,
                UseDefaultCredentials = false,
                Credentials = null,
                AllowAutoRedirect = false,
                AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate
            }) { Timeout = Timeout.InfiniteTimeSpan };
            using var service = new ResetNewsService(fixture, http, () => DateTimeOffset.UtcNow);
            await service.RefreshAsync().ConfigureAwait(false);
            snapshot = service.Snapshot;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or HttpRequestException
            or JsonException or InvalidOperationException or OperationCanceledException or ArgumentException)
        {
            snapshot = snapshot with { Fresh = false, StatusText = "公开消息核对暂未通过" };
        }
        try
        {
            var result = new
            {
                fresh = snapshot.Fresh,
                partial = snapshot.Partial,
                status = snapshot.StatusText,
                @checked = snapshot.LastCheckedAt,
                verifiedItems = snapshot.Items.Where(item => item.Kind != "uncertain").Select(item => new { id = item.Id, kind = item.Kind, publishedAt = item.PublishedAt, historical = item.Historical }).ToArray(),
                pendingHistory = snapshot.Items.Where(item => item.Kind == "uncertain").Select(item => new { id = item.Id, publishedAt = item.PublishedAt }).ToArray()
            };
            await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false)).ConfigureAwait(false);
            File.Move(temporary, report, true);
            return snapshot.Fresh ? 0 : 1;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { return 1; }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
