param(
    [string]$Version = '0.3.6',
    [string]$Python = 'python',
    [string]$MoverPackage,
    [string]$AnalysisToc,
    [string]$NsisDirectory,
    [string]$WebViewBootstrapper,
    [string]$CargoMetadata,
    [switch]$SkipPublish
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$artifacts = Join-Path $root 'artifacts'
$package = Join-Path $artifacts 'package\AI-First-Tools'
$project = [xml](Get-Content -LiteralPath (Join-Path $root 'workspace\AIFirst.Workspace.csproj') -Raw)
if ($project.Project.PropertyGroup.Version -ne $Version) { throw 'Package version must match the workspace project version.' }
if (!$MoverPackage -or !$AnalysisToc -or !$NsisDirectory -or !$WebViewBootstrapper) {
    throw 'Provide the frozen mover package, its Analysis TOC, the portable NSIS directory and Microsoft WebView2 bootstrapper.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $WebViewBootstrapper
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'WebView2 bootstrapper signature must be valid and issued to Microsoft Corporation.'
}
if (!$SkipPublish) {
    & dotnet publish (Join-Path $root 'workspace\AIFirst.Workspace.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -o $package
    if ($LASTEXITCODE) { throw 'Workspace publishing failed.' }
}
if (!(Test-Path -LiteralPath (Join-Path $package 'AI一手工具工作台.exe'))) { throw 'Workspace package is missing.' }
$targetMover = Join-Path $package 'tools\dialog-mover-v0.3'
New-Item -ItemType Directory -Force -Path $targetMover | Out-Null
Copy-Item -LiteralPath (Join-Path $MoverPackage '对话搬家.exe') -Destination $targetMover -Force
Copy-Item -LiteralPath (Join-Path $MoverPackage '_internal') -Destination $targetMover -Recurse -Force
$runtime = Join-Path $targetMover '_internal'
$engineDirectory = Join-Path $runtime 'bin'
foreach ($filename in @('MSVCP140.dll', 'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll')) {
    Copy-Item -LiteralPath (Join-Path $runtime $filename) -Destination $engineDirectory -Force
}
foreach ($filename in @('LICENSE', 'NOTICE', 'README.md')) { Copy-Item -LiteralPath (Join-Path $root $filename) -Destination $package -Force }
Copy-Item -LiteralPath (Join-Path $root 'docs') -Destination $package -Recurse -Force
& $Python (Join-Path $PSScriptRoot 'collect_licenses.py') --toc $AnalysisToc --package $package --nsis $NsisDirectory
if ($LASTEXITCODE) { throw 'License collection failed.' }
if (!$CargoMetadata) {
    $CargoMetadata = Join-Path $artifacts 'cargo-metadata.json'
    & cargo metadata --manifest-path (Join-Path $root 'txcript\Cargo.toml') --locked --format-version 1 --filter-platform x86_64-pc-windows-msvc | Set-Content -LiteralPath $CargoMetadata -Encoding utf8
    if ($LASTEXITCODE) { throw 'Rust dependency metadata failed.' }
}
& $Python (Join-Path $PSScriptRoot 'collect_rust_licenses.py') --metadata $CargoMetadata --package $package
if ($LASTEXITCODE) { throw 'Rust license collection failed.' }
Copy-Item -LiteralPath (Join-Path $root 'licenses\Microsoft-WebView2-SDK-LICENSE.txt') -Destination (Join-Path $package 'THIRD-PARTY-LICENSES') -Force
Copy-Item -LiteralPath (Join-Path $root 'licenses\Microsoft-WebView2-SDK-NOTICE.txt') -Destination (Join-Path $package 'THIRD-PARTY-LICENSES') -Force
Copy-Item -LiteralPath (Join-Path $root 'licenses\Microsoft-VC-Redist.txt') -Destination (Join-Path $package 'THIRD-PARTY-LICENSES') -Force
& $Python (Join-Path $PSScriptRoot 'check_release.py') --package $package
if ($LASTEXITCODE) { throw 'Release package checks failed.' }
$manifest = Join-Path $artifacts 'uninstall-files.nsh'
$commands = [System.Collections.Generic.List[string]]::new()
foreach ($file in Get-ChildItem -LiteralPath $package -Recurse -File) {
    $relative = [IO.Path]::GetRelativePath($package, $file.FullName)
    if ($relative.Contains('..') -or $relative.Contains('"') -or $relative.Contains('$')) { throw 'Unsafe package filename.' }
    $commands.Add('Delete "$INSTDIR\' + $relative + '"')
}
foreach ($directory in Get-ChildItem -LiteralPath $package -Recurse -Directory | Sort-Object { $_.FullName.Length } -Descending) {
    $relative = [IO.Path]::GetRelativePath($package, $directory.FullName)
    if ($relative.Contains('..') -or $relative.Contains('"') -or $relative.Contains('$')) { throw 'Unsafe package directory.' }
    $commands.Add('RMDir "$INSTDIR\' + $relative + '"')
}
[IO.File]::WriteAllLines($manifest, $commands, [Text.UTF8Encoding]::new($true))
$output = Join-Path $artifacts 'release'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$setup = Join-Path $output "AI-First-Tools-Setup-$Version.exe"
& (Join-Path $NsisDirectory 'makensis.exe') /INPUTCHARSET UTF8 "/DVERSION=$Version" "/DPACKAGE=$package" "/DOUTPUT=$setup" "/DICON=$(Join-Path $root 'workspace\assets\ai-first-logo.ico')" "/DWEBVIEW_BOOTSTRAPPER=$WebViewBootstrapper" "/DUNINSTALL_MANIFEST=$manifest" (Join-Path $root 'installer\setup.nsi')
if ($LASTEXITCODE) { throw 'Installer compilation failed.' }
$zip = Join-Path $output "AI-First-Tools-Portable-$Version-win-x64.zip"
Compress-Archive -LiteralPath $package -DestinationPath $zip -CompressionLevel Optimal -Force
$hashes = foreach ($file in @($setup, $zip)) { (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + [IO.Path]::GetFileName($file) }
[IO.File]::WriteAllLines((Join-Path $output 'SHA256SUMS.txt'), $hashes, [Text.UTF8Encoding]::new($false))
Write-Output "Release artifacts: $output"
