<#
start-app.ps1
- Kills existing backend/frontend dev processes and starts fresh ones.
-- Assumes a Windows PowerShell dev environment and a virtualenv at `venv`.
-- Places logs in `logs/` and `client/` as appropriate.
#>

param(
    [int]$BackendPort = 8000
)

Write-Host "Stopping existing uvicorn and node processes (if any)..."
Get-Process -Name uvicorn -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like '*venv*' } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Get-Process -Name node -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }

if(-not (Test-Path -Path .\logs)) { New-Item -ItemType Directory -Path .\logs | Out-Null }

Write-Host "Starting backend (uvicorn) on port $BackendPort..."
$VenvPython = Join-Path -Path $PSScriptRoot -ChildPath '.venv\Scripts\python.exe'
if(-not (Test-Path $VenvPython)){
    $VenvPython = Join-Path -Path $PSScriptRoot -ChildPath 'venv\Scripts\python.exe'
}
if(Test-Path $VenvPython) {
    Start-Process -FilePath $VenvPython -ArgumentList '-m','uvicorn','server.main:app','--host','127.0.0.1','--port',$BackendPort,'--reload' -NoNewWindow -RedirectStandardOutput '.\logs\backend-out.log' -RedirectStandardError '.\logs\backend-err.log'
    Write-Host "Backend started; logs -> .\logs\\backend-out.log"
} else {
    Write-Warning "Virtualenv python not found at $VenvPython. Start backend manually: python -m uvicorn server.main:app --reload"
}

Write-Host "Starting frontend (npm start) in a new process..."
$clientDir = Join-Path -Path $PSScriptRoot -ChildPath 'client'
if(Test-Path $clientDir) {
    $outLog = Join-Path $clientDir 'npm-out.log'
    $errLog = Join-Path $clientDir 'npm-err.log'
    $reactScripts = Join-Path $clientDir 'node_modules\react-scripts\bin\react-scripts.js'
    if(Test-Path $reactScripts) {
        Start-Process -FilePath 'node.exe' -ArgumentList $reactScripts,'start' -WorkingDirectory $clientDir -NoNewWindow -RedirectStandardOutput $outLog -RedirectStandardError $errLog
        Write-Host "Frontend started; logs -> $outLog"
    } else {
        Write-Warning "react-scripts not found at $reactScripts. Run 'npm ci' in client/ first, then rerun start-app.ps1"
    }
} else {
    Write-Warning "client directory not found at $clientDir. Start frontend manually in client/"
}

Write-Host "Done. Give the frontend a few seconds to boot and visit http://localhost:3000 (or configured dev port). Backend is at http://127.0.0.1:$BackendPort."
