<#
start-app.ps1
- Kills existing backend/frontend dev processes and starts fresh ones.
-- Assumes a Windows PowerShell dev environment and a virtualenv at `venv`.
-- Places logs in `logs/` and `client/` as appropriate.
#>

param(
    [int]$BackendPort = 8000
)

function Stop-ProcessesOnPort {
    param(
        [Parameter(Mandatory=$true)][int]$Port
    )
    try {
        $pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            if ($procId -and $procId -gt 0) {
                try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch { }
                try { taskkill /F /PID $procId | Out-Null } catch { }
            }
        }
    } catch {
        # Best-effort only (Get-NetTCPConnection may be unavailable in some environments)
    }

    # Fallback: netstat parsing is more reliable on some Windows setups.
    try {
        # Use regex so we can match any whitespace after the port.
        $lines = netstat -ano -p TCP | Select-String -Pattern (":$Port\s")
        foreach ($line in $lines) {
            $lineText = $line.Line
            $parts = ($lineText -replace "\s+", " ").Trim().Split(' ')
            # netstat columns: Proto LocalAddress ForeignAddress State PID
            if ($parts.Length -ge 5 -and $parts[3] -eq 'LISTENING') {
                $pid = [int]$parts[4]
                if ($pid -gt 0) {
                    try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch { }
                    try { taskkill /F /PID $pid | Out-Null } catch { }
                }
            }
        }
    } catch {
        # Best-effort only
    }
}

Write-Host "Stopping existing uvicorn and node processes (if any)..."
Stop-ProcessesOnPort -Port $BackendPort
Stop-ProcessesOnPort -Port 3000
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
    # If a .env.local file exists, import environment variables (do not commit this file).
    $envLocal = Join-Path -Path $PSScriptRoot -ChildPath '.env.local'
    if(Test-Path $envLocal){
        Write-Host "Loading .env.local variables..."
        Get-Content $envLocal | ForEach-Object {
            if($_ -and $_ -match '^(\s*#)') { return }
            $parts = $_ -split '=', 2
            if($parts.Length -ne 2) { return }
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim('"')
            if($k) { [System.Environment]::SetEnvironmentVariable($k, $v, 'Process') }
        }
    }
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
        Start-Process -FilePath 'node.exe' -ArgumentList @($reactScripts,'start') -WorkingDirectory $clientDir -NoNewWindow -RedirectStandardOutput $outLog -RedirectStandardError $errLog
        Write-Host "Frontend started; logs -> $outLog"
    } else {
        Write-Warning "react-scripts not found at $reactScripts. Run 'npm ci' in client/ first, then rerun start-app.ps1"
    }
} else {
    Write-Warning "client directory not found at $clientDir. Start frontend manually in client/"
}

Write-Host "Done. Give the frontend a few seconds to boot and visit http://localhost:3000 (or configured dev port). Backend is at http://127.0.0.1:$BackendPort."
