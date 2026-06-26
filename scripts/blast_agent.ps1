<#
.SYNOPSIS
    Fire a large batch of synthetic customer-support questions at the deployed
    hosted agent's OpenAI /responses endpoint to generate production traces.

.DESCRIPTION
    The hosted agent emits OpenTelemetry traces to Application Insights / Foundry
    for every runtime invocation. By blasting it with many varied, realistic
    questions we create a rich pool of production traces that can then be curated
    in the Foundry portal ("Create dataset" -> Supervised/Reinforcement fine-tuning
    or Evaluation) filtered by agent + date range.

    Each request is STATELESS (no azd session state is shared), so it parallelizes
    safely. We call the responses endpoint directly with a bearer token from
    `az account get-access-token` (scope https://ai.azure.com/.default).

.PARAMETER Count
    Number of questions to send. Default 1000.

.PARAMETER Throttle
    Max concurrent requests. Default 8.

.PARAMETER Endpoint
    The responses endpoint. Defaults to AGENT_SUPPORT_AGENT_RESPONSES_ENDPOINT
    from `azd env get-values`.

.EXAMPLE
    pwsh -File scripts/blast_agent.ps1 -Count 1000 -Throttle 8
#>
[CmdletBinding()]
param(
    [int]$Count = 1000,
    [int]$Throttle = 4,
    [int]$Retries = 5,
    [string]$Endpoint
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- Resolve the endpoint from the azd environment if not supplied ----------
if (-not $Endpoint) {
    $vals = azd env get-values 2>$null
    foreach ($line in $vals) {
        if ($line -match '^AGENT_SUPPORT_AGENT_RESPONSES_ENDPOINT="?(.*?)"?$') {
            $Endpoint = $Matches[1]
        }
    }
}
if (-not $Endpoint) {
    throw "Could not resolve the responses endpoint. Pass -Endpoint explicitly."
}
Write-Host "Endpoint: $Endpoint" -ForegroundColor DarkGray

# --- Acquire a bearer token (valid ~60-75 min; enough for one batch) ---------
Write-Host "Acquiring access token (scope https://ai.azure.com/.default)..." -ForegroundColor DarkGray
$token = az account get-access-token --scope "https://ai.azure.com/.default" --query accessToken -o tsv
if (-not $token) { throw "Failed to acquire an access token. Run 'az login' first." }

# --- Synthetic question bank -------------------------------------------------
# Built by combining intent templates with fillers so we get >=1000 varied,
# realistic questions across the agent's domains (returns, shipping, warranty)
# plus off-topic prompts that should trigger a human hand-off.
$products = @(
    'headphones','a laptop','a blender','running shoes','a phone','a smartwatch',
    'a coffee machine','a backpack','a monitor','a keyboard','a jacket','a camera',
    'a vacuum cleaner','a tablet','sunglasses','a desk lamp','a microwave','a printer'
)
$periods = @(
    '3 days','a week','two weeks','20 days','a month','45 days','two months',
    '6 months','8 months','a year','18 months','two years','25 months'
)

$returnTemplates = @(
    'How many days do I have to return {p}?',
    'I bought {p} {t} ago, can I still return it?',
    'Can I return {p} without the original packaging?',
    'I lost the receipt for {p}, am I able to return it?',
    'What is your return policy for {p}?',
    'How do I get a refund for {p}?',
    'I want to exchange {p} for a different size, how does that work?',
    'Is the return window for {p} really 30 days?',
    'My {p} arrived but I changed my mind, can I send it back?',
    'Do I need the box to return {p}?'
)
$shippingTemplates = @(
    'How long does standard shipping take for {p}?',
    'How much does express shipping cost?',
    'When will {p} arrive with standard delivery?',
    'Can I get {p} delivered in 24 hours?',
    'What is the difference between standard and express shipping?',
    'Is express shipping worth the extra cost for {p}?',
    'How fast can you ship {p}?',
    'Whats the delivery time on {p}?',
    'Do you offer next-day delivery for {p}?',
    'How much extra is express shipping for {p}?'
)
$warrantyTemplates = @(
    'What warranty does {p} come with?',
    'My {p} stopped working after {t}, is it covered?',
    'Does the warranty on {p} cover manufacturing defects?',
    'How long is the warranty on {p}?',
    'Is {p} still under warranty after {t}?',
    'The screen on {p} cracked, will the warranty cover it?',
    'Can I claim the warranty for {p} after {t}?',
    'What does the 2-year warranty cover for {p}?',
    'My {p} is defective, what are my warranty options?',
    'Does {p} have a guarantee against defects?'
)
# Off-topic / out-of-scope: should produce a graceful hand-off to a human.
$handoffTemplates = @(
    'Do you ship {p} internationally?',
    'Can I pay for {p} with cryptocurrency?',
    'Do you offer a student discount on {p}?',
    'Can I price match {p} with another store?',
    'Do you have {p} in stock in your physical store?',
    'Can I schedule an installation for {p}?',
    'Is there a loyalty program I can join?',
    'Can you gift wrap {p} for me?'
)

function Expand-Templates {
    param([string[]]$Templates)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($t in $Templates) {
        foreach ($p in $products) {
            if ($t -match '\{t\}') {
                foreach ($per in $periods) {
                    $s = ($t -replace '\{p\}', $p) -replace '\{t\}', $per
                    $out.Add($s)
                }
            }
            else {
                $s = $t -replace '\{p\}', $p
                $out.Add($s)
            }
        }
    }
    return $out
}

$bank = New-Object System.Collections.Generic.List[string]
foreach ($set in @($returnTemplates, $shippingTemplates, $warrantyTemplates, $handoffTemplates)) {
    Expand-Templates -Templates $set | ForEach-Object { $bank.Add($_) }
}
# De-duplicate, shuffle, take Count (cycling if the bank is smaller).
$bank = $bank | Sort-Object -Unique | Get-Random -Count $bank.Count
$questions = @()
for ($i = 0; $i -lt $Count; $i++) { $questions += $bank[$i % $bank.Count] }

Write-Host ("Question bank: {0} unique, sending {1} requests at throttle {2}." -f $bank.Count, $Count, $Throttle) -ForegroundColor Cyan

# --- Output log --------------------------------------------------------------
$logDir = Join-Path $root 'optimize-runs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$csv = Join-Path $logDir "blast-$ts.csv"
$startUtc = [DateTime]::UtcNow

# --- Fire in parallel --------------------------------------------------------
$indexed = 0..($questions.Count - 1) | ForEach-Object { [pscustomobject]@{ Index = $_ + 1; Question = $questions[$_] } }

$results = $indexed | ForEach-Object -ThrottleLimit $Throttle -Parallel {
    $ep = $using:Endpoint
    $maxRetries = $using:Retries
    $q = $_.Question
    $idx = $_.Index
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $status = 'error'
    $answer = ''
    $attempts = 0
    $body = @{ input = $q } | ConvertTo-Json -Compress

    # Each worker holds its own bearer and self-heals on token expiry (401).
    # A long run (88+ min) outlives a single token (~60-75 min), so we refresh
    # on demand. az caches/refreshes via MSAL, so this is cheap and thread-safe.
    $bearer = $using:token
    $authRefreshes = 0
    $maxAuthRefreshes = 5

    for ($attempt = 1; $attempt -le $maxRetries; $attempt++) {
        $attempts = $attempt
        try {
            $resp = Invoke-RestMethod -Method Post -Uri $ep `
                -Headers @{ Authorization = "Bearer $bearer" } `
                -ContentType 'application/json' -Body $body -TimeoutSec 120
            $answer = (($resp.output | Where-Object { $_.type -eq 'message' }).content.text -join ' ')
            if (-not [string]::IsNullOrWhiteSpace($answer)) {
                $status = 'ok'
                break
            }
            # HTTP 200 but no assistant message => model throttled mid-turn. Retry.
            $status = 'empty'
        }
        catch {
            $status = 'error'
            $answer = $_.Exception.Message
            # Token expired mid-run: refresh and retry WITHOUT spending the budget.
            if ($answer -match '401' -and $authRefreshes -lt $maxAuthRefreshes) {
                $authRefreshes++
                $fresh = az account get-access-token --scope "https://ai.azure.com/.default" --query accessToken -o tsv 2>$null
                if ($fresh) { $bearer = $fresh }
                $attempt--   # do not consume a retry for an auth refresh
                continue
            }
        }
        if ($attempt -lt $maxRetries) {
            # Exponential backoff with jitter to relieve model rate limits.
            $delay = [math]::Min(30, [math]::Pow(2, $attempt)) + (Get-Random -Minimum 0.0 -Maximum 1.0)
            Start-Sleep -Seconds $delay
        }
    }

    $sw.Stop()
    [pscustomobject]@{
        Index    = $idx
        Status   = $status
        Attempts = $attempts
        Seconds  = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        Question = $q
        Answer   = ($answer -replace '\r?\n', ' ')
    }
} | Sort-Object Index

$endUtc = [DateTime]::UtcNow
$results | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8

$ok = ($results | Where-Object Status -eq 'ok').Count
$empty = ($results | Where-Object Status -eq 'empty').Count
$err = ($results | Where-Object Status -eq 'error').Count
$avg = if ($results.Count) { [math]::Round((($results | Measure-Object Seconds -Average).Average), 2) } else { 0 }
$retried = ($results | Where-Object { $_.Attempts -gt 1 }).Count

Write-Host ""
Write-Host "======================= BLAST SUMMARY =======================" -ForegroundColor Yellow
Write-Host ("Sent:        {0}" -f $results.Count)
Write-Host ("Succeeded:   {0}" -f $ok) -ForegroundColor Green
Write-Host ("Empty (200, no message - throttled): {0}" -f $empty) -ForegroundColor ($(if ($empty) { 'Red' } else { 'Green' }))
Write-Host ("Errors:      {0}" -f $err) -ForegroundColor ($(if ($err) { 'Red' } else { 'Green' }))
Write-Host ("Retried:     {0}" -f $retried)
Write-Host ("Avg latency: {0}s" -f $avg)
Write-Host ("CSV log:     {0}" -f $csv)
Write-Host ""
Write-Host "Trace time window (UTC) for the Foundry 'Create dataset' filter:" -ForegroundColor Cyan
Write-Host ("  From: {0:yyyy-MM-ddTHH:mm:ssZ}" -f $startUtc)
Write-Host ("  To:   {0:yyyy-MM-ddTHH:mm:ssZ}" -f $endUtc)
