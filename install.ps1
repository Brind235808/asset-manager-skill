param(
    [string]$LibraryRoot = "D:\ASSETS"
)

$ErrorActionPreference = "Stop"
$SkillRoot = $PSScriptRoot
$SystemDir = Join-Path $LibraryRoot "_SYSTEM"

Write-Host "Installing asset-manager into $LibraryRoot"
New-Item -ItemType Directory -Force -Path $SystemDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $SystemDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $SystemDir "thumbs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $SystemDir "backups") | Out-Null

Copy-Item (Join-Path $SkillRoot "scripts\*.py") $SystemDir -Force
Copy-Item (Join-Path $SkillRoot "scripts\requirements.txt") $SystemDir -Force

$ConfigPath = Join-Path $SystemDir "config.json"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item (Join-Path $SkillRoot "config\config.example.json") $ConfigPath
    Write-Host "Created config: $ConfigPath"
} else {
    Write-Host "Keeping existing config: $ConfigPath"
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    throw "python not found in PATH. Install Python 3.10+ first."
}

& python (Join-Path $SystemDir "assets.py") init
if ($LASTEXITCODE -ne 0) {
    throw "assets.py init failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Installed."
Write-Host "Library: $LibraryRoot"
Write-Host "Next:"
Write-Host "  python `"$SystemDir\assets.py`" analyze `"<path>`""
Write-Host "  python `"$SystemDir\assets.py`" ingest `"<path>`" --apply"
Write-Host ""
Write-Host "If python dependencies are missing:"
Write-Host "  python -m pip install -r `"$SystemDir\requirements.txt`""
