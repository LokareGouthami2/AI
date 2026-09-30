# WriteAI 2.0 — one-time setup on Windows (PowerShell).
# Needs: Python 3.11+ and Node.js 22+ on PATH. Tesseract is optional (OCR of scanned PDFs).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python not found. Install Python 3.11+ from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js not found. Install Node.js 22 LTS from https://nodejs.org/" }

if (-not (Test-Path ".venv")) { python -m venv .venv }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements-dev.txt
& $Py -m spacy download en_core_web_sm
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

Set-Location (Join-Path $Root "frontend")
npm ci --no-audit --no-fund
Set-Location $Root
Write-Host "Setup complete. Start with: .\scripts\dev.ps1" -ForegroundColor Green
