using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace AIFirst.Workspace;

internal sealed record UpdateAsset(string Name, string Url, long Size, string Digest);
internal sealed record UpdateRelease(string Version, UpdateAsset Installer, UpdateAsset Portable, UpdateAsset Checksums);

internal sealed class UpdateClient : IDisposable
{
    internal const string Repository = "https://github.com/feifeigong/ai-first-tools";
    internal const string ReleasesApi = "https://api.github.com/repos/feifeigong/ai-first-tools/releases?per_page=100";
    internal static string CurrentVersion => typeof(App).Assembly.GetName().Version!.ToString(3);
    private readonly HttpClient client;

    internal UpdateClient(HttpMessageHandler? handler = null)
    {
        client = new HttpClient(handler ?? new HttpClientHandler { AllowAutoRedirect = false });
        client.Timeout = Timeout.InfiniteTimeSpan;
        client.DefaultRequestHeaders.UserAgent.ParseAdd("AI-First-Tools/" + CurrentVersion);
        client.DefaultRequestHeaders.Add("X-GitHub-Api-Version", "2022-11-28");
    }

    internal static Version ParseVersion(string text)
    {
        if (!Regex.IsMatch(text, @"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")) throw new InvalidDataException("版本信息无效。");
        return Version.Parse(text);
    }

    internal static void ValidateAsset(UpdateAsset asset, string version, string name)
    {
        if (asset.Name != name || asset.Size <= 0 || asset.Size > 1024L * 1024 * 1024 || !Regex.IsMatch(asset.Digest, "^[a-fA-F0-9]{64}$") ||
            asset.Url != Repository + "/releases/download/v" + version + "/" + name)
            throw new InvalidDataException("更新包信息不完整或来源不匹配。");
    }

    internal static UpdateRelease? SelectRelease(string json, string current)
    {
        var currentVersion = ParseVersion(current);
        using var document = JsonDocument.Parse(json);
        if (document.RootElement.ValueKind != JsonValueKind.Array) throw new InvalidDataException("更新列表无效。");
        UpdateRelease? latest = null;
        foreach (var release in document.RootElement.EnumerateArray())
        {
            try
            {
                if (release.GetProperty("draft").GetBoolean() || release.GetProperty("published_at").ValueKind != JsonValueKind.String) continue;
                var tag = release.GetProperty("tag_name").GetString() ?? "";
                if (!tag.StartsWith('v')) continue;
                var version = tag[1..];
                var parsed = ParseVersion(version);
                if (parsed <= currentVersion || latest is not null && parsed <= ParseVersion(latest.Version)) continue;
                UpdateAsset Asset(string name)
                {
                    var matches = release.GetProperty("assets").EnumerateArray().Where(asset => asset.GetProperty("name").GetString() == name).ToArray();
                    if (matches.Length != 1) throw new InvalidDataException("更新包缺失或重复。");
                    var data = matches[0];
                    if (data.GetProperty("state").GetString() != "uploaded") throw new InvalidDataException("更新尚未上传完成。");
                    var digest = data.GetProperty("digest").GetString() ?? "";
                    if (!digest.StartsWith("sha256:", StringComparison.Ordinal)) throw new InvalidDataException("更新缺少校验值。");
                    var asset = new UpdateAsset(name, data.GetProperty("browser_download_url").GetString() ?? "", data.GetProperty("size").GetInt64(), digest[7..]);
                    ValidateAsset(asset, version, name);
                    return asset;
                }
                latest = new UpdateRelease(version, Asset("AI-First-Tools-Setup-" + version + ".exe"), Asset("AI-First-Tools-Portable-" + version + "-win-x64.zip"), Asset("SHA256SUMS.txt"));
            }
            catch (Exception exception) when (exception is InvalidDataException or InvalidOperationException or FormatException or ArgumentException or KeyNotFoundException or OverflowException) { }
        }
        return latest;
    }

