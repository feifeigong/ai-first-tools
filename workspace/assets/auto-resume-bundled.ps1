param([ValidateSet('status','start','stop','autostart-on','autostart-off','prepare-update','finish-update','uninstall')][string]$Action='status', [switch]$FunctionsOnly)
$requested = $Action
$bundleFunctionsOnly = $FunctionsOnly
. (Join-Path $PSScriptRoot 'auto-resume-control.ps1') -FunctionsOnly
$bundleRoot = Split-Path -Parent $PSScriptRoot
$bundledExecutable = Join-Path $bundleRoot 'tools\auto-resume\AI一手续跑后台.exe'
$bundledPreference = Join-Path $settingsDirectory 'bundled-auto-resume-startup.json'
$updateReceipt = Join-Path $settingsDirectory 'auto-resume-update.json'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runName = 'AI First Auto Resume'

function Get-ResetMonitorDirectory {
    $directory = $settingsDirectory
    if (Test-Path -LiteralPath (Join-Path $bundleRoot 'development-preview.json') -PathType Leaf) {
        $directory = Join-Path $directory 'memory-preview'
    } else {
        $binding = Join-Path $directory 'active-data-profile.json'
        if (Test-Path -LiteralPath $binding) {
            $file = Get-Item -LiteralPath $binding -Force
            if ($file.PSIsContainer -or $file.Length -gt 1024 -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '工具箱资料设置暂时无法读取，原资料已保留。' }
            $value = [IO.File]::ReadAllText($binding) | ConvertFrom-Json
            if ($null -eq $value -or @($value.PSObject.Properties).Count -ne 2 -or $value.format -cne 'ai-first-data-profile-v1' -or $value.profile -cnotin @('default','memory-preview')) { throw '工具箱资料设置暂时无法读取，原资料已保留。' }
            if ($value.profile -ceq 'memory-preview') { $directory = Join-Path $directory 'memory-preview' }
        }
    }
    foreach ($path in @($settingsDirectory,$directory)) {
        if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '工具箱资料位置暂时无法核对，原资料已保留。' }
    }
    Join-Path $directory 'reset-notices'
}
function Write-ResetMonitorJson([string]$Path, $Value) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    $temporary = $Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}
function Get-ResetMonitorMutexName([string]$Directory) {
    $value = [IO.Path]::GetFullPath((Join-Path $Directory 'monitor')).ToUpperInvariant()
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($value))).Replace('-','').Substring(0,16) }
    finally { $hash.Dispose() }
    'Local\AI_FIRST_RESET_' + $key
}
function Remove-StaleOwnedResetMonitor([string]$Directory, [string]$Program, [string]$Token) {
    # Creating the missing mutex atomically keeps a new host from replacing the
    # owner between the token check and deletion. An existing mutex is left alone.
    $created = $false
    $guard = [Threading.Mutex]::new($true, (Get-ResetMonitorMutexName $Directory), [ref]$created)
    try {
        if (!$created) { return $false }
        $ownerPath = Join-Path $Directory 'monitor-owner.json'
        if (!(Test-Path -LiteralPath $ownerPath)) { return $true }
        try { $current = Get-Content -LiteralPath $ownerPath -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw '重置消息提醒状态暂时无法确认，请稍后重试。' }
        if ($current.token -cne $Token -or ![string]::Equals([string]$current.executable, $Program, [StringComparison]::OrdinalIgnoreCase)) { return $false }
        Remove-Item -LiteralPath $ownerPath -Force
        return $true
    } finally {
        if ($created) { $guard.ReleaseMutex() }
        $guard.Dispose()
    }
}
function Stop-OwnedResetMonitor([ValidateSet('update','uninstall')][string]$Reason) {
    $directory = Get-ResetMonitorDirectory
    $ownerPath = Join-Path $directory 'monitor-owner.json'
    $receiptPath = Join-Path $directory 'reset-monitor-update.json'
    $program = Join-Path $bundleRoot 'AI一手工具工作台.exe'
    if (Test-Path -LiteralPath $ownerPath) {
        try { $owner = Get-Content -LiteralPath $ownerPath -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw '重置消息提醒状态暂时无法确认，请稍后重试。' }
        # Another installed copy may own the same user-level notification service.
        # Its files and process must survive this package's update or uninstall.
        if (![string]::Equals([string]$owner.executable, $program, [StringComparison]::OrdinalIgnoreCase)) { return }
        $ownerPid = 0L
        if ($owner.token -isnot [string] -or [string]::IsNullOrWhiteSpace($owner.token) -or
            ![long]::TryParse([string]$owner.pid, [ref]$ownerPid) -or $ownerPid -le 0) {
            throw '重置消息提醒状态暂时无法确认，请稍后重试。'
        }
        if ($Reason -eq 'update') {
            Write-ResetMonitorJson $receiptPath @{executable=$program; token=$owner.token; restart=$true; reason='update'}
        }
        if (!(Remove-StaleOwnedResetMonitor $directory $program $owner.token)) {
            Write-ResetMonitorJson (Join-Path $directory 'monitor-stop.json') @{token=$owner.token; executable=$program; reason=$Reason}
            for ($attempt=0; $attempt -le 40; $attempt++) {
                if (!(Test-Path -LiteralPath $ownerPath) -or (Remove-StaleOwnedResetMonitor $directory $program $owner.token)) { break }
                if ($attempt -eq 40) { throw '重置消息提醒正在关闭，请稍后重试。' }
                Start-Sleep -Milliseconds 250
            }
        }
    }
    if ($Reason -eq 'uninstall' -and (Test-Path -LiteralPath $receiptPath)) {
        try { $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw '重置消息提醒状态暂时无法确认，请稍后重试。' }
        if ([string]::Equals([string]$receipt.executable, $program, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $receiptPath -Force
        }
    }
}
function Restore-OwnedResetMonitor {
    $receiptPath = Join-Path (Get-ResetMonitorDirectory) 'reset-monitor-update.json'
    if (!(Test-Path -LiteralPath $receiptPath)) { return }
    try { $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw '重置消息提醒暂时未恢复，请稍后重试。' }
    $program = Join-Path $bundleRoot 'AI一手工具工作台.exe'
    if (![string]::Equals([string]$receipt.executable, $program, [StringComparison]::OrdinalIgnoreCase)) { return }
    if ($receipt.restart -ne $true -or $receipt.reason -ne 'update' -or !(Test-Path -LiteralPath $program -PathType Leaf)) {
        throw '重置消息提醒暂时未恢复，请稍后重试。'
    }
    # The host checks the saved reminder choice itself; a disabled reminder exits.
    Start-Process -FilePath $program -ArgumentList '--reset-monitor' -WorkingDirectory $bundleRoot -WindowStyle Hidden | Out-Null
    Remove-Item -LiteralPath $receiptPath -Force
}
function Get-BundledWatchers {
    # Query the shared state owner, not just processes launched from this package.
    # The probe checks process identity and does not start work or read chats/accounts.
    $report = Join-Path ([IO.Path]::GetTempPath()) ('ai-first-resume-status-' + [guid]::NewGuid().ToString('N') + '.json')
    try {
        $probe = Start-Process -FilePath $script:bundledExecutable -ArgumentList @('--watch-status', ('"' + $report + '"')) -WorkingDirectory (Split-Path $script:bundledExecutable -Parent) -WindowStyle Hidden -PassThru
        if (!$probe.WaitForExit(8000)) {
            # This is only our read-only query child, never a watcher or Codex task.
            try { if (!$probe.HasExited) { $probe.Kill() } } catch { }
            throw '暂时无法确认自动续跑状态，请稍后重试。'
        }
        if (!(Test-Path -LiteralPath $report)) { throw '暂时无法确认自动续跑状态，请稍后重试。' }
        $value = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($value.ok -eq $false -and $value.errorCode -eq 'starting') {
            [pscustomobject]@{ProcessId=0; ExecutablePath=''; Ready=$false}
            return
        }
        if ($probe.ExitCode -ne 0 -or $value.ok -ne $true -or $value.running -isnot [bool]) { throw '暂时无法确认自动续跑状态，请稍后重试。' }
        if ($value.running) {
            if (!$value.pid -or !$value.executable -or $value.ready -isnot [bool]) { throw '暂时无法确认自动续跑状态，请稍后重试。' }
            # The legacy adapter already owns Python runners and their startup syntax.
            if ((Split-Path -Leaf $value.executable) -ne 'AI一手续跑后台.exe') {
                if ($script:hasLegacy) { return }
                throw '暂时无法确认自动续跑状态，请稍后重试。'
            }
            [pscustomobject]@{ProcessId=[int]$value.pid; ExecutablePath=[string]$value.executable; Ready=$value.ready}
        }
    } finally { if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report -Force } }
}
function Get-BundledRunValue {
    $key=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Run',$false)
    if ($null -eq $key) { return $null }
    try { return $key.GetValue($runName,$null) } finally { $key.Dispose() }
}
function Test-BundledRunValue([string]$Value) {
    if ($Value -notmatch '^"(.+)" watch --quiet$') { return $false }
    $program = $Matches[1]
    if ([string]::Equals($program, $script:bundledExecutable, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    $directory = Split-Path -Parent $program
    $tools = Split-Path -Parent $directory
    $root = Split-Path -Parent $tools
    if ((Split-Path -Leaf $program) -ne 'AI一手续跑后台.exe' -or (Split-Path -Leaf $directory) -ne 'auto-resume' -or (Split-Path -Leaf $tools) -ne 'tools') { return $false }
    foreach ($file in @($program, (Join-Path $root 'AI一手工具工作台.exe'), (Join-Path $root 'assets\auto-resume-bundled.ps1'), (Join-Path $root 'assets\auto-resume-control.ps1'), (Join-Path $root 'assets\tool-catalog.json'))) {
        if (!(Test-Path -LiteralPath $file -PathType Leaf)) { return $false }
    }
    try {
        $catalog = Get-Content -LiteralPath (Join-Path $root 'assets\tool-catalog.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        return @($catalog | Where-Object { $_.id -eq 'auto-resume' -and $_.nativePage -eq 'auto-resume' }).Count -eq 1
    } catch { return $false }
}
function Get-BundledRunCommand { '"' + $script:bundledExecutable + '" watch --quiet' }
function Set-BundledRunValue([bool]$Enabled) {
    $value = Get-BundledRunValue
    if ($value -and !(Test-BundledRunValue $value)) { throw '开机设置暂时无法确认，原设置已保留，请稍后重试。' }
    if ($Enabled) {
        $watchers = @(Get-BundledWatchers)
        $command = if ($watchers.Count -eq 1) { '"' + $watchers[0].ExecutablePath + '" watch --quiet' } else { Get-BundledRunCommand }
        if ($watchers.Count -eq 1 -and !$watchers[0].ExecutablePath) { $command = Get-BundledRunCommand }
        if (!(Test-Path -LiteralPath $runKey)) { New-Item -Path $runKey -Force | Out-Null }
        New-ItemProperty -LiteralPath $runKey -Name $runName -Value $command -PropertyType String -Force | Out-Null
    } elseif ($value) { Remove-ItemProperty -LiteralPath $runKey -Name $runName }
}
function Save-BundledPreference([bool]$Enabled) {
    New-Item -ItemType Directory -Path $settingsDirectory -Force | Out-Null
    $temporary = $bundledPreference + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        @{autostart=$Enabled} | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $bundledPreference -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}
function Get-BundledPreference {
    if (!(Test-Path -LiteralPath $bundledPreference)) { return $null }
    $value = Get-Content -LiteralPath $bundledPreference -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $value -or $value.autostart -isnot [bool]) { throw '开机设置暂时无法读取，请修复工具箱设置后重试。' }
    return $value.autostart
}
function Get-BundleStatus {
    $watchers = @(Get-BundledWatchers)
    if (@($watchers | Where-Object { $_.Ready -eq $false }).Count -gt 0) { throw '自动续跑仍在准备，请稍后刷新确认。' }
    $legacyWatchers = @()
    $legacyStartup = $false
    if ($script:hasLegacy) {
        $legacyWatchers = @(Get-Watchers)
        $legacyState = Get-ResumeStatus $true
        $legacyStartup = $legacyState.autostart
    }
    $startup = (Test-BundledRunValue ([string](Get-BundledRunValue))) -and ((Get-BundledPreference) -ne $false)
    $count = $watchers.Count + $legacyWatchers.Count
    @{installed=(Test-Path -LiteralPath $script:bundledExecutable -PathType Leaf); running=$count -gt 0; autostart=($startup -or $legacyStartup); watcherCount=$count; error=''}
}
function Disable-LegacyStartup {
    if ($script:hasLegacy) { Set-ResumeAutostart $false }
}
function Start-BundledWatcher {
    $existing = @(Get-BundledWatchers)
    if (($existing.Count -eq 1 -and $existing[0].Ready -ne $false) -or ($script:hasLegacy -and @(Get-Watchers).Count -gt 0)) { return }
    $process = $null
    if ($existing.Count -eq 0) {
        $previous = [Environment]::GetEnvironmentVariable('AI_FIRST_MANUAL_WATCH','Process')
        try {
            [Environment]::SetEnvironmentVariable('AI_FIRST_MANUAL_WATCH','1','Process')
            $process = Start-Process -FilePath $script:bundledExecutable -ArgumentList @('watch','--quiet') -WorkingDirectory (Split-Path $script:bundledExecutable -Parent) -WindowStyle Hidden -PassThru
        } finally { [Environment]::SetEnvironmentVariable('AI_FIRST_MANUAL_WATCH',$previous,'Process') }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $watchers = @(Get-BundledWatchers)
        if ($watchers.Count -eq 1 -and $watchers[0].Ready -ne $false) { return }
        if ($process -and $process.HasExited -and $watchers.Count -eq 0) { throw '自动续跑暂时没有开启，请再试一次。' }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw '自动续跑仍在准备，请稍后刷新确认。'
}
function Stop-BundledWatcher {
    if (@(Get-BundledWatchers).Count -eq 0) { return }
    $request = Start-Process -FilePath $script:bundledExecutable -ArgumentList '--request-stop' -WorkingDirectory (Split-Path $script:bundledExecutable -Parent) -WindowStyle Hidden -PassThru -Wait
    if ($request.ExitCode -ne 0) { throw '自动续跑暂时没有关闭，请再试一次。' }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $watchers = @(Get-BundledWatchers)
        if ($watchers.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    # Never force-stop a watcher or its in-flight Codex work to make the switch look off.
    if (@(Get-BundledWatchers).Count -gt 0) { throw '自动续跑正在结束当前检查，请稍后刷新确认。' }
}
function Invoke-BundledAction([string]$Operation) {
    if (!(Test-Path -LiteralPath $script:bundledExecutable -PathType Leaf)) { throw '内置续跑组件缺失，请重新安装完整工具箱。' }
    $script:hasLegacy = Connect-Resume
    if ($Operation -eq 'status') { return Get-BundleStatus }
    New-Item -ItemType Directory -Path $settingsDirectory -Force | Out-Null
    switch ($Operation) {
        'start' { Start-BundledWatcher }
        'stop' {
            Disable-LegacyStartup
            Save-BundledPreference $false
            Set-BundledRunValue $false
            if ($script:hasLegacy) { $null = Invoke-ResumeAction 'stop' }
            Stop-BundledWatcher
        }
        'autostart-on' { Disable-LegacyStartup; Save-BundledPreference $true; Set-BundledRunValue $true }
        'autostart-off' { Disable-LegacyStartup; Save-BundledPreference $false; Set-BundledRunValue $false }
        'prepare-update' {
            Stop-OwnedResetMonitor 'update'
            if (@(Get-BundledWatchers | Where-Object { !$_.ExecutablePath -or $_.ExecutablePath -eq $script:bundledExecutable }).Count -gt 0) {
                @{program=$script:bundledExecutable; restart=$true} | ConvertTo-Json | Set-Content -LiteralPath $updateReceipt -Encoding UTF8
                Stop-BundledWatcher
            }
        }
        'finish-update' {
            Restore-OwnedResetMonitor
            if (Test-Path -LiteralPath $updateReceipt) {
                $receipt = Get-Content -LiteralPath $updateReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($receipt.restart -eq $true -and $receipt.program -eq $script:bundledExecutable) { Start-BundledWatcher }
                Remove-Item -LiteralPath $updateReceipt -Force
            } elseif ($script:hasLegacy) {
                $legacyState=Get-ResumeStatus $true
                $wasRunning=@(Get-Watchers).Count -gt 0
                if ($wasRunning -or $legacyState.autostart) {
                    $wasAutomatic=[bool]$legacyState.autostart
                    Disable-LegacyStartup
                    if ($wasRunning) { $null=Invoke-ResumeAction 'stop' }
                    Save-BundledPreference $wasAutomatic
                    Set-BundledRunValue $wasAutomatic
                    if ($wasRunning) { Start-BundledWatcher }
                }
            }
        }
        'uninstall' {
            Stop-OwnedResetMonitor 'uninstall'
            # Removing an unused preview must not stop another installed copy.
            if (@(Get-BundledWatchers | Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ne $script:bundledExecutable }).Count -gt 0) { break }
            $registered = Get-BundledRunValue
            if ($registered -and $registered -ne (Get-BundledRunCommand)) { break }
            Disable-LegacyStartup
            Save-BundledPreference $false
            Set-BundledRunValue $false
            if ($script:hasLegacy) { $null = Invoke-ResumeAction 'stop' }
            Stop-BundledWatcher
            if (Test-Path -LiteralPath $updateReceipt) { Remove-Item -LiteralPath $updateReceipt -Force }
        }
    }
    Get-BundleStatus
}
if (!$bundleFunctionsOnly) {
    $mutex = [Threading.Mutex]::new($false,('Local\AI_FIRST_AUTO_RESUME_' + [Security.Principal.WindowsIdentity]::GetCurrent().User.Value))
    $locked = $false
    try {
        try { $locked = $mutex.WaitOne(10000) } catch [Threading.AbandonedMutexException] { $locked=$true }
        if (!$locked) { throw '另一个开关操作正在进行，请稍后刷新。' }
        Invoke-BundledAction $requested | ConvertTo-Json -Compress
    } catch {
        $message = $_.Exception.Message
        if ($message -notmatch '^(内置|开机|另一个|已有同名|检测到不同|没有找到|后台程序|自动续跑|暂时无法确认|重置消息提醒)') { $message='操作没有完成，请稍后重试。' }
        @{installed=$true; running=$false; autostart=$false; watcherCount=0; error=$message} | ConvertTo-Json -Compress
        exit 1
    } finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
}
