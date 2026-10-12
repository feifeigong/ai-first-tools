using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;

namespace AIFirst.Workspace;

internal sealed record PackageFile(string Path, long Size, string Sha256);
internal sealed record PackageManifest(string Version, List<PackageFile> Files);

internal static class UpdatePackage
{
    internal const string AppExecutable = "AI一手工具工作台.exe";
    internal const string ManifestName = "update-manifest.json";
    internal static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true, WriteIndented = true };

    internal static string Resolve(string root, string relative)
    {
        if (string.IsNullOrEmpty(relative) || relative.Contains('\\') || relative.Split('/').Any(part => part.Length == 0 || part is "." or ".." || part.EndsWith('.') || part.EndsWith(' ') || part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || Regex.IsMatch(part, @"^(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])(\.|$)", RegexOptions.IgnoreCase))) throw new InvalidDataException("更新包含不安全的文件名。");
        var absoluteRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var target = Path.GetFullPath(Path.Combine(absoluteRoot, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!target.StartsWith(absoluteRoot, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("更新文件超出程序目录。");
        EnsureNoLinks(target);
        return target;
    }

    internal static void EnsureNoLinks(string path)
    {
        var current = Path.GetFullPath(path);
        if (current.StartsWith(@"\\", StringComparison.Ordinal)) throw new InvalidDataException("请把工作台放在本机磁盘后更新。");
        while (!string.IsNullOrEmpty(current))
        {
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("更新目录包含链接，为保护文件已停止更新。");
            current = Path.GetDirectoryName(current);
        }
    }

    internal static PackageManifest Read(string root, string? expected = null)
    {
        var path = Resolve(root, ManifestName);
        if (new FileInfo(path).Length > 8 * 1024 * 1024) throw new InvalidDataException("程序清单过大。");
        var manifest = JsonSerializer.Deserialize<PackageManifest>(File.ReadAllText(path), Json) ?? throw new InvalidDataException("程序清单无效。");
        Validate(root, manifest, expected);
        return manifest;
    }

    internal static void Validate(string root, PackageManifest manifest, string? expected = null)
    {
        UpdateClient.ParseVersion(manifest.Version);
        if (expected is not null && manifest.Version != expected || manifest.Files is null || manifest.Files.Count is < 1 or > 30000) throw new InvalidDataException("更新版本或程序清单不匹配。");
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var file in manifest.Files)
        {
            Resolve(root, file.Path);
            if (!paths.Add(file.Path) || file.Path.Equals(ManifestName, StringComparison.OrdinalIgnoreCase) || file.Size < 0 || file.Size > 1024L * 1024 * 1024 || !Regex.IsMatch(file.Sha256 ?? "", "^[a-fA-F0-9]{64}$")) throw new InvalidDataException("程序清单包含无效或重复文件。");
            total += file.Size;
        }
        if (total > 4L * 1024 * 1024 * 1024 || !paths.Contains(AppExecutable)) throw new InvalidDataException("程序包不完整或过大。");
    }

    internal static void Verify(string path, long size, string digest)
    {
        EnsureNoLinks(path);
        if (new FileInfo(path).Length != size) throw new InvalidDataException("更新文件大小不匹配。");
        using var stream = File.OpenRead(path);
        if (!string.Equals(Convert.ToHexString(SHA256.HashData(stream)), digest, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("更新文件校验未通过。");
    }

    internal static PackageManifest Extract(string archive, string destination, string version, CancellationToken cancellation)
    {
        EnsureNoLinks(destination);
        if (Directory.Exists(destination)) throw new InvalidDataException("更新暂存目录已存在。");
        using var zip = ZipFile.OpenRead(archive);
        if (zip.Entries.Count > 60000) throw new InvalidDataException("更新压缩包过大。");
        const string prefix = "AI-First-Tools/";
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var entry in zip.Entries)
        {
            if (entry.FullName == prefix) continue;
            if (!entry.FullName.StartsWith(prefix, StringComparison.Ordinal) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000) throw new InvalidDataException("更新压缩包包含外部文件或链接。");
            var relative = entry.FullName[prefix.Length..].TrimEnd('/');
            Resolve(destination, relative);
            if (!paths.Add(relative) || entry.Length > 1024L * 1024 * 1024 || (total += entry.Length) > 4L * 1024 * 1024 * 1024) throw new InvalidDataException("更新压缩包包含重复文件或过大文件。");
        }
        Directory.CreateDirectory(destination);
        foreach (var entry in zip.Entries.Where(entry => entry.FullName != prefix && !entry.FullName.EndsWith('/')))
        {
            cancellation.ThrowIfCancellationRequested();
            var path = Resolve(destination, entry.FullName[prefix.Length..]);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            entry.ExtractToFile(path);
        }
        var manifest = Read(destination, version);
        var files = manifest.Files.Select(file => file.Path).Append(ManifestName).ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (!files.SetEquals(zip.Entries.Where(entry => !entry.FullName.EndsWith('/')).Select(entry => entry.FullName[prefix.Length..]))) throw new InvalidDataException("更新包与程序清单不一致。");
        foreach (var file in manifest.Files)
        {
            cancellation.ThrowIfCancellationRequested();
            Verify(Resolve(destination, file.Path), file.Size, file.Sha256);
        }
        return manifest;
    }

    internal static List<string> Apply(string target, string staged, string backup, Action<int>? checkpoint = null)
    {
        var previous = Read(target);
        var next = Read(staged);
        if (UpdateClient.ParseVersion(next.Version) <= UpdateClient.ParseVersion(previous.Version)) throw new InvalidDataException("不能降级或重复更新。");
        var oldPaths = previous.Files.Select(file => file.Path).Append(ManifestName).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var file in next.Files)
        {
            Verify(Resolve(staged, file.Path), file.Size, file.Sha256);
            if (!oldPaths.Contains(file.Path) && File.Exists(Resolve(target, file.Path))) throw new InvalidDataException("新版文件与您额外放入的文件重名，为保护文件已停止更新。");
        }
        Backup(target, backup, oldPaths);
        var written = new List<string>();
        try
        {
            foreach (var relative in next.Files.Select(file => file.Path).Append(ManifestName))
            {
                var destination = Resolve(target, relative);
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                written.Add(relative);
                File.Copy(Resolve(staged, relative), destination, true);
                checkpoint?.Invoke(written.Count);
            }
            var newPaths = next.Files.Select(file => file.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
            foreach (var file in previous.Files.Where(file => !newPaths.Contains(file.Path)))
            {
                var path = Resolve(target, file.Path);
                if (!File.Exists(path)) continue;
                try { Verify(path, file.Size, file.Sha256); }
                catch (InvalidDataException) { continue; }
                written.Add(file.Path);
                File.Delete(path);
            }
            return written;
        }
        catch
        {
            Restore(target, backup, written);
            throw;
        }
    }

    internal static void Backup(string target, string backup, IEnumerable<string> paths)
    {
        if (Directory.Exists(backup)) throw new InvalidDataException("更新备份目录已存在。");
        Directory.CreateDirectory(backup);
        foreach (var relative in paths)
        {
            var source = Resolve(target, relative);
            if (!File.Exists(source)) continue;
            var destination = Resolve(backup, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            File.Copy(source, destination);
        }
    }

    internal static void Restore(string target, string backup, IEnumerable<string> changed)
    {
        var errors = new List<Exception>();
        foreach (var relative in changed.Reverse().Distinct(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                var destination = Resolve(target, relative);
                var source = Resolve(backup, relative);
                if (File.Exists(source)) { Directory.CreateDirectory(Path.GetDirectoryName(destination)!); File.Copy(source, destination, true); }
                else if (File.Exists(destination)) File.Delete(destination);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException) { errors.Add(exception); }
        }
        if (errors.Count > 0) throw new AggregateException("部分程序文件暂时被占用。更新备份已保留，请关闭其他工作台后恢复或重新安装。", errors);
    }
}
