# Runs the lead system on this machine: sweep loop + inbound listener.
#   powershell -ExecutionPolicy Bypass -File leads\deploy\5090\start-leads.ps1
# Reads secrets from .env next to this script. Logs to data\leads.log.
$ErrorActionPreference = "Stop"
$Kit  = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Kit "..\..\..")).Path
$EnvFile = Join-Path $Kit ".env"
if (-not (Test-Path $EnvFile)) { throw "Missing $EnvFile - copy .env.example to .env and fill it in." }
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process") }
}
$env:PYTHONUTF8 = "1"   # log lines use arrows/stars; keep Windows consoles and log files happy
$Port  = if ($env:LEADS_PORT) { $env:LEADS_PORT } else { "8080" }
$Every = if ($env:SWEEP_EVERY) { $env:SWEEP_EVERY } else { "1800" }
$Data  = Join-Path $Repo "data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null
$Config = Join-Path $Repo "leads.config.json"
if (-not (Test-Path $Config)) { $Config = Join-Path $Repo "leads\config.example.json" }
Set-Location $Repo
$Py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $Py -m leads --config $Config --store (Join-Path $Data "leads.db") check
& $Py -m leads --config $Config --store (Join-Path $Data "leads.db") loop --serve --port $Port --every $Every *>> (Join-Path $Data "leads.log")
