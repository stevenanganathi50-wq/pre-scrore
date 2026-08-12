# Registers the pre-scrore cycle as a Windows scheduled task.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-schedule.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-schedule.ps1 -Uninstall
#
# Runs every 6 hours as the current user. No password is stored, so the task
# only runs while you are logged on -- registering a "run whether logged on or
# not" task would require handing over your Windows password, which is not
# worth it for this.
#
# StartWhenAvailable is deliberate: if the machine was asleep at the scheduled
# time, the run happens as soon as it wakes rather than being skipped. A
# prediction cannot be written after kickoff, so a skipped run is a permanent
# hole in the record, not a delay.

param(
    [switch]$Uninstall,
    [int]$IntervalHours = 6
)

$ErrorActionPreference = "Stop"

$taskName = "pre-scrore cycle"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\run-cycle.ps1"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($Uninstall) {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "removed scheduled task '$taskName'"
    } else {
        Write-Host "no scheduled task named '$taskName'"
    }
    return
}

if (-not (Test-Path $script)) { throw "cannot find $script" }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

# -Once plus a repetition interval is how Task Scheduler expresses "every N
# hours, forever". The long duration stands in for "indefinitely".
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(15)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration ([TimeSpan]::FromDays(3650))).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "replacing existing task"
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "pre-scrore: sync fixtures, publish predictions before kickoff, grade results, push to Supabase." | Out-Null

Write-Host "registered '$taskName', every $IntervalHours hours"
Write-Host ""
Write-Host "  check status : Get-ScheduledTask -TaskName '$taskName'"
Write-Host "  run it now   : Start-ScheduledTask -TaskName '$taskName'"
Write-Host "  logs         : $root\data\logs\"
Write-Host "  remove       : install-schedule.ps1 -Uninstall"
