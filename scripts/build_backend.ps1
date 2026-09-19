$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
pyinstaller --noconfirm --clean CodexAccountManager.spec
