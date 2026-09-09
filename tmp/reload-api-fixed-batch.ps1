$ErrorActionPreference = 'Stop'
. C:\AutoZS\AutoZS-RestartLock.ps1
if (-not (Enter-AutoZSRestartLock)) { throw 'AutoZS restart already in progress' }
try {
  $running = Invoke-RestMethod 'http://127.0.0.1:8000/listing-jobs?status=running&lite=true&limit=1' -TimeoutSec 10
  if (@($running).Count) { throw 'Listing job running; defer reload' }
  $source = Invoke-RestMethod 'http://127.0.0.1:8000/source-refresh/jobs/running' -TimeoutSec 10
  if ($source.running) { throw 'Source capture running; defer reload' }
  $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
  if ($process.CommandLine -notmatch 'uvicorn app.main:app') { throw 'Unexpected API process' }
  Get-Content C:\AutoZS\.env | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
      $settingName, $settingValue = $line -split '=', 2
      [Environment]::SetEnvironmentVariable($settingName, $settingValue, 'Process')
    }
  }
  $env:PYTHONPATH = 'C:\AutoZS\repo\apps\api'
  Stop-Process -Id $listener.OwningProcess
  $newApi = Start-Process C:\AutoZS\venv\Scripts\python.exe -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000') -WorkingDirectory C:\AutoZS\repo\apps\api -RedirectStandardOutput C:\AutoZS\logs\api.stdout.log -RedirectStandardError C:\AutoZS\logs\api.stderr.log -WindowStyle Hidden -PassThru
  $dashboardProcess = (Get-NetTCPConnection -LocalPort 3000 -State Listen).OwningProcess
  @{api=$newApi.Id;dashboard=$dashboardProcess}|ConvertTo-Json|Set-Content C:\AutoZS\autozs.pids.json
  Write-Output "Started AutoZS API process $($newApi.Id)"
} finally { Exit-AutoZSRestartLock }
