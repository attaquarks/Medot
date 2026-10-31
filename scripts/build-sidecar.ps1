# Build the Medot runtime sidecar executable (PyInstaller onefile) and place it
# where the Tauri bundler expects it. Run from the repo root:
#   powershell -File scripts/build-sidecar.ps1
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location "$repo/runtime"

uv run --extra dev pyinstaller `
  --onefile --name medot-runtime --collect-submodules uvicorn `
  --paths . --distpath ../desktop/src-tauri/binaries `
  --workpath build --specpath build --noconfirm run_runtime.py

$triple = & rustc -vV | Select-String "host:" | ForEach-Object { ($_ -split ": ")[1].Trim() }
Copy-Item "../desktop/src-tauri/binaries/medot-runtime.exe" `
  "../desktop/src-tauri/binaries/medot-runtime-$triple.exe" -Force
Write-Host "Sidecar built for $triple"
