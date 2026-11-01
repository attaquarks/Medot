# Start the local Supabase stack with Google auth credentials loaded from
# supabase/.env.local (gitignored). Run from the repo root:
#   powershell -File scripts/start-stack.ps1
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $repo "supabase/.env.local"

if (-not (Test-Path $envFile)) {
    Write-Host "supabase/.env.local not found."
    Write-Host "Copy supabase/.env.example to supabase/.env.local and add your Google OAuth credentials."
    Write-Host "See docs/medot/12-ac1-verification.md for the full walkthrough."
    exit 1
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.+)\s*$') {
        Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
    }
}

Set-Location (Join-Path $repo "supabase")
npx supabase start
npx supabase status
