<#!
ci.ps1
- Runs local CI-equivalent checks in a Windows-safe way (works in paths containing '&').
- Mirrors GitHub Actions intent in .github/workflows/ci.yml.

Usage:
  ./ci.ps1
  ./ci.ps1 -SkipFrontend
  ./ci.ps1 -SkipBackend
#>

[CmdletBinding()]
param(
  [switch]$SkipBackend,
  [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'

function Resolve-PythonExe {
  $root = $PSScriptRoot
  $candidates = @(
    (Join-Path $root '.venv\Scripts\python.exe'),
    (Join-Path $root 'venv\Scripts\python.exe')
  )
  foreach($c in $candidates){
    if(Test-Path $c){ return $c }
  }
  return 'python'
}

function Assert-Success([int]$code, [string]$step){
  if($code -ne 0){
    throw "Step failed ($step) with exit code $code"
  }
}

if(-not $SkipBackend){
  Write-Host "== Backend checks ==" -ForegroundColor Cyan
  $py = Resolve-PythonExe
  Write-Host "Python: $py"

  & $py -m ruff check server/
  Assert-Success $LASTEXITCODE 'ruff'

  # Keep mypy aligned with repo config (currently non-blocking in GH Actions).
  & $py -m mypy server
  if($LASTEXITCODE -ne 0){
    Write-Warning "mypy reported issues (non-blocking in CI)."
  }

  & $py -m pytest server/tests -q
  Assert-Success $LASTEXITCODE 'pytest'
}

if(-not $SkipFrontend){
  Write-Host "== Frontend checks ==" -ForegroundColor Cyan
  $clientDir = Join-Path $PSScriptRoot 'client'
  if(-not (Test-Path $clientDir)){
    throw "client/ directory not found"
  }

  Push-Location $clientDir
  try{
    if(-not (Test-Path (Join-Path $clientDir 'node_modules'))){
      Write-Host "Installing frontend deps (npm ci)..." -ForegroundColor Yellow
      npm ci
      Assert-Success $LASTEXITCODE 'npm ci'
    }

    Write-Host "Typecheck (tsc --noEmit)..." -ForegroundColor Gray
    node node_modules/typescript/bin/tsc --noEmit
    Assert-Success $LASTEXITCODE 'tsc'

    Write-Host "Tests (react-scripts test)..." -ForegroundColor Gray
    $env:CI = 'true'
    node node_modules/react-scripts/bin/react-scripts.js test --watchAll=false
    Assert-Success $LASTEXITCODE 'frontend tests'

    Write-Host "Build (react-scripts build)..." -ForegroundColor Gray
    $env:CI = 'true'
    node node_modules/react-scripts/bin/react-scripts.js build
    Assert-Success $LASTEXITCODE 'frontend build'
  }
  finally{
    Pop-Location
  }
}

Write-Host "All blocking checks passed." -ForegroundColor Green
