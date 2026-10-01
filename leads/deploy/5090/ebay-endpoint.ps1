# One command to stand up eBay's Marketplace Account Deletion endpoint on this machine,
# so eBay can switch the Production keyset on (no waiting on the exemption review).
#
#   powershell -ExecutionPolicy Bypass -File leads\deploy\5090\ebay-endpoint.ps1
#   powershell -ExecutionPolicy Bypass -File leads\deploy\5090\ebay-endpoint.ps1 -Hostname leads.example.com   # named tunnel already running
#
# What it does:
#   1. makes .env if missing; adds LEADS_WEBHOOK_TOKEN and EBAY_VERIFICATION_TOKEN if blank
#   2. opens a Cloudflare quick tunnel (or uses -Hostname) and finds the public URL
#   3. saves EBAY_DELETION_ENDPOINT = <url>/ebay/account-deletion to .env
#   4. starts the listener and tests the challenge end to end, the same way eBay will
#   5. prints the two values to paste into eBay, and keeps running (Ctrl+C stops it)
#
# Quick-tunnel URLs change every time the tunnel restarts. eBay must keep reaching the
# endpoint, so after a restart re-paste the new URL into eBay, or set up the named
# tunnel (README step 3) and pass -Hostname.
param([string]$Hostname = "")
$ErrorActionPreference = "Stop"
$Kit  = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Kit "..\..\..")).Path
$EnvFile = Join-Path $Kit ".env"
$Port = if ($env:LEADS_PORT) { $env:LEADS_PORT } else { "8080" }
$Data = Join-Path $Repo "data"
New-Item -ItemType Directory -Force -Path $Data | Out-Null

function New-Secret { [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N") }   # 64 hex chars

function Set-EnvValue([string]$Name, [string]$Value) {
    $lines = @(Get-Content $EnvFile)
    $found = $false
    $lines = $lines | ForEach-Object {
        if ($_ -match "^\s*$Name\s*=") { $found = $true; "$Name=$Value" } else { $_ }
    }
    if (-not $found) { $lines += "$Name=$Value" }
    Set-Content -Path $EnvFile -Value $lines -Encoding ASCII
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

# 1. .env and secrets -------------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Kit ".env.example") $EnvFile
    Write-Host "Made $EnvFile from .env.example"
}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process") }
}
if (-not $env:LEADS_WEBHOOK_TOKEN -or $env:LEADS_WEBHOOK_TOKEN -eq "make-a-long-random-string") {
    Set-EnvValue "LEADS_WEBHOOK_TOKEN" (New-Secret)
}
if (-not $env:EBAY_VERIFICATION_TOKEN) {
    Set-EnvValue "EBAY_VERIFICATION_TOKEN" (New-Secret)
}

# 2. public URL -------------------------------------------------------------------------
$Tunnel = $null
if ($Hostname) {
    $Base = "https://" + ($Hostname -replace '^https?://', '').TrimEnd('/')
} else {
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        throw "cloudflared not found. Install: winget install --id Cloudflare.cloudflared"
    }
    $TunnelLog = Join-Path $Data "tunnel-quick.log"
    if (Test-Path $TunnelLog) { Remove-Item $TunnelLog }
    $Tunnel = Start-Process cloudflared -ArgumentList @("tunnel", "--url", "http://localhost:$Port", "--logfile", $TunnelLog) `
        -WindowStyle Hidden -PassThru
    Write-Host "Opening Cloudflare quick tunnel..."
    $Base = $null
    for ($i = 0; $i -lt 60 -and -not $Base; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $TunnelLog) {
            $hit = Select-String -Path $TunnelLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
            if ($hit) { $Base = $hit.Matches[0].Value }
        }
    }
    if (-not $Base) { Stop-Process -Id $Tunnel.Id -ErrorAction SilentlyContinue; throw "No tunnel URL after 60s. See $TunnelLog" }
}
$Endpoint = "$Base/ebay/account-deletion"
Set-EnvValue "EBAY_DELETION_ENDPOINT" $Endpoint

# 3. listener ---------------------------------------------------------------------------
$env:PYTHONUTF8 = "1"
$Config = Join-Path $Repo "leads.config.json"
if (-not (Test-Path $Config)) { $Config = Join-Path $Repo "leads\config.example.json" }
$Py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$ServeLog = Join-Path $Data "ebay-endpoint.log"
$Server = Start-Process $Py -WorkingDirectory $Repo -WindowStyle Hidden -PassThru `
    -RedirectStandardError $ServeLog `
    -ArgumentList @("-m", "leads", "--config", $Config, "--store", (Join-Path $Data "leads.db"), "serve", "--port", $Port)

# 4. test it the way eBay will: GET ?challenge_code=… must return SHA-256(code + token + endpoint)
$Code = "selftest" + (Get-Random)
$sha = [System.Security.Cryptography.SHA256]::Create()
$Expect = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Code + $env:EBAY_VERIFICATION_TOKEN + $Endpoint)) | ForEach-Object { $_.ToString("x2") })
$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
    Start-Sleep -Seconds 2
    try {
        $reply = Invoke-RestMethod -Uri "$Endpoint`?challenge_code=$Code" -TimeoutSec 10
        $ok = ($reply.challengeResponse -eq $Expect)
    } catch { }
}

Write-Host ""
if ($ok) {
    Write-Host "SELF-TEST PASSED: the public endpoint answers eBay's challenge correctly." -ForegroundColor Green
} else {
    Write-Host "Self-test did not pass yet. Check $ServeLog and $Data\tunnel-quick.log" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Paste these into developer.ebay.com -> Alerts & Notifications -> Marketplace account deletion:"
Write-Host "  Endpoint:            $Endpoint" -ForegroundColor Cyan
Write-Host "  Verification token:  $($env:EBAY_VERIFICATION_TOKEN)" -ForegroundColor Cyan
Write-Host "Also fill in the alert email, click Save, then 'Send Test Notification'."
Write-Host ""
Write-Host "Keep this window open. Ctrl+C stops the endpoint and tunnel."
try {
    while (-not $Server.HasExited) { Start-Sleep -Seconds 5 }
    Write-Host "Listener stopped. See $ServeLog" -ForegroundColor Yellow
} finally {
    if (-not $Server.HasExited) { Stop-Process -Id $Server.Id -ErrorAction SilentlyContinue }
    if ($Tunnel -and -not $Tunnel.HasExited) { Stop-Process -Id $Tunnel.Id -ErrorAction SilentlyContinue }
}
