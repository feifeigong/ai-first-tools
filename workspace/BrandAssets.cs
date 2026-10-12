using System;
using System.IO;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace AIFirst.Workspace;

internal sealed class BrandAssets
{
    private readonly string savedPath;
    internal BrandAssets(string configuration) => savedPath = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(configuration))!, "brand-logo.image");

    internal ImageSource? Load()
    {
        foreach (var path in new[] { savedPath, Path.Combine(AppContext.BaseDirectory, "assets", "ai-first-logo.jpg"), Path.Combine(AppContext.BaseDirectory, "assets", "ai-first-logo.png"), Path.Combine(AppContext.BaseDirectory, "assets", "ai-first-logo.ico") })
        {
            if (!File.Exists(path)) continue;
            try { return Read(path, path.EndsWith("ai-first-logo.jpg", StringComparison.OrdinalIgnoreCase)); }
            catch (Exception exception) when (exception is IOException or NotSupportedException or FileFormatException or UnauthorizedAccessException) { App.Log(exception); }
        }
        return null;
    }

    internal ImageSource Save(string source)
    {
        var image = Read(source);
        Directory.CreateDirectory(Path.GetDirectoryName(savedPath)!);
        var temporary = savedPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.Copy(source, temporary); File.Move(temporary, savedPath, true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
        return image;
    }

    internal static BitmapFrame LoadWindowIcon()
    {
        using var stream = File.OpenRead(Path.Combine(AppContext.BaseDirectory, "assets", "ai-first-logo.ico"));
        var decoder = BitmapDecoder.Create(stream, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
        var image = decoder.Frames[decoder.Frames.Count - 1];
        image.Freeze();
        return image;
    }

    private static ImageSource Read(string path, bool wordmark = false)
    {
        using var stream = File.OpenRead(path);
        var image = new BitmapImage();
        image.BeginInit();
        image.CacheOption = BitmapCacheOption.OnLoad;
        image.StreamSource = stream;
        image.DecodePixelWidth = 800;
        image.EndInit();
        image.Freeze();
        if (wordmark)
        {
            var region = new System.Windows.Int32Rect((int)(image.PixelWidth * 0.10), (int)(image.PixelHeight * 0.305), (int)(image.PixelWidth * 0.81), (int)(image.PixelHeight * 0.40));
            var cropped = new CroppedBitmap(image, region);
            cropped.Freeze();
            return cropped;
        }
        return image;
    }
}
