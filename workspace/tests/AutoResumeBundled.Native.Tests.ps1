param([Parameter(Mandatory=$true)][string]$Package,[Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference='Stop'
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('ai-first-native-bundle-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
$env:LOCALAPPDATA=Join-Path $fixture 'local'
$env:APPDATA=Join-Path $fixture 'roaming'
$env:CODEX_HOME=Join-Path $fixture 'codex'
$env:PATH=Join-Path $env:SystemRoot 'System32'
. (Join-Path $Package 'assets\auto-resume-bundled.ps1') -FunctionsOnly
function Connect-Resume { return $false }
$script:fakeRun=$null
$runKey=$fixture
function Get-BundledRunValue { $script:fakeRun }
function New-ItemProperty { param($LiteralPath,$Name,$Value,$PropertyType,[switch]$Force) $script:fakeRun=$Value }
function Remove-ItemProperty { param($LiteralPath,$Name) $script:fakeRun=$null }
$state=Join-Path $env:LOCALAPPDATA 'vibcoding\codex-auto-resume'
New-Item -ItemType Directory -Path $state -Force | Out-Null
@{enabled=$false;poll_seconds=5;state_dir=$state;codex_home=$env:CODEX_HOME;auto_redeem_weekly_reset=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $state 'config.json') -Encoding UTF8
# The production loader accepts UTF-8 JSON without a BOM.
$config=Join-Path $state 'config.json';[IO.File]::WriteAllText($config,[IO.File]::ReadAllText($config),[Text.UTF8Encoding]::new($false))
$checks=[ordered]@{}
function Require([bool]$Value){if(!$Value){throw 'Native bundled background assertion failed'}}
try {
    $initial=Invoke-BundledAction 'status'; Require($initial.installed -and !$initial.running)
    $value=Invoke-BundledAction 'start'; Require($value.running -and $value.watcherCount -eq 1);$checks.startWithoutExternalRuntime=$true
    $value=Invoke-BundledAction 'start'; Require($value.watcherCount -eq 1);$checks.singleInstance=$true
    $value=Invoke-BundledAction 'autostart-on';Require($value.autostart -and $value.running)
    $value=Invoke-BundledAction 'stop';Require(!$value.running -and !$value.autostart)
    Start-Sleep -Seconds 2;Require(!(Invoke-BundledAction 'status').running);$checks.stopRemainsStopped=$true
    $value=Invoke-BundledAction 'start';Require($value.running)
    $value=Invoke-BundledAction 'prepare-update';Require(!$value.running)
    $value=Invoke-BundledAction 'finish-update';Require($value.running -and !$value.autostart);$checks.updateRestoresBackground=$true
    $value=Invoke-BundledAction 'autostart-on';Require($value.autostart)
    $value=Invoke-BundledAction 'uninstall';Require(!$value.running -and !$value.autostart);$checks.uninstallRemovesBackgroundAndStartup=$true
    @{passed=$true;checks=$checks;scope='Actual frozen process and production controls; synthetic disabled work, mocked registry and legacy discovery, no user configuration or model requests'}|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $Report -Encoding UTF8
    Get-Content -LiteralPath $Report
} finally { Stop-BundledWatcher }
