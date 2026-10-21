param([string]$Api = 'http://127.0.0.1:8000', [ValidateRange(1024, 65535)][int]$DebugPort = 9335)
# Keeps the isolated delivery-check worker available while checks are waiting. Called every five
# minutes by C:\AutoZS\Ensure-AutoZS.ps1 (task "AutoZS Operations Server"). Chrome ignores
# --load-extension, so the worker exists only after the launcher's CDP load: a closed browser, or
# one restarted any other way, otherwise leaves queued checks waiting with nothing to claim them.
# Never closes a browser; it only launches the dedicated profile or loads the worker into it.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$profile = 'C:\AutoZS\chrome-profiles\delivery-checks-guest'
$built = Join-Path $repoRoot 'tmp\delivery-check-extension'
$prepare = Join-Path $PSScriptRoot 'prepare-delivery-check-worker.ps1'
$logPath = 'C:\AutoZS\logs\autozs-delivery-worker-ensure.log'

function Write-WorkerLog([string]$message) {
    New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null
    Add-Content -LiteralPath $logPath -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $message"
}

function Get-UnpackedExtensionId([string]$path) {
    # Chrome derives an unpacked extension's ID from the SHA-256 of its UTF-16 path, digits 0-f as a-p.
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash([Text.Encoding]::Unicode.GetBytes($path)) } finally { $sha.Dispose() }
    return -join ($hash[0..15] | ForEach-Object { [char](97 + ($_ -shr 4)); [char](97 + ($_ -band 15)) })
}

function Test-WorkerLoaded {
    $workerUrl = "chrome-extension://$(Get-UnpackedExtensionId $built)/background.js"
    $targets = Invoke-RestMethod "http://127.0.0.1:$DebugPort/json/list" -TimeoutSec 5
    return [bool]($targets | Where-Object { $_.url -eq $workerUrl })
}

function Format-Output([object[]]$lines) { return (($lines | Out-String).Trim() -replace '\s+', ' ') }

$policy = Invoke-RestMethod "$Api/delivery-quotes/policy" -TimeoutSec 10
if (-not $policy.enabled -and -not $policy.trial) { exit 0 }
$jobs = Invoke-RestMethod "$Api/delivery-quotes/jobs" -TimeoutSec 15
$waiting = @($jobs | Where-Object { $_.status -in @('queued', 'running') }).Count
if ($waiting -eq 0) { exit 0 }

$browser = Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" | Where-Object {
    $commandLine = [string]$_.CommandLine
    $commandLine.IndexOf($profile, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $commandLine -notmatch '--type='
} | Select-Object -First 1

if (-not $browser) {
    try {
        $output = & $prepare -Launch -DebugPort $DebugPort
    } catch {
        Write-WorkerLog "Launching the isolated delivery worker failed ($waiting waiting): $($_.Exception.Message)"
        throw
    }
    Write-WorkerLog "Launched the isolated delivery worker ($waiting waiting): $(Format-Output $output)"
    exit 0
}

try {
    # A stopped extension service worker drops out of the target list between alarms, so look twice.
    $loaded = Test-WorkerLoaded
    if (-not $loaded) { Start-Sleep -Seconds 35; $loaded = Test-WorkerLoaded }
} catch {
    Write-WorkerLog "Isolated delivery browser (PID $($browser.ProcessId)) is not answering on port $DebugPort; close it so the next check relaunches it."
    exit 0
}
if ($loaded) { exit 0 }

$python = Join-Path (Split-Path $repoRoot -Parent) 'venv\Scripts\python.exe'
$output = @(& $prepare -DebugPort $DebugPort) + @(& $python (Join-Path $PSScriptRoot 'inspect-delivery-check-worker.py') --port $DebugPort)
if ($LASTEXITCODE -ne 0) {
    Write-WorkerLog "Loading the delivery worker into the running browser failed ($waiting waiting): $(Format-Output $output)"
    throw 'The isolated delivery extension could not be loaded into the running browser'
}
Write-WorkerLog "Loaded the delivery worker into the running browser ($waiting waiting): $(Format-Output $output)"
