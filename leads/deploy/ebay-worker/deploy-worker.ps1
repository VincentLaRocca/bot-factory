# Puts eBay's account-deletion endpoint on Cloudflare Workers: free, always on,
# a permanent https://ebay-deletion.<your-account>.workers.dev address.
#
#   powershell -ExecutionPolicy Bypass -File leads\deploy\ebay-worker\deploy-worker.ps1
#
# First run opens a browser once so you can sign in to Cloudflare (free account).
# Then it deploys, sets the two secrets, self-tests eBay's challenge, and prints
# the Endpoint + Verification token to paste into developer.ebay.com.
# Re-running is safe: it keeps the same address and token.
$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Kit  = Resolve-Path (Join-Path $Here "..\5090")
$EnvFile = Join-Path $Kit ".env"
Set-Location $Here

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "Node.js not found. Install: winget install OpenJS.NodeJS.LTS  (then open a new PowerShell)"
}

# Token: reuse the one in the 5090 .env if there is one, so both endpoints agree.
$Token = $null
if (Test-Path $EnvFile) {
    $line = Get-Content $EnvFile | Where-Object { $_ -match '^\s*EBAY_VERIFICATION_TOKEN\s*=\s*(\S+)' } | Select-Object -First 1
    if ($line -and $line -match '=\s*(\S+)') { $Token = $Matches[1] }
}
if (-not $Token) { $Token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N") }

Write-Host "Checking Cloudflare sign-in (a browser window opens the first time)..."
$who = npx --yes wrangler@4 whoami 2>&1 | Out-String
if ($LASTEXITCODE -ne 0 -or $who -match "not authenticated|not logged in") { npx --yes wrangler@4 login }

Write-Host "Deploying the endpoint (answer 'yes' if asked to register a workers.dev subdomain)..."
npx --yes wrangler@4 deploy          # interactive: first-time prompts work here
# Second deploy is a no-op change but prints the address in a form we can read.
$out = npx --yes wrangler@4 deploy 2>&1 | Out-String
Write-Host $out
$m = [regex]::Match($out, 'https://ebay-deletion\.[a-z0-9-]+\.workers\.dev')
if (-not $m.Success) { throw "Could not find the workers.dev address in the deploy output above." }
$Base = $m.Value
$Endpoint = "$Base/ebay/account-deletion"

Write-Host "Setting secrets..."
$Token    | npx --yes wrangler@4 secret put EBAY_VERIFICATION_TOKEN | Out-Null
$Endpoint | npx --yes wrangler@4 secret put EBAY_DELETION_ENDPOINT  | Out-Null

# Keep the 5090 .env in step (the local listener uses the same pair).
if (Test-Path $EnvFile) {
    $lines = @(Get-Content $EnvFile)
    foreach ($pair in @(@("EBAY_VERIFICATION_TOKEN", $Token), @("EBAY_DELETION_ENDPOINT", $Endpoint))) {
        $name, $value = $pair
        if ($lines -match "^\s*$name\s*=") { $lines = $lines | ForEach-Object { if ($_ -match "^\s*$name\s*=") { "$name=$value" } else { $_ } } }
        else { $lines += "$name=$value" }
    }
    Set-Content -Path $EnvFile -Value $lines -Encoding ASCII
}

# Self-test the way eBay does.
$Code = "selftest" + (Get-Random)
$sha = [System.Security.Cryptography.SHA256]::Create()
$Expect = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Code + $Token + $Endpoint)) | ForEach-Object { $_.ToString("x2") })
$ok = $false
for ($i = 0; $i -lt 15 -and -not $ok; $i++) {
    Start-Sleep -Seconds 2
    try { $ok = ((Invoke-RestMethod -Uri "$Endpoint`?challenge_code=$Code" -TimeoutSec 10).challengeResponse -eq $Expect) } catch { }
}

Write-Host ""
if ($ok) { Write-Host "SELF-TEST PASSED: the endpoint answers eBay's challenge correctly." -ForegroundColor Green }
else     { Write-Host "Self-test not passing yet (new workers.dev addresses can take a minute). Re-run this script." -ForegroundColor Yellow }
Write-Host ""
Write-Host "Paste into developer.ebay.com -> Alerts & Notifications -> Marketplace account deletion:"
Write-Host "  Endpoint:            $Endpoint" -ForegroundColor Cyan
Write-Host "  Verification token:  $Token" -ForegroundColor Cyan
Write-Host "Add an alert email, click Save, then 'Send Test Notification'. This address is permanent."
