$ErrorActionPreference = "Stop"
$TaskName = "VibcodingCodexAutoResume"
$StartupScript = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\codex-auto-resume.vbs"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  Write-Host "Removed scheduled task: $TaskName"
}

if (Test-Path $StartupScript) {
  Remove-Item $StartupScript -Force
  Write-Host "Removed startup script: $StartupScript"
}

Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'wscript.exe'" |
  Where-Object { $_.CommandLine -and ($_.CommandLine -like "*codex-auto-resume*run.py*watch*" -or $_.CommandLine -like "*codex-auto-resume.vbs*") } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped process: $($_.ProcessId)"
  }

Write-Host "Uninstall finished"
