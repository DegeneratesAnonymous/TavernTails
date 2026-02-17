<#
.SYNOPSIS
    Start TavernTAIls development services (backend and/or frontend)

.DESCRIPTION
    Starts the backend (FastAPI with uvicorn) and frontend (React dev server) for local development.
    By default, starts both services. Use switches to run only one service.
    Press Enter to stop all running services.

.PARAMETER BackendPort
    Port for the backend API server (default: 8000)

.PARAMETER FrontendOnly
    Start only the frontend React dev server

.PARAMETER BackendOnly
    Start only the backend FastAPI server

.EXAMPLE
    .\start-app.ps1
    Start both backend and frontend services

.EXAMPLE
    .\start-app.ps1 -BackendOnly
    Start only the backend service

.EXAMPLE
    .\start-app.ps1 -FrontendOnly
    Start only the frontend service

.EXAMPLE
    .\start-app.ps1 -BackendPort 8080
    Start both services with backend on port 8080
#>

param(
    [int]$BackendPort = 8000,
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)

# Validate that both switches aren't used together
if ($FrontendOnly -and $BackendOnly) {
    Write-Error "Cannot use -FrontendOnly and -BackendOnly together. Choose one or neither."
    exit 1
}

Write-Host "=== TavernTAIls Local Development Startup ===" -ForegroundColor Cyan
Write-Host ""

# Determine what to start
$startBackend = -not $FrontendOnly
$startFrontend = -not $BackendOnly

# Store process IDs for cleanup
$script:BackendProcess = $null
$script:FrontendProcess = $null

# Cleanup function
function Stop-DevServices {
    Write-Host ""
    Write-Host "Stopping services..." -ForegroundColor Yellow
    
    if ($script:BackendProcess -and -not $script:BackendProcess.HasExited) {
        Write-Host "Stopping backend process (PID: $($script:BackendProcess.Id))..."
        Stop-Process -Id $script:BackendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    
    if ($script:FrontendProcess -and -not $script:FrontendProcess.HasExited) {
        Write-Host "Stopping frontend process (PID: $($script:FrontendProcess.Id))..."
        Stop-Process -Id $script:FrontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    
    # Also kill any remaining node/uvicorn processes that might be orphaned
    Get-Process -Name node -ErrorAction SilentlyContinue | ForEach-Object { 
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue 
    }
    Get-Process -Name uvicorn -ErrorAction SilentlyContinue | ForEach-Object { 
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue 
    }
    
    Write-Host "All services stopped." -ForegroundColor Green
}

function Stop-ProcessesOnPort {
    param(
        [Parameter(Mandatory=$true)][int]$Port
    )
    try {
        $processIds = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($processId in $processIds) {
            if ($processId -and $processId -gt 0) {
                try { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue } catch { }
                try { taskkill /F /PID $processId | Out-Null } catch { }
            }
        }
    } catch {
        # Best-effort only (Get-NetTCPConnection may be unavailable in some environments)
    }
}

# Register cleanup on script exit
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-DevServices }

# Clean up any existing processes
Write-Host "Cleaning up existing processes..." -ForegroundColor Gray
Stop-ProcessesOnPort -Port $BackendPort
Stop-ProcessesOnPort -Port 3000
Get-Process -Name uvicorn -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like '*venv*' } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Get-Process -Name node -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500

# Ensure logs directory exists
if (-not (Test-Path -Path .\logs)) { 
    New-Item -ItemType Directory -Path .\logs | Out-Null 
}

