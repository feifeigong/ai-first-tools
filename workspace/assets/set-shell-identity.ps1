param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $InstallRoot 'assets/ShellLinkTarget.cs')
$target=Join-Path $InstallRoot 'AI一手工具工作台.exe'
$alias=Join-Path $InstallRoot 'AI一手工具箱.exe'
$icon=Join-Path $InstallRoot 'assets/ai-first-logo.ico'
$appId='AI.First.Tools.Toolbox'
$desktop=[Environment]::GetFolderPath('DesktopDirectory')
$programs=[Environment]::GetFolderPath('Programs')
$pins=Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar'
$links=@((Join-Path $desktop 'AI一手工具箱.lnk'),(Join-Path $programs 'AI一手工具箱/AI一手工具箱.lnk'),
    (Join-Path $pins 'AI一手工具箱.lnk'),(Join-Path $pins 'AI一手工具工作台.lnk'))
foreach($link in $links){
 if(!(Test-Path -LiteralPath $link)){continue}
 $owner=[AIFirst.Toolbox.ShellLinkTarget]::Read($link)
 if($owner -eq $target -or $owner -eq $alias){
  if(![AIFirst.Toolbox.ShellLinkTarget]::ApplyBranding($link,$owner,$appId,$icon)){throw 'Owned shortcut identity was not saved'}
  if([AIFirst.Toolbox.ShellLinkTarget]::ReadAppId($link) -ne $appId){throw 'Owned shortcut identity was not verified'}
 }
}
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ToolboxShellRefresh {
 [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e,uint f,IntPtr a,IntPtr b);
}
'@
[ToolboxShellRefresh]::SHChangeNotify(0x08000000,0,[IntPtr]::Zero,[IntPtr]::Zero)
