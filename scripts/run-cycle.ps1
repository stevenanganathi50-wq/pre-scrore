# One scheduled cycle: sync fixtures, publish predictions, grade finished
# matches, regenerate the site, push to Supabase.
#
# Registered by scripts/install-schedule.ps1. Safe to run by hand.
#
# Why this matters more than a normal cron job: a prediction cannot be written
# after kickoff, by design. A missed run is not a late prediction, it is a
# permanently absent one, and a track record with silent holes in it is worth
# nothing. So this logs every run, and exits non-zero when anything fails, so
# the failure is visible rather than quiet.

$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "data\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }

$log = Join-Path $logDir ("cycle-{0}.log" -f (Get-Date -Format "yyyy-MM"))
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Log([string]$text) {
    Add-Content -Path $log -Value $text -Encoding utf8
    Write-Host $text
}

Write-Log ""
Write-Log "=== cycle $stamp ==="

Set-Location $root

$failed = @()

# The horizon is a trade-off. Longer means more chances to catch a fixture
# before kickoff if a run is missed; shorter means the ratings behind the
# prediction are fresher. A week gives many chances at modest staleness.
$steps = @(
    @{ name = "run";  args = @("-m", "prescore", "run", "--horizon-days", "7") },
    @{ name = "push"; args = @("-m", "prescore", "push") }
)

foreach ($step in $steps) {
    Write-Log "--- $($step.name) ---"
    $output = & python $step.args 2>&1
    $code = $LASTEXITCODE
    foreach ($line in $output) { Write-Log "    $line" }
    if ($code -ne 0) {
        Write-Log "    !! $($step.name) exited $code"
        $failed += $step.name
    }
}

if ($failed.Count -gt 0) {
    Write-Log "=== FAILED: $($failed -join ', ') ==="
    exit 1
}

Write-Log "=== ok ==="
exit 0
