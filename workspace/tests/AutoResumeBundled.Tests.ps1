$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\assets\auto-resume-bundled.ps1') -FunctionsOnly
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('ai-first-bundled-tests-'+[guid]::NewGuid().ToString('N'))
$settingsDirectory=Join-Path $testRoot 'settings'
$bundleRoot=$testRoot
$workspaceExecutable=Join-Path $bundleRoot 'AI一手工具工作台.exe'
$bundledExecutable=Join-Path $testRoot 'tools\auto-resume\AI一手续跑后台.exe'
$bundledPreference=Join-Path $settingsDirectory 'bundled-auto-resume-startup.json'
$updateReceipt=Join-Path $settingsDirectory 'auto-resume-update.json'
$runKey=$testRoot
New-Item -ItemType Directory -Path (Split-Path $bundledExecutable -Parent),$settingsDirectory -Force | Out-Null
[IO.File]::WriteAllText($bundledExecutable,'synthetic fixture, never executed')
[IO.File]::WriteAllText($workspaceExecutable,'synthetic fixture, never executed')
$script:results=[Collections.Generic.List[object]]::new()
$script:calls=[Collections.Generic.List[string]]::new()
$script:monitorMutexes=[Collections.Generic.List[Threading.Mutex]]::new()
function Reset-Fixture {
    $script:policy=$null
    foreach($monitorMutex in $script:monitorMutexes){$monitorMutex.ReleaseMutex();$monitorMutex.Dispose()}
    $script:monitorMutexes.Clear()
    $script:fakeRunning=$false; $script:fakeLegacy=$false; $script:legacyRunning=$false; $script:legacyAuto=$false; $script:fakeRun=$null; $script:owner=$bundledExecutable; $script:readyAfter=0; $script:readyChecks=0; $script:monitorResponds=$false; $script:monitorLaunchFails=$false; $script:calls.Clear()
    foreach($file in @($bundledPreference,$updateReceipt,(Join-Path $settingsDirectory 'active-data-profile.json'))){if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}}
    foreach($directory in @((Join-Path $settingsDirectory 'reset-notices'),(Join-Path $settingsDirectory 'memory-preview\reset-notices'))){
        foreach($name in @('monitor-owner.json','monitor-stop.json','reset-monitor-update.json')){
            $file=Join-Path $directory $name
            if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file -Force}
        }
    }
    $marker=Join-Path $bundleRoot 'development-preview.json'
    if(Test-Path -LiteralPath $marker){Remove-Item -LiteralPath $marker -Force}
}
function Connect-Resume { return $script:fakeLegacy }
function Get-BundledAutomation {
    param($Operation='status')
    if(!$script:policy){$script:policy=@{resumeEnabled=$true;autoRedeem=$false;autoStartWindow=$false;timerStatus='waiting';nextResetAt=0}}
    switch($Operation){
        'resume-on'{$script:policy.resumeEnabled=$true}
        'resume-off'{$script:policy.resumeEnabled=$false}
        'credit-on'{$script:policy.autoRedeem=$true}
        'credit-off'{$script:policy.autoRedeem=$false}
        'timer-on'{$script:policy.autoStartWindow=$true}
        'timer-off'{$script:policy.autoStartWindow=$false}
    }
    return $script:policy
}
function Get-Watchers { if($script:legacyRunning){[pscustomobject]@{ProcessId=501}} }
function Get-ResumeStatus { param($Installed) @{autostart=$script:legacyAuto} }
function Set-ResumeAutostart { param($Enabled) $script:legacyAuto=$Enabled; $script:calls.Add('legacy-startup-off') }
function Invoke-ResumeAction { param($RequestedAction) if($RequestedAction -eq 'stop'){$script:legacyRunning=$false;$script:calls.Add('legacy-stop')} }
function Get-BundledWatchers { if($script:fakeRunning){$script:readyChecks++;[pscustomobject]@{ProcessId=9001;ExecutablePath=$script:owner;Ready=($script:readyChecks -gt $script:readyAfter)}} }
function Get-BundledRunValue { $script:fakeRun }
function New-ItemProperty { param($LiteralPath,$Name,$Value,$PropertyType,[switch]$Force) $script:fakeRun=$Value; $script:calls.Add('run-on') }
function Remove-ItemProperty { param($LiteralPath,$Name) $script:fakeRun=$null; $script:calls.Add('run-off') }
function Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,[switch]$PassThru,[switch]$Wait)
    if($FilePath -eq $workspaceExecutable){
        if($ArgumentList -ne '--reset-monitor' -or $WindowStyle -ne 'Hidden' -or $WorkingDirectory -ne $bundleRoot){throw 'Unsafe monitor launch'}
        if($script:monitorLaunchFails){throw 'Synthetic monitor launch failure'}
        $script:calls.Add('monitor-start');return
    }
    if($FilePath -ne $bundledExecutable -or $WindowStyle -ne 'Hidden'){throw 'Unsafe packaged launch'}
    if($ArgumentList -eq '--request-stop'){$script:fakeRunning=$false;$script:calls.Add('stop');return [pscustomobject]@{ExitCode=0}}
    if(($ArgumentList -join ' ') -ne 'watch --quiet' -or $env:AI_FIRST_MANUAL_WATCH -ne '1'){throw 'Manual launch did not use packaged service'}
    $script:fakeRunning=$true; $script:calls.Add('start'); return [pscustomobject]@{HasExited=$false}
}
function Start-Sleep {
    param($Milliseconds,$Seconds)
    if(!$script:monitorResponds){return}
    $directory=Get-ResetMonitorDirectory
    $ownerPath=Join-Path $directory 'monitor-owner.json'
    $stopPath=Join-Path $directory 'monitor-stop.json'
    if((Test-Path -LiteralPath $ownerPath) -and (Test-Path -LiteralPath $stopPath)){
        $monitorOwner=Get-Content -LiteralPath $ownerPath -Raw -Encoding UTF8|ConvertFrom-Json
        $request=Get-Content -LiteralPath $stopPath -Raw -Encoding UTF8|ConvertFrom-Json
        if($monitorOwner.token -eq $request.token -and $monitorOwner.executable -eq $request.executable){
            Remove-Item -LiteralPath $ownerPath -Force
            $script:calls.Add('monitor-exit')
        }
    }
}
function Add-MonitorOwner([string]$Program=$workspaceExecutable, [switch]$Crashed){
    $directory=Get-ResetMonitorDirectory
    Write-ResetMonitorJson (Join-Path $directory 'monitor-owner.json') @{pid=9002;executable=$Program;token='synthetic-owner-token'}
    if(!$Crashed){
        $created=$false;$monitorMutex=[Threading.Mutex]::new($true,(Get-ResetMonitorMutexName $directory),[ref]$created)
        if(!$created){$monitorMutex.Dispose();throw 'Synthetic monitor mutex already exists'}
        $script:monitorMutexes.Add($monitorMutex)
    }
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
Check 'Credit permission can be disabled while resume stays active' {
    $null=Invoke-BundledAction 'resume-on'
    $null=Invoke-BundledAction 'credit-on'
    $value=Invoke-BundledAction 'credit-off'
    Require($value.running -and $value.resumeEnabled -and !$value.autoRedeem)
}
Check 'Credit permission can be prepared before resume without launching a watcher' {
    $value=Invoke-BundledAction 'credit-on'
    Require(!$value.running -and $value.autoRedeem -and !$script:calls.Contains('start'))
    $value=Invoke-BundledAction 'credit-off'
    Require(!$value.running -and !$value.autoRedeem -and !$script:calls.Contains('start'))
}
Check 'Timer-only opt-in never enables resume or cards and survives resume off' {
    $value=Invoke-BundledAction 'timer-on'
    Require($value.running -and !$value.resumeEnabled -and !$value.autoRedeem -and $value.autoStartWindow)
    $null=Invoke-BundledAction 'autostart-on'
    $value=Invoke-BundledAction 'resume-off'
    Require($value.running -and !$value.resumeEnabled -and $value.autoStartWindow -and $value.autostart)
    $value=Invoke-BundledAction 'timer-off'
    Require(!$value.running -and !$value.autostart)
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
Check 'Slow startup waits for readiness instead of treating a living process as ready' {
    $script:readyAfter=6
    $value=Invoke-BundledAction 'start'
    Require($value.running -and $script:readyChecks -gt 6 -and @($script:calls|Where-Object {$_ -eq 'start'}).Count -eq 1)
}
Check 'Another package owner is reused without launching or stopping it during update' {
    $script:fakeRunning=$true;$script:owner=Join-Path $testRoot 'other\tools\auto-resume\AI一手续跑后台.exe'
    $value=Invoke-BundledAction 'start'
    Require($value.running -and !$script:calls.Contains('start'))
    $null=Invoke-BundledAction 'prepare-update';$null=Invoke-BundledAction 'uninstall'
    Require($script:fakeRunning -and !$script:calls.Contains('stop') -and !(Test-Path -LiteralPath $updateReceipt))
}
Check 'Update requests an owned monitor normal exit and restores it hidden once' {
    Add-MonitorOwner;$script:monitorResponds=$true
    $null=Invoke-BundledAction 'prepare-update'
    $directory=Get-ResetMonitorDirectory
    $request=Get-Content -LiteralPath (Join-Path $directory 'monitor-stop.json') -Raw -Encoding UTF8|ConvertFrom-Json
    Require($request.token -eq 'synthetic-owner-token' -and $request.executable -eq $workspaceExecutable -and $request.reason -eq 'update')
    Require(!(Test-Path -LiteralPath (Join-Path $directory 'monitor-owner.json')) -and (Test-Path -LiteralPath (Join-Path $directory 'reset-monitor-update.json')))
    $null=Invoke-BundledAction 'finish-update';$null=Invoke-BundledAction 'finish-update'
    Require(@($script:calls|Where-Object {$_ -eq 'monitor-start'}).Count -eq 1 -and !(Test-Path -LiteralPath (Join-Path $directory 'reset-monitor-update.json')))
}
Check 'Uninstall stops its monitor even when a different package owns auto resume' {
    Add-MonitorOwner;$script:monitorResponds=$true
    $script:fakeRunning=$true;$script:owner=Join-Path $testRoot 'other\tools\auto-resume\AI一手续跑后台.exe'
    $directory=Get-ResetMonitorDirectory
    Write-ResetMonitorJson (Join-Path $directory 'reset-monitor-update.json') @{executable=$workspaceExecutable;restart=$true;reason='update'}
    $null=Invoke-BundledAction 'uninstall';$null=Invoke-BundledAction 'finish-update'
    $request=Get-Content -LiteralPath (Join-Path $directory 'monitor-stop.json') -Raw -Encoding UTF8|ConvertFrom-Json
    Require($request.reason -eq 'uninstall' -and $script:calls.Contains('monitor-exit') -and !$script:calls.Contains('monitor-start'))
    Require($script:fakeRunning -and !$script:calls.Contains('stop') -and !(Test-Path -LiteralPath (Join-Path $directory 'reset-monitor-update.json')))
}
Check 'Another package monitor owner and update receipt are untouched' {
    $foreign=Join-Path $testRoot 'other\AI一手工具工作台.exe';Add-MonitorOwner $foreign
    $directory=Get-ResetMonitorDirectory;$ownerPath=Join-Path $directory 'monitor-owner.json';$receipt=Join-Path $directory 'reset-monitor-update.json'
    Write-ResetMonitorJson $receipt @{executable=$foreign;restart=$true;reason='update'}
    $ownerBefore=[IO.File]::ReadAllText($ownerPath);$receiptBefore=[IO.File]::ReadAllText($receipt)
    $null=Invoke-BundledAction 'prepare-update';$null=Invoke-BundledAction 'uninstall';$null=Invoke-BundledAction 'finish-update'
    Require([IO.File]::ReadAllText($ownerPath) -eq $ownerBefore -and [IO.File]::ReadAllText($receipt) -eq $receiptBefore)
    Require(!(Test-Path -LiteralPath (Join-Path $directory 'monitor-stop.json')) -and !$script:calls.Contains('monitor-start'))
}
Check 'Unresponsive monitor blocks update without forcing it or stopping auto resume' {
    Add-MonitorOwner;$script:fakeRunning=$true;$rejected=$false
    try{$null=Invoke-BundledAction 'prepare-update'}catch{$rejected=$true}
    Require($rejected -and (Test-Path -LiteralPath (Join-Path (Get-ResetMonitorDirectory) 'monitor-owner.json')))
    Require($script:fakeRunning -and !$script:calls.Contains('stop') -and !$script:calls.Contains('monitor-exit'))
}
Check 'An incomplete owned monitor record is preserved without sending a stop' {
    $directory=Get-ResetMonitorDirectory;$ownerPath=Join-Path $directory 'monitor-owner.json'
    Write-ResetMonitorJson $ownerPath @{pid=9002;executable=$workspaceExecutable;token=''}
    $before=[IO.File]::ReadAllText($ownerPath);$rejected=$false
    try{$null=Invoke-BundledAction 'prepare-update'}catch{$rejected=$true}
    Require($rejected -and [IO.File]::ReadAllText($ownerPath) -eq $before)
    Require(!(Test-Path -LiteralPath (Join-Path $directory 'monitor-stop.json')) -and !(Test-Path -LiteralPath (Join-Path $directory 'reset-monitor-update.json')))
}
Check 'Monitor restart failure preserves the receipt for a later retry' {
    Add-MonitorOwner;$script:monitorResponds=$true;$null=Invoke-BundledAction 'prepare-update'
    $script:monitorLaunchFails=$true;$rejected=$false
    try{$null=Invoke-BundledAction 'finish-update'}catch{$rejected=$true}
    Require($rejected -and (Test-Path -LiteralPath (Join-Path (Get-ResetMonitorDirectory) 'reset-monitor-update.json')))
    $script:monitorLaunchFails=$false;$null=Invoke-BundledAction 'finish-update'
    Require($script:calls.Contains('monitor-start'))
}
Check 'Preview monitor handoff stays separate from the installed reminder data' {
    Add-MonitorOwner
    $installedOwner=Join-Path (Get-ResetMonitorDirectory) 'monitor-owner.json'
    $before=[IO.File]::ReadAllText($installedOwner)
    [IO.File]::WriteAllText((Join-Path $bundleRoot 'development-preview.json'),'{}')
    Add-MonitorOwner;$script:monitorResponds=$true
    $null=Invoke-BundledAction 'prepare-update'
    Require([IO.File]::ReadAllText($installedOwner) -eq $before)
    Require((Get-ResetMonitorDirectory) -eq (Join-Path $settingsDirectory 'memory-preview\reset-notices'))
    Require(!(Test-Path -LiteralPath (Join-Path (Get-ResetMonitorDirectory) 'monitor-owner.json')))
}
Check 'A crashed owned monitor is reclaimed without a stop request and restored after update' {
    Add-MonitorOwner -Crashed
    $directory=Get-ResetMonitorDirectory
    $null=Invoke-BundledAction 'prepare-update'
    Require(!(Test-Path -LiteralPath (Join-Path $directory 'monitor-owner.json')) -and !(Test-Path -LiteralPath (Join-Path $directory 'monitor-stop.json')))
    Require(Test-Path -LiteralPath (Join-Path $directory 'reset-monitor-update.json'))
    $null=Invoke-BundledAction 'finish-update'
    Require($script:calls.Contains('monitor-start'))
}
Check 'Formal upgrade keeps the selected preview reminder data and normal lifecycle' {
    $binding=Join-Path $settingsDirectory 'active-data-profile.json'
    [IO.File]::WriteAllText($binding,'{"format":"ai-first-data-profile-v1","profile":"memory-preview"}')
    Require((Get-ResetMonitorDirectory) -eq (Join-Path $settingsDirectory 'memory-preview\reset-notices'))
    Add-MonitorOwner;$script:monitorResponds=$true
    $null=Invoke-BundledAction 'prepare-update';$null=Invoke-BundledAction 'finish-update'
    Require($script:calls.Contains('monitor-exit') -and $script:calls.Contains('monitor-start'))
    Require([IO.File]::ReadAllText($binding) -eq '{"format":"ai-first-data-profile-v1","profile":"memory-preview"}')
}
Check 'Invalid profile bindings fail closed before reminder or resume changes' {
    foreach($text in @('{"format":"unknown","profile":"memory-preview"}','{"format":"ai-first-data-profile-v1","profile":"../other"}','{"format":"ai-first-data-profile-v1","profile":"default","path":"other"}')){
        $binding=Join-Path $settingsDirectory 'active-data-profile.json';[IO.File]::WriteAllText($binding,$text)
        $rejected=$false;try{$null=Invoke-BundledAction 'prepare-update'}catch{$rejected=$true}
        Require($rejected -and $script:calls.Count -eq 0 -and [IO.File]::ReadAllText($binding) -eq $text)
    }
}
Check 'Development preview ignores formal binding and stays isolated' {
    [IO.File]::WriteAllText((Join-Path $bundleRoot 'development-preview.json'),'{}')
    [IO.File]::WriteAllText((Join-Path $settingsDirectory 'active-data-profile.json'),'invalid')
    Require((Get-ResetMonitorDirectory) -eq (Join-Path $settingsDirectory 'memory-preview\reset-notices'))
}
Check 'A crashed foreign monitor is never reclaimed by this package' {
    Add-MonitorOwner (Join-Path $testRoot 'other\AI一手工具工作台.exe') -Crashed
    $ownerPath=Join-Path (Get-ResetMonitorDirectory) 'monitor-owner.json';$before=[IO.File]::ReadAllText($ownerPath)
    $null=Invoke-BundledAction 'prepare-update';$null=Invoke-BundledAction 'uninstall'
    Require([IO.File]::ReadAllText($ownerPath) -eq $before)
    Require(!(Test-Path -LiteralPath (Join-Path (Get-ResetMonitorDirectory) 'reset-monitor-update.json')))
}
Check 'Stale cleanup rechecks the owner token before deleting metadata' {
    Add-MonitorOwner -Crashed
    $directory=Get-ResetMonitorDirectory;$ownerPath=Join-Path $directory 'monitor-owner.json'
    Require(!(Remove-StaleOwnedResetMonitor $directory $workspaceExecutable 'old-token'))
    Require(Test-Path -LiteralPath $ownerPath)
    Require(Remove-StaleOwnedResetMonitor $directory $workspaceExecutable 'synthetic-owner-token')
}
foreach($monitorMutex in $script:monitorMutexes){$monitorMutex.ReleaseMutex();$monitorMutex.Dispose()}
$script:monitorMutexes.Clear()
$script:results|ConvertTo-Json -Depth 4
if(@($script:results|Where-Object {!$_.passed}).Count){exit 1}
