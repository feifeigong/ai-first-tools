$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $Root "run.py"
$TaskName = "VibcodingCodexAutoResume"
$StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$StartupScript = Join-Path $StartupDir "codex-auto-resume.vbs"

$PythonW = Get-Command pythonw -ErrorAction SilentlyContinue
$Python = if ($PythonW) { $PythonW.Source } else { (Get-Command python).Source }

if (-not (Test-Path $Runner)) {
  throw "run.py not found: $Runner"
}

function Install-StartupVbs {
  New-Item -ItemType Directory -Force -Path $StartupDir | Out-Null
  $escapedPython = $Python.Replace("\", "\\")
  $escapedRunner = $Runner.Replace("\", "\\")
  $escapedRoot = $Root.Replace("\", "\\")
  $content = @"
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "$escapedRoot"
Do
  sh.Run """$escapedPython"" ""$escapedRunner"" watch --quiet", 0, True
  WScript.Sleep 5000
Loop
"@
  Set-Content -Path $StartupScript -Value $content -Encoding ASCII
  Write-Host "Installed startup script: $StartupScript"
}

$taskOk = $false
try {
  $Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Runner`" watch --quiet" -WorkingDirectory $Root
  $Trigger = New-ScheduledTaskTrigger -AtLogOn
  $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
  $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
  Start-ScheduledTask -TaskName $TaskName
  if (Test-Path $StartupScript) {
    Remove-Item $StartupScript -Force
    Write-Host "Removed startup script because the scheduled task is installed."
  }
  Write-Host "Installed scheduled task: $TaskName"
  $taskOk = $true
} catch {
  Write-Host "Scheduled task denied, using Startup folder."
  Install-StartupVbs
}

if (-not $taskOk) {
  Start-Process -FilePath "wscript.exe" -ArgumentList @("//B", $StartupScript) -WindowStyle Hidden
  Write-Host "Started watcher supervisor for this session."
}

Write-Host "Command: $Python $Runner watch --quiet"
Write-Host "Workdir: $Root"
