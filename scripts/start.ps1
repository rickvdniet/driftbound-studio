# One-command start (native Windows PowerShell): API + worker + built dashboard on http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw "FFmpeg not found. See docs/SETUP.md" }
if (-not (Test-Path backend\.venv)) {
  py -3.12 -m venv backend\.venv
  backend\.venv\Scripts\pip install -q -e "backend[dev]"
}
if (-not (Test-Path frontend\dist)) { Push-Location frontend; npm install --no-audit --no-fund; npm run build; Pop-Location }
Set-Location backend
$worker = Start-Process -PassThru -NoNewWindow .venv\Scripts\python.exe "-m app.workers.worker"
try {
  Write-Host "Driftbound Studio: http://127.0.0.1:8000"
  .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
} finally { Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue }
