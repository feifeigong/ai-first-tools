param(
    [ValidateSet('status', 'start', 'stop', 'resume-on', 'resume-off', 'credit-on', 'credit-off', 'timer-on', 'timer-off', 'autostart-on', 'autostart-off')][string]$Action = 'status',
    [switch]$FunctionsOnly
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$taskName = 'VibcodingCodexAutoResume'
$startupFile = Join-Path ([Environment]::GetFolderPath('Startup')) 'codex-auto-resume.vbs'
$settingsDirectory = Join-Path $env:LOCALAPPDATA 'AI一手工具工作台'
$connectionFile = Join-Path $settingsDirectory 'auto-resume-connection.json'
$disabledStartup = Join-Path $settingsDirectory 'codex-auto-resume.vbs.disabled'
$startupPreference = Join-Path $settingsDirectory 'auto-resume-startup.json'

function Get-StartupPreference {
    if (!(Test-Path -LiteralPath $startupPreference)) { return $null }
    $value = Get-Content -LiteralPath $startupPreference -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $value -or $value.autostart -isnot [bool]) { throw '自动续跑开机设置无法读取，请修复设置后刷新。' }
    return $value.autostart
}

function Save-StartupPreference([bool]$Enabled) {
    $temporary = $startupPreference + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        @{ autostart = $Enabled } | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $startupPreference -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}

function Test-StartupGate {
    (Test-Path -LiteralPath (Join-Path $script:root 'src\codex_auto_resume\workspace_control.py')) -and ([IO.File]::ReadAllText($script:runner).Contains('allow_background_watch'))
}

function Convert-WatcherCommand([string]$Command) {
    if ($Command -match '^\s*(?:"(?<python>[^"]+)"|(?<python>\S+))\s+"(?<runner>[^"]+\\run\.py)"\s+watch(?:\s+--quiet)?\s*$') {
        $runner = $Matches.runner
        if ([IO.Path]::GetFileName([IO.Path]::GetDirectoryName($runner)) -eq 'codex-auto-resume') {
            return @{ Runner = $runner; Python = $Matches.python }
        }
    }
    return $null
}

function Get-Watchers {
    @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object {
        $parsed = Convert-WatcherCommand $_.CommandLine
        $parsed -and [string]::Equals($parsed.Runner, $script:runner, [StringComparison]::OrdinalIgnoreCase)
    })
}

function Get-ResumeTask {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        if (@($task.Actions).Count -ne 1 -or $task.Actions[0].Arguments -notmatch '^"([^"]+\\run\.py)"\s+watch(?:\s+--quiet)?\s*$') {
            throw '已有同名开机任务无法识别，未做修改。'
        }
        $candidate = $Matches[1]
        if ([IO.Path]::GetFileName([IO.Path]::GetDirectoryName($candidate)) -ne 'codex-auto-resume') { throw '已有同名开机任务不属于续跑工具，未做修改。' }
        if ($script:runner -and ![string]::Equals($script:runner, $candidate, [StringComparison]::OrdinalIgnoreCase)) { throw '检测到不同位置的续跑程序，请先统一安装位置。' }
    }
    return $task
}

function Connect-Resume {
    $script:runner = $null
    $script:python = $null
    $task = Get-ResumeTask
    if ($task) {
        $null = $task.Actions[0].Arguments -match '^"([^"]+\\run\.py)"'
        $script:runner = $Matches[1]
        $script:python = $task.Actions[0].Execute
    }
    $processes = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'")
    foreach ($process in $processes) {
        $parsed = Convert-WatcherCommand $process.CommandLine
        if (!$parsed) { continue }
        if ($script:runner -and ![string]::Equals($script:runner, $parsed.Runner, [StringComparison]::OrdinalIgnoreCase)) { throw '检测到不同位置的续跑程序，请先统一安装位置。' }
        $script:runner = $parsed.Runner
        $script:python = $parsed.Python
    }
    if (!$script:runner -and (Test-Path -LiteralPath $connectionFile)) {
        $saved = Get-Content -LiteralPath $connectionFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:runner = $saved.Runner
        $script:python = $saved.Python
    }
    if (!$script:runner) {
        foreach ($file in @($startupFile, $disabledStartup)) {
            if (!(Test-Path -LiteralPath $file)) { continue }
            $vbs = Get-Content -LiteralPath $file -Raw
            if ($vbs -match 'sh\.Run\s+"""([^"\r\n]+)""\s+""([^"\r\n]+\\run\.py)""\s+watch') {
                $script:python = $Matches[1].Replace('\\', '\')
                $script:runner = $Matches[2].Replace('\\', '\')
            }
        }
    }
    if (!$script:runner) { return $false }
    if (![IO.Path]::IsPathRooted($script:runner) -or [IO.Path]::GetFileName($script:runner) -ne 'run.py' -or [IO.Path]::GetFileName([IO.Path]::GetDirectoryName($script:runner)) -ne 'codex-auto-resume') { throw '续跑程序的位置无效，未执行操作。' }
    $script:root = [IO.Path]::GetDirectoryName($script:runner)
    if (!(Test-Path -LiteralPath $script:runner -PathType Leaf) -or !(Test-Path -LiteralPath (Join-Path $script:root 'src\codex_auto_resume\daemon.py') -PathType Leaf)) { return $false }
    if (![IO.Path]::IsPathRooted($script:python) -or !(Test-Path -LiteralPath $script:python -PathType Leaf) -or [IO.Path]::GetFileName($script:python) -notin @('python.exe', 'pythonw.exe')) { throw '没有找到原续跑程序使用的 Python，请修复原安装后刷新。' }
    $pythonw = Join-Path ([IO.Path]::GetDirectoryName($script:python)) 'pythonw.exe'
    if (Test-Path -LiteralPath $pythonw -PathType Leaf) { $script:python = $pythonw }
    return $true
}

function Stop-Supervisor {
    $pattern = '(?:^|[\s"])' + [regex]::Escape($startupFile) + '(?:"|\s|$)'
    Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" | Where-Object { $_.CommandLine -match $pattern } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
    }
}

function Set-ResumeAutostart([bool]$Enabled) {
    $task = Get-ResumeTask
    if (!$Enabled) {
        # Disable future launches first. Stopping only Python lets the supervisor restart it.
        if ($task -and $task.Settings.Enabled) {
            try { Disable-ScheduledTask -InputObject $task | Out-Null }
            catch { if (!(Test-StartupGate)) { throw '没有找到支持开机开关的续跑入口，请更新原工具后重试。' } }
        }
        Save-StartupPreference $false
        if (Test-Path -LiteralPath $startupFile) { Move-Item -LiteralPath $startupFile -Destination $disabledStartup -Force }
        Stop-Supervisor
        return
    }
    Save-StartupPreference $true
    if ($task -and $task.Settings.Enabled) { return }
    if ($task) {
        try { Enable-ScheduledTask -InputObject $task | Out-Null; return }
        catch { }
    }
    try {
        $taskAction = New-ScheduledTaskAction -Execute $script:python -Argument ('"' + $script:runner + '" watch --quiet') -WorkingDirectory $script:root
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
        $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    } catch {
        # Same fallback as the original tool; no admin access is required.
        $pythonVbs = $script:python.Replace('"', '""')
        $runnerVbs = $script:runner.Replace('"', '""')
        $rootVbs = $script:root.Replace('"', '""')
        $vbs = "Set sh = CreateObject(""WScript.Shell"")`r`nsh.CurrentDirectory = ""$rootVbs""`r`nDo`r`n  sh.Run """"""$pythonVbs"""" """"$runnerVbs"""" watch --quiet"", 0, True`r`n  WScript.Sleep 5000`r`nLoop`r`n"
        [IO.File]::WriteAllText($startupFile, $vbs, [Text.Encoding]::Unicode)
    }
}

function Get-ResumeStatus([bool]$Installed) {
    $watchers = @()
    if ($Installed) { $watchers = @(Get-Watchers) }
    $task = Get-ResumeTask
    $autostart = ($null -ne $task -and $task.Settings.Enabled) -or (Test-Path -LiteralPath $startupFile)
    if ((Get-StartupPreference) -eq $false) { $autostart = $false }
    return @{ installed = $Installed; running = $watchers.Count -gt 0; autostart = [bool]$autostart; watcherCount = $watchers.Count; error = '' }
}

function Invoke-ResumeAction([string]$RequestedAction) {
    $installed = Connect-Resume
    if ($RequestedAction -eq 'status') { return Get-ResumeStatus $installed }
    if (!$installed) { throw '没有找到已有的自动续跑安装，请先安装后刷新。' }
    New-Item -ItemType Directory -Path $settingsDirectory -Force | Out-Null
    # Save connection metadata only, never copy Codex credentials, configuration or conversations.
    $temporary = $connectionFile + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        @{ Runner = $script:runner; Python = $script:python } | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $connectionFile -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
    switch ($RequestedAction) {
        'start' {
            if (@(Get-Watchers).Count -eq 0) {
                $previousManual = [Environment]::GetEnvironmentVariable('AI_FIRST_MANUAL_WATCH', 'Process')
                try {
                    [Environment]::SetEnvironmentVariable('AI_FIRST_MANUAL_WATCH', '1', 'Process')
                    $process = Start-Process -FilePath $script:python -ArgumentList @(('"' + $script:runner + '"'), 'watch', '--quiet') -WorkingDirectory $script:root -WindowStyle Hidden -PassThru
                } finally { [Environment]::SetEnvironmentVariable('AI_FIRST_MANUAL_WATCH', $previousManual, 'Process') }
                Start-Sleep -Milliseconds 900
                if ($process.HasExited -or @(Get-Watchers).Count -eq 0) { throw '后台程序没有保持运行，请检查原自动续跑工具后重试。' }
            }
        }
        'stop' {
            Set-ResumeAutostart $false
            foreach ($watcher in @(Get-Watchers)) {
                # Re-read identity immediately before stopping. Never use the PID file or kill the process tree.
                $current = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $watcher.ProcessId)
                $parsed = if ($current) { Convert-WatcherCommand $current.CommandLine } else { $null }
                if ($parsed -and [string]::Equals($parsed.Runner, $script:runner, [StringComparison]::OrdinalIgnoreCase)) { Stop-Process -Id $watcher.ProcessId -Force }
            }
            if (@(Get-Watchers).Count -ne 0) { throw '后台程序尚未停止，请刷新后重试。' }
        }
        'autostart-on' { Set-ResumeAutostart $true }
        'autostart-off' { Set-ResumeAutostart $false }
    }
    return Get-ResumeStatus $true
}

