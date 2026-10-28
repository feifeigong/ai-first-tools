using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace AIFirst.Workspace;

internal static class WhatsNewVisualTests
{
    internal static int Render(string output)
    {
        var root=Path.GetFullPath(output);Directory.CreateDirectory(root);
        var fixture=Path.Combine(root,"fixture-"+Guid.NewGuid().ToString("N"));
        var checks=new Dictionary<string,bool>();
        try
        {
            var notes=ReleaseHighlights.Load(Path.Combine(AppContext.BaseDirectory,"assets","whats-new.json"),UpdateClient.CurrentVersion) ?? throw new InvalidDataException();
            var state=new ReleaseHighlightsState(fixture,notes.Version);
            foreach(var mode in new[]{"done","close","escape"})
            {
                var persisted=false;
                var window=new WhatsNewWindow(notes,()=>persisted=state.Acknowledge());
                if(mode=="close")window.Width=420;
                window.Show();window.UpdateLayout();window.Dispatcher.Invoke(()=>{},DispatcherPriority.ApplicationIdle);
                var bitmap=new RenderTargetBitmap((int)Math.Ceiling(window.ActualWidth),(int)Math.Ceiling(window.ActualHeight),96,96,PixelFormats.Pbgra32);
                bitmap.Render(window);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(bitmap));
                using(var file=File.Create(Path.Combine(root,"dialog-"+mode+".png")))encoder.Save(file);
                checks[mode+"Layout"] = window.ActualWidth>350 && window.ActualHeight<SystemParameters.WorkArea.Height && window.DismissButton.IsVisible;
                checks[mode+"Focus"] = window.DismissButton.IsKeyboardFocused;
                if(mode=="escape") window.RaiseEvent(new KeyEventArgs(Keyboard.PrimaryDevice,PresentationSource.FromVisual(window),Environment.TickCount,Key.Escape){RoutedEvent=Keyboard.PreviewKeyDownEvent});
                else (mode=="done"?window.DismissButton:window.CloseButton).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                checks[mode+"Acknowledged"] = persisted && !window.IsVisible && !new ReleaseHighlightsState(fixture,notes.Version).ShouldShow;
            }
            var passed=!checks.ContainsValue(false);
            File.WriteAllText(Path.Combine(root,"report.json"),JsonSerializer.Serialize(new{passed,checks,syntheticOnly=true,modelRequests=0},UpdatePackage.Json));
            return passed?0:1;
        }
        catch(Exception error)
        {
            File.WriteAllText(Path.Combine(root,"report.json"),JsonSerializer.Serialize(new{passed=false,errorType=error.GetType().Name,checks,syntheticOnly=true,modelRequests=0}));return 1;
        }
    }
}
