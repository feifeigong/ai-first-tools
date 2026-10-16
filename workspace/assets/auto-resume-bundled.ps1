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

function Get-BundledWatchers {
    $expected = '^\s*"?' + [regex]::Escape($script:bundledExecutable) + '"?\s+watch\s+--quiet\s*$'
    @(Get-CimInstance Win32_Process -Filter "Name='AI一手续跑后台.exe'" | Where-Object { $_.CommandLine -match $expected })
}
function Get-BundledRunValue {
    $key=[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Run',$false)
    if ($null -eq $key) { return $null }
    try { return $key.GetValue($runName,$null) } finally { $key.Dispose() }
}
function Get-BundledRunCommand { '"' + $script:bundledExecutable + '" watch --quiet' }
function Set-BundledRunValue([bool]$Enabled) {
    $value = Get-BundledRunValue
    if ($value -and $value -ne (Get-BundledRunCommand)) { throw '开机设置属于另一处工作台，请先使用原工作台关闭开机自启。' }
    if ($Enabled) {
        if (!(Test-Path -LiteralPath $runKey)) { New-Item -Path $runKey -Force | Out-Null }
        New-ItemProperty -LiteralPath $runKey -Name $runName -Value (Get-BundledRunCommand) -PropertyType String -Force | Out-Null
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
    if ($null -eq $value -or $value.autostart -isnot [bool]) { throw '开机设置暂时无法读取，请修复工作台设置后重试。' }
    return $value.autostart
}
function Get-BundleStatus {
    $watchers = @(Get-BundledWatchers)
    $legacyWatchers = @()
    $legacyStartup = $false
    if ($script:hasLegacy) {
        $legacyWatchers = @(Get-Watchers)
        $legacyState = Get-ResumeStatus $true
        $legacyStartup = $legacyState.autostart
    }
    $startup = ((Get-BundledRunValue) -eq (Get-BundledRunCommand)) -and ((Get-BundledPreference) -ne $false)
    $count = $watchers.Count + $legacyWatchers.Count
    @{installed=(Test-Path -LiteralPath $script:bundledExecutable -PathType Leaf); running=$count -gt 0; autostart=($startup -or $legacyStartup); watcherCount=$count; error=''}
}
function Disable-LegacyStartup {
    if ($script:hasLegacy) { Set-ResumeAutostart $false }
}
function Start-BundledWatcher {
    if (@(Get-BundledWatchers).Count -gt 0 -or ($script:hasLegacy -and @(Get-Watchers).Count -gt 0)) { return }
    $previous = [Environment]::GetEnvironmentVariable('AI_FIRST_MANUAL_WATCH','Process')
    try {
        [Environment]::SetEnvironmentVariable('AI_FIRST_MANUAL_WATCH','1','Process')
        $process = Start-Process -FilePath $script:bundledExecutable -ArgumentList @('watch','--quiet') -WorkingDirectory (Split-Path $script:bundledExecutable -Parent) -WindowStyle Hidden -PassThru
    } finally { [Environment]::SetEnvironmentVariable('AI_FIRST_MANUAL_WATCH',$previous,'Process') }
    Start-Sleep -Milliseconds 900
    if ($process.HasExited -or @(Get-BundledWatchers).Count -ne 1) { throw '内置续跑后台没有保持运行，请修复或重新安装工作台。' }
}
function Stop-BundledWatcher {
    if (@(Get-BundledWatchers).Count -eq 0) { return }
    $request = Start-Process -FilePath $script:bundledExecutable -ArgumentList '--request-stop' -WorkingDirectory (Split-Path $script:bundledExecutable -Parent) -WindowStyle Hidden -PassThru -Wait
    if ($request.ExitCode -ne 0) { throw '内置后台暂时无法保存停止请求，请稍后重试。' }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $watchers = @(Get-BundledWatchers)
        if ($watchers.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    # Stop only this exact watcher; existing Codex turns and child processes are not targeted.
    foreach ($watcher in @(Get-BundledWatchers)) {
        $current = @(Get-BundledWatchers | Where-Object ProcessId -eq $watcher.ProcessId)
        if ($current.Count -eq 1) { Stop-Process -Id $watcher.ProcessId -Force }
    }
    if (@(Get-BundledWatchers).Count -gt 0) { throw '内置后台尚未停止，请刷新后重试。' }
}
function Invoke-BundledAction([string]$Operation) {
    if (!(Test-Path -LiteralPath $script:bundledExecutable -PathType Leaf)) { throw '内置续跑组件缺失，请重新安装完整工作台。' }
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
            if (@(Get-BundledWatchers).Count -gt 0) {
                @{program=$script:bundledExecutable; restart=$true} | ConvertTo-Json | Set-Content -LiteralPath $updateReceipt -Encoding UTF8
                Stop-BundledWatcher
            }
        }
        'finish-update' {
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
        if ($message -notmatch '^(内置|开机|另一个|已有同名|检测到不同|没有找到|后台程序)') { $message='操作没有完成，请刷新确认或修复工作台后重试。' }
        @{installed=$true; running=$false; autostart=$false; watcherCount=0; error=$message} | ConvertTo-Json -Compress
        exit 1
    } finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
}
