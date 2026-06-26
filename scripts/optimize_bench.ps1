# Runs the Foundry Agent Optimizer N times, logs each run, and picks the best-scoring candidate.
# Usage: pwsh -File scripts/optimize_bench.ps1 [-Runs 10]
param(
    [int]$Runs = 10,
    [string]$Config = 'src/support-agent/eval.yaml'
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logDir = Join-Path $root 'optimize-runs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$results = @()

for ($i = 1; $i -le $Runs; $i++) {
    $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
    $log = Join-Path $logDir "run-$i-$ts.log"
    Write-Host ""
    Write-Host "==================== Run $i/$Runs started $ts ====================" -ForegroundColor Cyan

    & azd ai agent optimize --config $Config --no-prompt *>&1 | Tee-Object -FilePath $log

    $content = Get-Content $log -Raw

    $jobId = if ($content -match 'Job ID:\s*(\S+)') { $Matches[1] } else { '' }
    $status = if ($content -match 'succeeded') { 'succeeded' }
              elseif ($content -match 'EvalServiceTimeoutError') { 'failed:timeout' }
              elseif ($content -match 'AllEvaluatorsFailedError') { 'failed:400' }
              elseif ($content -match 'failed|ERROR') { 'failed' }
              else { 'unknown' }

    # Best score: the line in the Results table where the candidate name is followed by the star and a score.
    $bestScore = $null
    foreach ($line in ($content -split "`n")) {
        if ($line -match '\u2605\s+([0-9]+\.[0-9]+)') { $bestScore = [double]$Matches[1] }
    }
    # Best candidate id: the starred row in the "Candidate IDs" section.
    $bestCand = if ($content -match '\u2605\s+\S+\s+(cand_[0-9a-fA-F]+)') { $Matches[1] } else { '' }

    $row = [pscustomobject]@{
        Run           = $i
        Status        = $status
        JobId         = $jobId
        BestScore     = $bestScore
        BestCandidate = $bestCand
        Log           = (Split-Path $log -Leaf)
    }
    $results += $row
    Write-Host "==================== Run $i done: status=$status score=$bestScore cand=$bestCand ====================" -ForegroundColor Green

    # Persist a running summary after every iteration so progress survives interruptions.
    $results | Export-Csv -Path (Join-Path $logDir 'summary.csv') -NoTypeInformation -Encoding UTF8
}

Write-Host ""
Write-Host "======================= SUMMARY =======================" -ForegroundColor Yellow
$results | Format-Table -AutoSize | Out-String | Write-Host

$winner = $results |
    Where-Object { $_.Status -eq 'succeeded' -and $_.BestCandidate -and $_.BestScore -ne $null } |
    Sort-Object BestScore -Descending |
    Select-Object -First 1

if ($winner) {
    $winnerFile = Join-Path $logDir 'winner.txt'
    @(
        "WINNER_RUN=$($winner.Run)"
        "WINNER_SCORE=$($winner.BestScore)"
        "WINNER_CANDIDATE=$($winner.BestCandidate)"
        "WINNER_JOB=$($winner.JobId)"
    ) | Set-Content -Path $winnerFile -Encoding UTF8
    Write-Host "WINNER: Run $($winner.Run) | score=$($winner.BestScore) | candidate=$($winner.BestCandidate)" -ForegroundColor Magenta
    Write-Host "Saved to $winnerFile"
} else {
    Write-Host "No successful run produced a candidate. Check the logs in $logDir." -ForegroundColor Red
}
