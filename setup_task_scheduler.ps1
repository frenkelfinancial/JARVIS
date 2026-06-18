# Registers a Windows Task Scheduler task that fires Jarvis at 9:00 AM Central daily.
# Run this script ONCE from PowerShell (as your normal user, no admin needed for user tasks):
#   powershell -ExecutionPolicy Bypass -File "C:\Users\jacef\Jarvis\setup_task_scheduler.ps1"

$taskName  = "Jarvis Daily Brief"
$jarvisDir = "C:\Users\jacef\Jarvis"
$python    = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $python) {
    Write-Host "ERROR: python not found in PATH. Install Python and re-run." -ForegroundColor Red
    exit 1
}

# Unregister old version if it exists
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action  = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "main.py --now" `
    -WorkingDirectory $jarvisDir

# 9:00 AM daily. Windows stores tasks in local time, so Central = correct as-is.
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -WakeToRun:$false `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Jarvis daily intelligence brief — runs all agents and emails jace@frenkelfinancial.com" `
    -RunLevel Limited | Out-Null

Write-Host ""
Write-Host "Task '$taskName' registered successfully." -ForegroundColor Green
Write-Host "  Fires:    Daily at 9:00 AM (your local / Central time)"
Write-Host "  Script:   $jarvisDir\main.py --now"
Write-Host "  Python:   $python"
Write-Host ""
Write-Host "To verify: open Task Scheduler and look for '$taskName' under Task Scheduler Library."
Write-Host "To test now: python `"$jarvisDir\main.py`" --now"
