# Exposes the inbound listener (localhost:8080) over HTTPS with Cloudflare Tunnel.
#   Named tunnel (stable hostname):  start-tunnel.ps1
#   Quick tunnel (random URL, no setup): start-tunnel.ps1 -Quick
param([switch]$Quick)
$ErrorActionPreference = "Stop"
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared not found. Install: winget install --id Cloudflare.cloudflared"
}
$Port = if ($env:LEADS_PORT) { $env:LEADS_PORT } else { "8080" }
if ($Quick) {
    cloudflared tunnel --url "http://localhost:$Port"
} else {
    $Config = Join-Path $PSScriptRoot "cloudflared.yml"
    if (-not (Test-Path $Config)) { throw "Missing $Config - copy cloudflared.example.yml and fill it in (see README)." }
    cloudflared tunnel --config $Config run
}
