$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\assets\auto-resume-bundled.ps1') -FunctionsOnly
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('ai-first-bundled-tests-'+[guid]::NewGuid().ToString('N'))
$settingsDirectory=Join-Path $testRoot 'settings'
$bundledExecutable=Join-Path $testRoot 'tools\auto-resume\AI一手续跑后台.exe'
$bundledPreference=Join-Path $settingsDirectory 'bundled-auto-resume-startup.json'
$updateReceipt=Join-Path $settingsDirectory 'auto-resume-update.json'
$runKey=$testRoot
New-Item -ItemType Directory -Path (Split-Path $bundledExecutable -Parent),$settingsDirectory -Force | Out-Null
[IO.File]::WriteAllText($bundledExecutable,'synthetic fixture, never executed')
$script:results=[Collections.Generic.List[object]]::new()
$script:calls=[Collections.Generic.List[string]]::new()
function Reset-Fixture {
    $script:fakeRunning=$false; $script:fakeLegacy=$false; $script:legacyRunning=$false; $script:legacyAuto=$false; $script:fakeRun=$null; $script:calls.Clear()
    foreach($file in @($bundledPreference,$updateReceipt)){if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}}
}
function Connect-Resume { return $script:fakeLegacy }
function Get-Watchers { if($script:legacyRunning){[pscustomobject]@{ProcessId=501}} }
function Get-ResumeStatus { param($Installed) @{autostart=$script:legacyAuto} }
function Set-ResumeAutostart { param($Enabled) $script:legacyAuto=$Enabled; $script:calls.Add('legacy-startup-off') }
function Invoke-ResumeAction { param($RequestedAction) if($RequestedAction -eq 'stop'){$script:legacyRunning=$false;$script:calls.Add('legacy-stop')} }
function Get-BundledWatchers { if($script:fakeRunning){[pscustomobject]@{ProcessId=9001}} }
function Get-BundledRunValue { $script:fakeRun }
function New-ItemProperty { param($LiteralPath,$Name,$Value,$PropertyType,[switch]$Force) $script:fakeRun=$Value; $script:calls.Add('run-on') }
function Remove-ItemProperty { param($LiteralPath,$Name) $script:fakeRun=$null; $script:calls.Add('run-off') }
function Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,[switch]$PassThru,[switch]$Wait)
    if($FilePath -ne $bundledExecutable -or $WindowStyle -ne 'Hidden'){throw 'Unsafe packaged launch'}
    if($ArgumentList -eq '--request-stop'){$script:fakeRunning=$false;$script:calls.Add('stop');return [pscustomobject]@{ExitCode=0}}
    if(($ArgumentList -join ' ') -ne 'watch --quiet' -or $env:AI_FIRST_MANUAL_WATCH -ne '1'){throw 'Manual launch did not use packaged service'}
    $script:fakeRunning=$true; $script:calls.Add('start'); return [pscustomobject]@{HasExited=$false}
}
function Require([bool]$Condition){if(!$Condition){throw 'Assertion failed'}}
function Check([string]$Name,[scriptblock]$Test){Reset-Fixture;try{& $Test;$script:results.Add(@{name=$Name;passed=$true})}catch{$script:results.Add(@{name=$Name;passed=$false;error=$_.Exception.Message})}}
Check 'Fresh installation works without any legacy tool or external Python' {
    $value=Invoke-BundledAction 'status'; Require($value.installed -and !$value.running -and !$value.autostart)
    $value=Invoke-BundledAction 'start'; Require($value.running -and $value.watcherCount -eq 1 -and !$value.autostart)
}
Check 'Repeated enable does not create another watcher' {
    $null=Invoke-BundledAction 'start'; $null=Invoke-BundledAction 'start'
    Require(@($script:calls|Where-Object {$_ -eq 'start'}).Count -eq 1)
}
Check 'Stop removes startup and shuts down only the packaged watcher' {
    $null=Invoke-BundledAction 'autostart-on'; $null=Invoke-BundledAction 'start'; $value=Invoke-BundledAction 'stop'
    Require(!$value.running -and !$value.autostart -and (Get-BundledPreference) -eq $false)
}
Check 'Startup switch does not launch or terminate current work' {
    $value=Invoke-BundledAction 'autostart-on'; Require($value.autostart -and !$value.running)
    $null=Invoke-BundledAction 'start'; $value=Invoke-BundledAction 'autostart-off'; Require($value.running -and !$value.autostart)
}
Check 'Upgrade stops and restores background without changing autostart' {
    $null=Invoke-BundledAction 'start'; $null=Invoke-BundledAction 'prepare-update'; Require(!$script:fakeRunning -and (Test-Path -LiteralPath $updateReceipt))
    $value=Invoke-BundledAction 'finish-update'; Require($value.running -and !$value.autostart -and !(Test-Path -LiteralPath $updateReceipt))
}
Check 'Uninstall stops background and removes only owned startup' {
    $null=Invoke-BundledAction 'start'; $null=Invoke-BundledAction 'autostart-on'; $value=Invoke-BundledAction 'uninstall'
    Require(!$value.running -and !$value.autostart -and $null -eq $script:fakeRun)
}
Check 'Legacy process is adopted and startup moves to the packaged entry' {
    $script:fakeLegacy=$true; $script:legacyRunning=$true; $script:legacyAuto=$true
    $value=Invoke-BundledAction 'start'; Require($value.watcherCount -eq 1 -and !$script:calls.Contains('start'))
    $value=Invoke-BundledAction 'autostart-on'; Require($value.autostart -and !$script:legacyAuto -and $script:calls.Contains('legacy-startup-off'))
}
Check 'Another installation startup registration is preserved' {
    $script:fakeRun='unrelated registration';$rejected=$false
    try{$null=Invoke-BundledAction 'autostart-on'}catch{$rejected=$true}
    Require($rejected -and $script:fakeRun -eq 'unrelated registration')
}
Check 'First upgrade adopts existing running and autostart state into the bundled service' {
    $script:fakeLegacy=$true;$script:legacyRunning=$true;$script:legacyAuto=$true
    $value=Invoke-BundledAction 'finish-update'
    Require($value.running -and $value.autostart -and !$script:legacyRunning -and !$script:legacyAuto -and $script:fakeRunning)
}
$script:results|ConvertTo-Json -Depth 4
if(@($script:results|Where-Object {!$_.passed}).Count){exit 1}
