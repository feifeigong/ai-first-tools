param([Parameter(Mandatory=$true)][string]$InstallDirectory)
$ErrorActionPreference='Stop'
$expected=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs/AI First Tools'))
if (![string]::Equals([IO.Path]::GetFullPath($InstallDirectory),$expected,[StringComparison]::OrdinalIgnoreCase)) { throw '安装位置不匹配。' }
if (!(Test-Path -LiteralPath (Join-Path $expected 'AI一手工具箱.exe') -PathType Leaf)) { throw '工具箱程序尚未准备好。' }
$legacy='AI一手工具工作台'
$programs=[Environment]::GetFolderPath('Programs')
$folder=Join-Path $programs $legacy
$links=@((Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) ($legacy+'.lnk')),(Join-Path $folder ($legacy+'.lnk')))
$owned=@((Join-Path $expected ($legacy+'.exe')),(Join-Path $expected 'AI一手工具箱.exe'))
$shell=New-Object -ComObject WScript.Shell
foreach($path in $links) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
    $link=$shell.CreateShortcut($path)
    if ($owned -contains $link.TargetPath) { Remove-Item -LiteralPath $path -Force }
}
# Remove only the now-empty legacy shortcut folder; extra user links survive.
if ((Test-Path -LiteralPath $folder -PathType Container) -and !(Get-ChildItem -LiteralPath $folder -Force | Select-Object -First 1)) {
    Remove-Item -LiteralPath $folder
}