# Start Backend
if ($startBackend) {
    Write-Host "Starting backend (uvicorn) on port $BackendPort..." -ForegroundColor Green
    $VenvPython = Join-Path -Path $PSScriptRoot -ChildPath '.venv\Scripts\python.exe'
    if (-not (Test-Path $VenvPython)) {
        $VenvPython = Join-Path -Path $PSScriptRoot -ChildPath 'venv\Scripts\python.exe'
    }
    
    if (Test-Path $VenvPython) {
        $backendLogOut = Join-Path -Path $PSScriptRoot -ChildPath 'logs\backend-out.log'
        $backendLogErr = Join-Path -Path $PSScriptRoot -ChildPath 'logs\backend-err.log'
        
        # If a .env.local file exists, import environment variables (do not commit this file).
        $envLocal = Join-Path -Path $PSScriptRoot -ChildPath '.env.local'
        if (Test-Path $envLocal) {
            Write-Host "  Loading .env.local variables..." -ForegroundColor Gray
            Get-Content $envLocal | ForEach-Object {
                if ($_ -and $_ -match '^(\s*#)') { return }
                $parts = $_ -split '=', 2
                if ($parts.Length -ne 2) { return }
                $k = $parts[0].Trim()
                $v = $parts[1].Trim().Trim('"')
                if ($k) { [System.Environment]::SetEnvironmentVariable($k, $v, 'Process') }
            }
        }
        
        $script:BackendProcess = Start-Process -FilePath $VenvPython `
            -ArgumentList '-m','uvicorn','server.main:app','--host','0.0.0.0','--port',$BackendPort,'--reload' `
            -WorkingDirectory $PSScriptRoot `
            -NoNewWindow `
            -RedirectStandardOutput $backendLogOut `
            -RedirectStandardError $backendLogErr `
            -PassThru
        
        Write-Host "  ✓ Backend started (PID: $($script:BackendProcess.Id))" -ForegroundColor Green
        Write-Host "  → API: http://127.0.0.1:$BackendPort" -ForegroundColor Gray
        Write-Host "  → Docs: http://127.0.0.1:$BackendPort/docs" -ForegroundColor Gray
        Write-Host "  → Logs: $backendLogOut" -ForegroundColor Gray
    } else {
        Write-Warning "Virtualenv python not found at $VenvPython"
        Write-Host "  Please run: python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r server\requirements.txt" -ForegroundColor Yellow
    }
    Write-Host ""
}

# Start Frontend
if ($startFrontend) {
    Write-Host "Starting frontend (React dev server)..." -ForegroundColor Green
    $clientDir = Join-Path -Path $PSScriptRoot -ChildPath 'client'
    
    if (Test-Path $clientDir) {
        $frontendLogOut = Join-Path $clientDir 'npm-out.log'
        $frontendLogErr = Join-Path $clientDir 'npm-err.log'
        $reactScripts = Join-Path $clientDir 'node_modules\react-scripts\bin\react-scripts.js'
        
        if (Test-Path $reactScripts) {
            $apiUrl = "http://127.0.0.1:$BackendPort"
            # Start react-scripts with REACT_APP_API_URL set so the frontend always targets the same backend port.
            # This avoids confusing failures like 405 Method Not Allowed when an old backend is still running on :8000.
            # NOTE: On some Windows setups, CRA's ESLint plugin can fail with a false "Plugin 'react' was conflicted"
            # error due to drive-letter/path casing differences (C:\ vs c:\). Disabling the plugin unblocks dev
            # startup; CI still runs linting/typechecks.
            # IMPORTANT: Avoid passing a string to powershell.exe -Command here; paths in this repo can contain '&'
            # (e.g. OneDrive\Dungeons&Dragons\...), which PowerShell would otherwise treat as an operator.
            $env:REACT_APP_API_URL = $apiUrl
            $env:DISABLE_ESLINT_PLUGIN = 'true'
            
            $script:FrontendProcess = Start-Process -FilePath 'node.exe' `
                -ArgumentList @($reactScripts,'start') `
                -WorkingDirectory $clientDir `
                -NoNewWindow `
                -RedirectStandardOutput $frontendLogOut `
                -RedirectStandardError $frontendLogErr `
                -PassThru
            
            Write-Host "  ✓ Frontend started (PID: $($script:FrontendProcess.Id))" -ForegroundColor Green
            Write-Host "  → UI: http://localhost:3000 (will open in browser)" -ForegroundColor Gray
            Write-Host "  → Logs: $frontendLogOut" -ForegroundColor Gray
        } else {
            Write-Warning "react-scripts not found at $reactScripts"
            Write-Host "  Run 'npm ci' in client/ first, then rerun start-app.ps1" -ForegroundColor Yellow
        }
    } else {
        Write-Warning "client directory not found at $clientDir"
        Write-Host "  Please ensure the client directory exists" -ForegroundColor Yellow
    }
    Write-Host ""
}

# Show status and wait for user input
Write-Host "=== Services Running ===" -ForegroundColor Cyan
if ($startBackend) {
    Write-Host "  Backend:  http://127.0.0.1:$BackendPort" -ForegroundColor White
    Write-Host "  Docs:     http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
}
if ($startFrontend) {
    Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
}
Write-Host ""
Write-Host "Press Enter to stop all services..." -ForegroundColor Yellow
$null = Read-Host

# Stop services
Stop-DevServices
