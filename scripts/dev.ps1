# WriteAI 2.0 — start API (8000) + web UI (5173) on Windows and open the browser.
# Stop: close the two windows that open (or run .\scripts\dev.ps1 -Stop).
param([switch]$Stop)
$Root = Split-Path -Parent $PSScriptRoot

function Stop-WriteAI {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "uvicorn backend.main:app|vite --host|title WriteAI API" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
if ($Stop) { Stop-WriteAI; Write-Host "stopped"; exit 0 }
Stop-WriteAI

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Run .\scripts\setup.ps1 first." }

# "cmd /k" keeps the API window open if it stops, so its error stays readable.
Start-Process -FilePath "cmd.exe" -ArgumentList "/k title WriteAI API && `"$Py`" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $Root -WindowStyle Minimized
Start-Process -FilePath "cmd.exe" -ArgumentList "/c npx vite --host 127.0.0.1 --port 5173" -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Minimized

Write-Host "Starting WriteAI..." -NoNewline
for ($i = 0; $i -lt 120; $i++) {
  try {
    Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health -TimeoutSec 2 | Out-Null
    Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173 -TimeoutSec 2 | Out-Null
    Write-Host " ready." -ForegroundColor Green
    Write-Host "Web: http://localhost:5173    API docs: http://localhost:8000/api/docs"
    Start-Process "http://localhost:5173"
    exit 0
  } catch { Start-Sleep -Seconds 1; Write-Host "." -NoNewline }
}
Write-Host ""
Write-Host "WriteAI did not start in time. Open the minimized 'WriteAI API' window to see the error." -ForegroundColor Red
exit 1
