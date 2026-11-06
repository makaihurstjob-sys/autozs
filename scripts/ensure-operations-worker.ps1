$ErrorActionPreference = "Stop"

$root = "C:\AutoZS"
$repo = Split-Path $PSScriptRoot -Parent
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profile = Join-Path $root "chrome-profiles\testing"
$extension = Join-Path $repo "tools\chrome-extension"
$api = "http://127.0.0.1:8000"
$dashboard = "https://desktop-56u49jf.tailb2892a.ts.net/?api=https://desktop-56u49jf.tailb2892a.ts.net:8443&autozs_worker_mode=operations"
$logPath = Join-Path $root "logs\autozs-chrome-worker-ensure.log"
$runnableStatuses = @("queued", "running", "processing", "in_progress")
$queuePaths = @(
    "/products/capture-queue",
    "/listing-jobs",
    "/source-refresh/jobs",
    "/ebay/revision-jobs",
    "/ebay/revision-batches",
    "/ebay/sync-runs",
    "/depop/jobs"
)

New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null

function Write-WorkerLog([string]$message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $logPath -Value "[$timestamp] $message"
}

function Get-QueueItems([object]$payload) {
    if ($null -eq $payload) {
        return @()
    }
    if ($payload -is [array]) {
        return @($payload)
    }
    if ($null -ne $payload.items) {
        return @($payload.items)
    }
    return @()
}

function Test-MainWorkerRunning {
    $escapedProfile = [Regex]::Escape("--user-data-dir=$profile")
    $browser = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -match $escapedProfile } |
        Select-Object -First 1
    return $null -ne $browser
}

if (-not (Test-Path -LiteralPath $chrome)) {
    throw "Chrome was not found at the configured path."
}
if (-not (Test-Path -LiteralPath (Join-Path $extension "manifest.json"))) {
    throw "The AutoZS Chrome extension is missing."
}

$health = Invoke-WebRequest -Uri "$api/health" -UseBasicParsing -TimeoutSec 5
if ($health.StatusCode -ne 200) {
    throw "The AutoZS API is not healthy."
}

$runnableCount = 0
foreach ($path in $queuePaths) {
    try {
        $payload = Invoke-RestMethod -Uri "$api$path" -TimeoutSec 10
        foreach ($item in (Get-QueueItems $payload)) {
            $status = ([string]$item.status).ToLowerInvariant()
            if ($runnableStatuses -contains $status) {
                $runnableCount++
            }
        }
    } catch {
        Write-WorkerLog "Queue check failed for $path."
    }
}

if ($runnableCount -eq 0) {
    Write-WorkerLog "No runnable work; Chrome worker not required."
    exit 0
}

function Test-OperationsExtension {
    $mutex = [Threading.Mutex]::new($false, 'Local\AutoZS-OperationsExtensionHealth')
    $held = $false
    try {
        try { $held = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) { Write-WorkerLog 'Another operations extension health check is in progress.'; return }
        $node = Join-Path $env:ProgramFiles 'nodejs\node.exe'
        if (-not (Test-Path -LiteralPath $node)) { throw 'Node is required to verify the AUTOZS operations extension.' }
        $output = & $node (Join-Path $PSScriptRoot 'ensure-operations-extension.mjs')
        if ($LASTEXITCODE -ne 0) { throw 'AUTOZS operations extension verification failed.' }
        Write-WorkerLog (($output | Out-String).Trim())
    } finally {
        if ($held) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}

if (Test-MainWorkerRunning) {
    Test-OperationsExtension
    Write-WorkerLog "Main worker is already running; runnable jobs=$runnableCount."
    exit 0
}

New-Item -ItemType Directory -Force -Path $profile | Out-Null
Start-Process -FilePath $chrome -WindowStyle Hidden -ArgumentList @(
    "--user-data-dir=$profile",
    "--profile-directory=Default",
    "--load-extension=`"$extension`"",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-session-crashed-bubble",
    "--remote-debugging-port=9225",
    "--new-window",
    $dashboard
)
Write-WorkerLog "Started the main operations worker; runnable jobs=$runnableCount."

Start-Sleep -Seconds 3
Test-OperationsExtension
