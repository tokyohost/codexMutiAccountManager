$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '..'
& (Join-Path $PSScriptRoot 'build_frontend.ps1')
& (Join-Path $PSScriptRoot 'build_backend.ps1')
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $localIscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
    if (Test-Path $localIscc) { $iscc = Get-Command $localIscc }
}
if (-not $iscc) { throw '未找到 Inno Setup 编译器 iscc，请安装 Inno Setup 6 并加入 PATH。' }
New-Item -ItemType Directory -Force (Join-Path $root 'release') | Out-Null
$version = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim()
& $iscc.Source "/DAppVersion=$version" (Join-Path $root 'installer\installer.iss')
$installer = Get-ChildItem (Join-Path $root 'release\CodexAccountManager-*-Setup-x64.exe') | Select-Object -First 1
$hash = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash.ToLower()
"$hash  $($installer.Name)" | Set-Content (Join-Path $root 'release\SHA256SUMS.txt') -Encoding ascii