if (!$FunctionsOnly) {
    $bundledExecutable = Join-Path (Split-Path -Parent $PSScriptRoot) 'tools\auto-resume\AI一手续跑后台.exe'
    if (Test-Path -LiteralPath $bundledExecutable -PathType Leaf) {
        & (Join-Path $PSScriptRoot 'auto-resume-bundled.ps1') -Action $Action
        exit $LASTEXITCODE
    }
    if ($Action -in @('resume-on','resume-off','credit-on','credit-off','timer-on','timer-off')) { throw '请更新完整工具箱后使用自动化设置。' }
    $mutex = [Threading.Mutex]::new($false, ('Local\AI_FIRST_AUTO_RESUME_' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value))
    $locked = $false
    try {
        try { $locked = $mutex.WaitOne(10000) } catch [Threading.AbandonedMutexException] { $locked = $true }
        if (!$locked) { throw '自动续跑正在处理另一个操作，请稍后刷新。' }
        Invoke-ResumeAction $Action | ConvertTo-Json -Compress
    } catch {
        # Return only curated messages; system exception details may contain personal paths.
        $message = $_.Exception.Message
        if ($message -notmatch '^(已有同名|检测到不同|续跑程序的位置|没有找到|自动续跑正在|后台程序)') { $message = '操作没有完成，请检查开机任务权限或原工具安装后重试。' }
        @{ installed = $false; running = $false; autostart = $false; watcherCount = 0; error = $message } | ConvertTo-Json -Compress
        exit 1
    } finally {
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
