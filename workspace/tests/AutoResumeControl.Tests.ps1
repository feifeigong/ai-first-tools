$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\assets\auto-resume-control.ps1') -FunctionsOnly
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('ai-first-control-tests-' + [guid]::NewGuid().ToString('N'))
$settingsDirectory = Join-Path $testDirectory 'settings'
$startupFile = Join-Path $testDirectory 'startup\codex-auto-resume.vbs'
$connectionFile = Join-Path $settingsDirectory 'connection.json'
$disabledStartup = Join-Path $settingsDirectory 'codex-auto-resume.vbs.disabled'
$startupPreference = Join-Path $settingsDirectory 'startup-preference.json'
$fixtureRunner = Join-Path $testDirectory 'codex-auto-resume\run.py'
$fixturePython = Join-Path $testDirectory 'pythonw.exe'
New-Item -ItemType Directory -Path (Join-Path $testDirectory 'codex-auto-resume\src\codex_auto_resume'), (Split-Path $startupFile -Parent), $settingsDirectory -Force | Out-Null
[IO.File]::WriteAllText($fixtureRunner, '# synthetic fixture only')
[IO.File]::WriteAllText((Join-Path $testDirectory 'codex-auto-resume\src\codex_auto_resume\daemon.py'), '# synthetic fixture only')
[IO.File]::WriteAllText($fixturePython, 'synthetic fixture; never executed')
[IO.File]::WriteAllText($fixtureRunner, '# synthetic allow_background_watch')
[IO.File]::WriteAllText((Join-Path $testDirectory 'codex-auto-resume\src\codex_auto_resume\workspace_control.py'), '# synthetic fixture only')
$script:mutations = [Collections.Generic.List[string]]::new()
$script:results = [Collections.Generic.List[object]]::new()

function Reset-Fixture {
    if (Test-Path -LiteralPath $startupPreference) { Remove-Item -LiteralPath $startupPreference -Force }
    $script:denyTaskChanges = $false
    $script:taskFixture = [pscustomobject]@{ TaskName = $taskName; State = 'Running'; Settings = [pscustomobject]@{ Enabled = $true }; Actions = @([pscustomobject]@{ Arguments = ('"' + $fixtureRunner + '" watch --quiet'); Execute = $fixturePython }) }
    $script:processFixtures = @(
        [pscustomobject]@{ ProcessId = 1001; Name = 'pythonw.exe'; CommandLine = ('"' + $fixturePython + '" "' + $fixtureRunner + '" watch --quiet') },
        [pscustomobject]@{ ProcessId = 1002; Name = 'python.exe'; CommandLine = 'python.exe unrelated-job.py' },
        [pscustomobject]@{ ProcessId = 1003; Name = 'wscript.exe'; CommandLine = ('wscript.exe //B "' + $startupFile + '"') },
        [pscustomobject]@{ ProcessId = 1004; Name = 'wscript.exe'; CommandLine = 'wscript.exe unrelated-job.vbs' }
    )
    $script:mutations.Clear()
    $script:runner = $null
}
function Get-ScheduledTask { param($TaskName, $ErrorAction) return $script:taskFixture }
function Get-CimInstance {
    param($ClassName, $Filter)
    if ($Filter -match '^ProcessId=(\d+)$') { return @($script:processFixtures | Where-Object ProcessId -eq ([int]$Matches[1])) }
    if ($Filter -eq "Name='wscript.exe'") { return @($script:processFixtures | Where-Object Name -eq 'wscript.exe') }
    return @($script:processFixtures | Where-Object { $_.Name -in @('python.exe', 'pythonw.exe') })
}
function Disable-ScheduledTask { param($InputObject) if ($script:denyTaskChanges) { throw 'Access is denied' }; $InputObject.Settings.Enabled = $false; $script:mutations.Add('disable-task') }
function Enable-ScheduledTask { param($InputObject) $InputObject.Settings.Enabled = $true; $script:mutations.Add('enable-task') }
function Stop-ScheduledTask { param($InputObject) $InputObject.State = 'Ready'; $script:mutations.Add('stop-task') }
function Stop-Process { param($Id, [switch]$Force, $ErrorAction) $script:processFixtures = @($script:processFixtures | Where-Object ProcessId -ne $Id); $script:mutations.Add('stop-' + $Id) }
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle, [switch]$PassThru)
    if ($FilePath -ne $fixturePython -or $WindowStyle -ne 'Hidden' -or $WorkingDirectory -ne (Split-Path $fixtureRunner -Parent) -or $env:AI_FIRST_MANUAL_WATCH -ne '1') { throw 'Unsafe launch' }
    $script:processFixtures += [pscustomobject]@{ ProcessId = 1005; Name = 'pythonw.exe'; CommandLine = ('"' + $fixturePython + '" "' + $fixtureRunner + '" watch --quiet') }
    $script:mutations.Add('start')
    return [pscustomobject]@{ HasExited = $false }
}
function New-ScheduledTaskAction { throw 'Synthetic task scheduler unavailable' }
function Check([string]$Name, [scriptblock]$Test) {
    Reset-Fixture
    try { & $Test; $script:results.Add(@{ name = $Name; passed = $true }) }
    catch { $script:results.Add(@{ name = $Name; passed = $false; error = $_.Exception.Message }) }
}
function Require([bool]$Condition) { if (!$Condition) { throw 'Assertion failed' } }

