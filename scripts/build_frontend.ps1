$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\frontend')
npm ci
npm run build
