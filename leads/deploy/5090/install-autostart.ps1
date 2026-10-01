# Starts the lead system and the tunnel automatically when you log in.
# Run once from an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File leads\deploy\5090\install-autostart.ps1
# Remove later with: Unregister-ScheduledTask -TaskName "BotFactory Leads*" -Confirm:$false
$ErrorActionPreference = "Stop"
$Kit = $PSScriptRoot
foreach ($job in @(
    @{ Name = "BotFactory Leads";        Script = "start-leads.ps1" },
    @{ Name = "BotFactory Leads Tunnel"; Script = "start-tunnel.ps1" }
)) {
    $action   = New-ScheduledTaskAction -Execute "powershell.exe" `
                -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $Kit $job.Script)`""
    $trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
                -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
    Register-ScheduledTask -TaskName $job.Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Registered: $($job.Name)"
}
Write-Host "Start now with: Start-ScheduledTask 'BotFactory Leads'; Start-ScheduledTask 'BotFactory Leads Tunnel'"
