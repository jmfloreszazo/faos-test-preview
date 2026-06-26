# Re-parses optimize-runs/*.log to extract the best candidate + score per run and the global winner.
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root 'optimize-runs'

$esc = [char]27
$results = foreach ($log in (Get-ChildItem -Path $logDir -Filter 'run-*.log' | Sort-Object Name)) {
    # Strip ANSI escape sequences and carriage returns left by the spinner.
    $lines = Get-Content $log.FullName | ForEach-Object {
        ($_ -replace "$esc\[[0-9;?]*[A-Za-z]", '' -replace "$esc\[[0-9;]*m", '' -replace "`r", '')
    }
    $runNum = if ($log.Name -match '^run-(\d+)-') { [int]$Matches[1] } else { 0 }

    $jobId = ''
    foreach ($l in $lines) { if ($l -match 'Job ID:\s*(\S+)') { $jobId = $Matches[1]; break } }

    # Parse the Results table: lines like "  candidate_4 *   0.98  View  system_prompt"
    $scores = @{}
    foreach ($l in $lines) {
        if ($l -match '\b(baseline|candidate_\d+)\b' -and $l -match 'View') {
            $name = if ($l -match '\b(baseline|candidate_\d+)\b') { $Matches[1] } else { $null }
            if ($name -and $l -match '([01]\.\d{2})') { $scores[$name] = [double]$Matches[1] }
        }
    }
    # Parse the Candidate IDs section: lines like "    * candidate_4   cand_0123...."
    $ids = @{}
    foreach ($l in $lines) {
        if ($l -match '\b(baseline|candidate_\d+)\s+(cand_[0-9a-fA-F]{32})') {
            $ids[$Matches[1]] = $Matches[2]
        }
    }

    $bestName = $null; $bestScore = $null
    foreach ($kv in $scores.GetEnumerator()) {
        if ($null -eq $bestScore -or $kv.Value -gt $bestScore) { $bestScore = $kv.Value; $bestName = $kv.Key }
    }
    $bestCand = if ($bestName -and $ids.ContainsKey($bestName)) { $ids[$bestName] } else { '' }

    [pscustomobject]@{
        Run           = $runNum
        JobId         = $jobId
        BestName      = $bestName
        BestScore     = $bestScore
        BestCandidate = $bestCand
        AllScores     = ($scores.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ' '
    }
}

$results = $results | Sort-Object Run
$results | Format-Table Run, BestName, BestScore, BestCandidate -AutoSize | Out-String | Write-Host
Write-Host "Per-run detail:" -ForegroundColor DarkGray
$results | ForEach-Object { Write-Host ("  Run {0,2}: {1}" -f $_.Run, $_.AllScores) }

$results | Export-Csv -Path (Join-Path $logDir 'summary.csv') -NoTypeInformation -Encoding UTF8

$winner = $results | Where-Object { $_.BestCandidate } | Sort-Object BestScore -Descending | Select-Object -First 1
if ($winner) {
    @(
        "WINNER_RUN=$($winner.Run)"
        "WINNER_SCORE=$($winner.BestScore)"
        "WINNER_NAME=$($winner.BestName)"
        "WINNER_CANDIDATE=$($winner.BestCandidate)"
        "WINNER_JOB=$($winner.JobId)"
    ) | Set-Content -Path (Join-Path $logDir 'winner.txt') -Encoding UTF8
    Write-Host ""
    Write-Host ("WINNER -> Run {0} | {1} = {2} | {3}" -f $winner.Run, $winner.BestName, $winner.BestScore, $winner.BestCandidate) -ForegroundColor Magenta
}