Check 'Read-only status detects exactly one watcher and changes nothing' {
    $before = Test-Path -LiteralPath $connectionFile
    $value = Invoke-ResumeAction 'status'
    Require ($value.installed -and $value.running -and $value.autostart -and $value.watcherCount -eq 1)
    Require ($script:mutations.Count -eq 0 -and (Test-Path -LiteralPath $connectionFile) -eq $before)
}
Check 'Stop disables restart sources before stopping only the exact watcher' {
    [IO.File]::WriteAllText($startupFile, 'synthetic supervisor')
    $value = Invoke-ResumeAction 'stop'
    Require (!$value.running -and !$value.autostart -and $value.watcherCount -eq 0)
    Require ($script:mutations[0] -eq 'disable-task' -and $script:mutations.Contains('stop-1003') -and $script:mutations.Contains('stop-1001'))
    Require (@($script:processFixtures | Where-Object { $_.ProcessId -in @(1002, 1004) }).Count -eq 2)
    Require ((Test-Path -LiteralPath $disabledStartup) -and !(Test-Path -LiteralPath $startupFile))
}
Check 'Repeated start never creates a duplicate watcher or changes autostart' {
    $value = Invoke-ResumeAction 'start'
    Require ($value.running -and $value.watcherCount -eq 1 -and $script:mutations.Count -eq 0)
}
Check 'Start after stop creates one hidden watcher while autostart stays off' {
    $null = Invoke-ResumeAction 'stop'
    $value = Invoke-ResumeAction 'start'
    Require ($value.running -and !$value.autostart -and $value.watcherCount -eq 1)
    Require (@($script:mutations | Where-Object { $_ -eq 'start' }).Count -eq 1)
}
Check 'Changing autostart does not stop or start the current watcher' {
    $value = Invoke-ResumeAction 'autostart-off'
    Require ($value.running -and !$value.autostart -and !$script:mutations.Contains('stop-1001'))
    $value = Invoke-ResumeAction 'autostart-on'
    Require ($value.running -and $value.autostart -and !$script:mutations.Contains('start'))
}
Check 'Protected original task is controlled by the installed startup gate without elevation' {
    $script:denyTaskChanges = $true
    $value = Invoke-ResumeAction 'autostart-off'
    Require ($script:taskFixture.Settings.Enabled -and !$value.autostart -and $value.running)
    Require ((Get-StartupPreference) -eq $false)
    $value = Invoke-ResumeAction 'autostart-on'
    Require ($value.autostart -and $value.running -and !$script:mutations.Contains('start'))
}
Check 'Same-name task with unrelated arguments is rejected without mutations' {
    $script:taskFixture.Actions[0].Arguments = 'unrelated-job.py'
    $rejected = $false
    try { $null = Invoke-ResumeAction 'stop' } catch { $rejected = $true }
    Require ($rejected -and $script:mutations.Count -eq 0)
}
Check 'No PID file or matching substring can authorize stopping unrelated Python' {
    Require ($null -eq (Convert-WatcherCommand ('python.exe "' + $fixtureRunner + '" doctor')))
    Require ($null -eq (Convert-WatcherCommand 'python.exe "C:\other\run.py" watch --quiet'))
    Require ($null -eq (Convert-WatcherCommand ('python.exe "' + $fixtureRunner + '" watch --quiet --other')))
}
Check 'Missing Python fails before changing task or stopping any processes' {
    $script:taskFixture.Actions[0].Execute = Join-Path $testDirectory 'missing\pythonw.exe'
    $script:processFixtures = @()
    $rejected = $false
    try { $null = Invoke-ResumeAction 'stop' } catch { $rejected = $true }
    Require ($rejected -and $script:mutations.Count -eq 0)
}
Check 'No scheduler permission uses a correctly quoted Unicode startup file without starting it' {
    $script:taskFixture = $null
    $null = Invoke-ResumeAction 'autostart-on'
    $vbs = [IO.File]::ReadAllText($startupFile)
    Require ($vbs.Contains('sh.Run """' + $fixturePython + '"" ""' + $fixtureRunner + '"" watch --quiet", 0, True'))
    Require (!$script:mutations.Contains('start'))
}

$script:results | ConvertTo-Json -Depth 5
if (@($script:results | Where-Object { !$_.passed }).Count -gt 0) { exit 1 }
