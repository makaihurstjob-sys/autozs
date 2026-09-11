param([switch]$Launch, [ValidateRange(1024, 65535)][int]$DebugPort = 9335)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$source = Join-Path $repoRoot 'tools\delivery-check-extension'
$built = Join-Path $repoRoot 'tmp\delivery-check-extension'
$profile = 'C:\AutoZS\chrome-profiles\delivery-checks-guest'
New-Item -ItemType Directory -Force -Path $built | Out-Null
foreach ($name in @('manifest.json', 'background.js', 'page.js')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $built $name)
}
Copy-Item -LiteralPath (Join-Path $repoRoot 'tools\chrome-extension\home-depot-cart-quotes.js') -Destination (Join-Path $built 'cart-quotes.js')
Write-Output "Delivery extension prepared at $built"
if ($Launch) {
    $chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (-not (Test-Path -LiteralPath $chrome)) { throw 'Chrome executable was not found' }
    # Dedicated guest profile: never reuse testing, operations, or checkout profiles.
    New-Item -ItemType Directory -Force -Path $profile | Out-Null
    Start-Process -FilePath $chrome -WindowStyle Hidden -ArgumentList @(
        "--user-data-dir=`"$profile`"", "--load-extension=`"$built`"",
        "--remote-debugging-port=$DebugPort", '--remote-debugging-address=127.0.0.1',
        '--no-first-run', '--no-default-browser-check', 'about:blank'
    )
    $python = Join-Path (Split-Path $repoRoot -Parent) 'venv\Scripts\python.exe'
    & $python (Join-Path $PSScriptRoot 'inspect-delivery-check-worker.py') --port $DebugPort
    if ($LASTEXITCODE -ne 0) { throw 'The isolated delivery extension could not be verified' }
}