    internal async Task<UpdateRelease?> CheckAsync(CancellationToken cancellation)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        using var response = await GetAsync(new Uri(ReleasesApi), false, deadline.Token);
        if (response.StatusCode == System.Net.HttpStatusCode.Forbidden || (int)response.StatusCode == 429) throw new HttpRequestException("检查更新太频繁，请稍后再试。", null, response.StatusCode);
        response.EnsureSuccessStatusCode();
        var bytes = await ReadLimitedAsync(response, 4 * 1024 * 1024, deadline.Token);
        return SelectRelease(Encoding.UTF8.GetString(bytes), CurrentVersion);
    }

    private async Task<HttpResponseMessage> GetAsync(Uri address, bool asset, CancellationToken cancellation)
    {
        for (var redirects = 0; redirects <= 5; redirects++)
        {
            if (!AllowedAddress(address, asset)) throw new InvalidDataException("更新下载地址不安全。");
            var response = await client.GetAsync(address, HttpCompletionOption.ResponseHeadersRead, cancellation);
            if ((int)response.StatusCode is not (301 or 302 or 303 or 307 or 308)) return response;
            var location = response.Headers.Location;
            response.Dispose();
            if (location is null) throw new InvalidDataException("更新下载跳转无效。");
            address = location.IsAbsoluteUri ? location : new Uri(address, location);
        }
        throw new InvalidDataException("更新下载跳转过多。");
    }

    internal static bool AllowedAddress(Uri address, bool asset) => address.Scheme == "https" && address.IsDefaultPort && string.IsNullOrEmpty(address.UserInfo) &&
        (asset ? address.Host == "github.com" && address.AbsolutePath.StartsWith("/feifeigong/ai-first-tools/releases/download/", StringComparison.Ordinal) || address.Host == "release-assets.githubusercontent.com" || address.Host == "objects.githubusercontent.com" : address.AbsoluteUri == ReleasesApi);

    private static async Task<byte[]> ReadLimitedAsync(HttpResponseMessage response, int limit, CancellationToken cancellation)
    {
        if (response.Content.Headers.ContentLength > limit) throw new InvalidDataException("更新信息过大。");
        using var input = await response.Content.ReadAsStreamAsync(cancellation);
        using var output = new MemoryStream();
        var buffer = new byte[16384];
        int count;
        while ((count = await input.ReadAsync(buffer, cancellation)) > 0)
        {
            if (output.Length + count > limit) throw new InvalidDataException("更新信息过大。");
            output.Write(buffer, 0, count);
        }
        return output.ToArray();
    }

    internal static void ValidateChecksums(string text, UpdateAsset asset)
    {
        var matches = text.Split('\n').Select(line => Regex.Match(line.TrimEnd('\r'), @"^([a-fA-F0-9]{64})  (.+)$")).Where(match => match.Success && match.Groups[2].Value == asset.Name).ToArray();
        if (matches.Length != 1 || !string.Equals(matches[0].Groups[1].Value, asset.Digest, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("更新校验文件与发布包不匹配。");
    }

    internal async Task DownloadAsync(UpdateRelease release, UpdateAsset asset, string destination, IProgress<double>? progress, CancellationToken cancellation)
    {
        ValidateAsset(asset, release.Version, asset == release.Installer ? "AI-First-Tools-Setup-" + release.Version + ".exe" : "AI-First-Tools-Portable-" + release.Version + "-win-x64.zip");
        ValidateAsset(release.Checksums, release.Version, "SHA256SUMS.txt");
        if (release.Checksums.Size > 65536) throw new InvalidDataException("校验文件过大。");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromMinutes(15));
        using var checksumResponse = await GetAsync(new Uri(release.Checksums.Url), true, deadline.Token);
        checksumResponse.EnsureSuccessStatusCode();
        var checksums = await ReadLimitedAsync(checksumResponse, 65536, deadline.Token);
        if (checksums.Length != release.Checksums.Size || !string.Equals(Convert.ToHexString(SHA256.HashData(checksums)), release.Checksums.Digest, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("校验文件下载不完整。");
        ValidateChecksums(Encoding.UTF8.GetString(checksums), asset);
        var partial = destination + ".partial";
        try
        {
            using var response = await GetAsync(new Uri(asset.Url), true, deadline.Token);
            response.EnsureSuccessStatusCode();
            if (response.Content.Headers.ContentLength is long length && length != asset.Size) throw new InvalidDataException("更新包大小不匹配。");
            using var input = await response.Content.ReadAsStreamAsync(deadline.Token);
            await using (var output = new FileStream(partial, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536, true))
            {
                using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
                var buffer = new byte[65536];
                long received = 0;
                int count;
                while ((count = await input.ReadAsync(buffer, deadline.Token)) > 0)
                {
                    received += count;
                    if (received > asset.Size) throw new InvalidDataException("更新包大小不匹配。");
                    hash.AppendData(buffer, 0, count);
                    await output.WriteAsync(buffer.AsMemory(0, count), deadline.Token);
                    progress?.Report(received * 100.0 / asset.Size);
                }
                if (received != asset.Size || !string.Equals(Convert.ToHexString(hash.GetHashAndReset()), asset.Digest, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("更新包校验未通过，请重新下载。");
            }
            File.Move(partial, destination);
        }
        finally { if (File.Exists(partial)) File.Delete(partial); }
    }

    public void Dispose() => client.Dispose();
}
