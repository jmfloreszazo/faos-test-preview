[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $JobId,
    [string] $Endpoint = 'https://aisvc-yrwwwokfuruzy.services.ai.azure.com',
    [string] $ApiVersion = '2024-10-21',
    [int]    $IntervalSec = 60
)

$ErrorActionPreference = 'Stop'
$terminal = @('succeeded', 'failed', 'cancelled')
$lastStatus = ''
$lastEventId = ''

function Get-Token {
    az account get-access-token --scope https://cognitiveservices.azure.com/.default --query accessToken -o tsv
}

Write-Host "Watching $JobId (poll every ${IntervalSec}s)..."
while ($true) {
    try {
        $h = @{ Authorization = "Bearer $(Get-Token)" }
        $base = "$Endpoint/openai/fine_tuning/jobs/$JobId"
        $job = Invoke-RestMethod -Headers $h -Uri "${base}?api-version=$ApiVersion"

        if ($job.status -ne $lastStatus) {
            $ts = (Get-Date).ToString('HH:mm:ss')
            Write-Host "[$ts] status: $($job.status)"
            $lastStatus = $job.status
        }

        # Stream new events for progress visibility.
        try {
            $ev = Invoke-RestMethod -Headers $h -Uri "${base}/events?api-version=$ApiVersion"
            $events = @($ev.data | Sort-Object created_at)
            foreach ($e in $events) {
                if ($e.id -and $e.id -gt $lastEventId) {
                    $et = ([DateTimeOffset]::FromUnixTimeSeconds($e.created_at)).LocalDateTime.ToString('HH:mm:ss')
                    Write-Host "  [$et] $($e.message)"
                    $lastEventId = $e.id
                }
            }
        } catch { }

        if ($terminal -contains $job.status) {
            Write-Host ""
            Write-Host "DONE: $($job.status)"
            Write-Host "  fine_tuned_model: $($job.fine_tuned_model)"
            Write-Host "  trained_tokens:   $($job.trained_tokens)"
            break
        }
    } catch {
        Write-Host "poll error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $IntervalSec
}
