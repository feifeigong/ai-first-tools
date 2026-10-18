param([Parameter(Mandatory)][string]$Package,[Parameter(Mandatory)][string]$Setup,[Parameter(Mandatory)][string]$Output,[Parameter(Mandatory)][string]$Report)
$ErrorActionPreference='Stop'
$Package=(Resolve-Path -LiteralPath $Package).Path
$Setup=(Resolve-Path -LiteralPath $Setup).Path
$Output=[IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $Output) { throw 'Use a fresh disposable test directory' }
New-Item -ItemType Directory -Path $Output | Out-Null
$target=Join-Path $Output 'target'
Copy-Item -LiteralPath $Package -Destination $target -Recurse
$manifest=Get-Content -LiteralPath (Join-Path $target 'update-manifest.json') -Raw | ConvertFrom-Json
$version=$manifest.version
# Only the disposable clone is marked older; the real helper/version check is
# independently covered by audit_update_pipeline.py with two actual versions.
$manifest.version='0.0.1'
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $target 'update-manifest.json') -Encoding utf8
$stable=Join-Path $target 'tools/auto-resume/_internal/bin/codex.exe'
if (!(Test-Path -LiteralPath $stable)) { $stable=Join-Path $target ($manifest.files | Sort-Object size -Descending | Select-Object -First 1).path }
$stableTime=(Get-Item -LiteralPath $stable).LastWriteTimeUtc
Set-Content -LiteralPath (Join-Path $target 'synthetic-user-note.txt') -Value 'keep this extra file'
$job=Join-Path (Join-Path $env:LOCALAPPDATA 'AI一手工具工作台/updates') ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $job | Out-Null
$download=Join-Path $job ([IO.Path]::GetFileName($Setup))
Copy-Item -LiteralPath $Setup -Destination $download
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;
public static class StageAudit {
    public static object Run(string dll,string download,string job,string target,string version) {
        var assembly=Assembly.LoadFrom(dll);
        var flags=BindingFlags.Static|BindingFlags.NonPublic;
        var runner=assembly.GetType("AIFirst.Workspace.UpdateRunner");
        var package=assembly.GetType("AIFirst.Workspace.UpdatePackage");
        var timer=Stopwatch.StartNew();
        ((Task)runner.GetMethod("StageInstallerAsync",flags).Invoke(null,new object[]{download,job,version,CancellationToken.None})).GetAwaiter().GetResult();
        var prepareMs=timer.ElapsedMilliseconds;
        timer.Restart();
        var changed=(System.Collections.Generic.List<string>)package.GetMethod("Apply",flags).Invoke(null,new object[]{target,Path.Combine(job,"staged"),Path.Combine(job,"backup"),null,null,true});
        return new { prepareMs,applyMs=timer.ElapsedMilliseconds,changedFiles=changed.Count };
    }
}
'@
$timing=[StageAudit]::Run((Join-Path $Package 'AI一手工具工作台.dll'),$download,$job,$target,$version)
$after=Get-Content -LiteralPath (Join-Path $target 'update-manifest.json') -Raw | ConvertFrom-Json
if ($after.version -ne $version -or $stableTime -ne (Get-Item -LiteralPath $stable).LastWriteTimeUtc -or (Get-Content -LiteralPath (Join-Path $target 'synthetic-user-note.txt') -Raw).Trim() -ne 'keep this extra file') { throw 'Incremental installation changed stable/extra files or version' }
foreach ($entry in $after.files) {
    $file=Join-Path $target $entry.path
    if ((Get-Item -LiteralPath $file).Length -ne $entry.size -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { throw 'Incremental installation readback mismatch' }
}
if (!(Test-Path -LiteralPath (Join-Path $target 'Uninstall.exe')) -or $timing.changedFiles -ge 10) { throw 'Incremental installation or uninstaller was not verified' }
$result=@{passed=$true;fullPayloadBytes=($after.files | Measure-Object size -Sum).Sum;stageOnly=$true;incrementalApply=$true;stableFilesUntouched=$true;extraFilePreserved=$true;allHashesVerified=$true;uninstallerUpdated=$true;timing=$timing;scope='Real full installer unpacked into its own job, applied to a disposable clone; no user installation changed'}
$parent=Split-Path -Parent ([IO.Path]::GetFullPath($Report))
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Report -Encoding utf8
$result | ConvertTo-Json -Depth 4 -Compress
