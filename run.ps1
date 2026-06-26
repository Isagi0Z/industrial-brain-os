# Industrial Brain OS Task Runner for Windows PowerShell

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("help", "install", "dev", "lint", "format", "test", "up", "down", "clean")]
    [string]$Action
)

function Show-Help {
    Write-Host "Industrial Brain OS PowerShell Task Runner" -ForegroundColor Green
    Write-Host "Usage: ./run.ps1 -Action <action>"
    Write-Host "Available actions:"
    Write-Host "  help    - Show this help message"
    Write-Host "  install - Install backend, frontend, and shared dependencies"
    Write-Host "  dev     - Start local dev services (requires separate shells for backend/frontend)"
    Write-Host "  lint    - Run linters on backend (black, ruff) and frontend"
    Write-Host "  format  - Run formatters on backend and frontend"
    Write-Host "  test    - Run backend tests (pytest)"
    Write-Host "  up      - Spin up docker compose infrastructure services"
    Write-Host "  down    - Stop docker compose infrastructure services"
    Write-Host "  clean   - Remove pycache, node_modules, and build artifacts"
}

switch ($Action) {
    "help" {
        Show-Help
    }
    "install" {
        Write-Host "Installing backend requirements..." -ForegroundColor Cyan
        pip install -r backend/requirements.txt
        Write-Host "Installing shared python package..." -ForegroundColor Cyan
        pip install -e shared/python
        Write-Host "Installing frontend node modules..." -ForegroundColor Cyan
        Set-Location frontend
        pnpm install
        Set-Location ..
        Write-Host "Installation completed!" -ForegroundColor Green
    }
    "dev" {
        Write-Host "To run dev environment:" -ForegroundColor Cyan
        Write-Host "1. Backend: cd backend; uvicorn app.main:app --reload" -ForegroundColor Yellow
        Write-Host "2. Frontend: cd frontend; pnpm run dev" -ForegroundColor Yellow
    }
    "lint" {
        Write-Host "Linting backend code..." -ForegroundColor Cyan
        black --check backend/app backend/tests
        ruff check backend/app backend/tests
        Write-Host "Linting frontend code..." -ForegroundColor Cyan
        Set-Location frontend
        pnpm run lint
        Set-Location ..
    }
    "format" {
        Write-Host "Formatting backend code..." -ForegroundColor Cyan
        black backend/app backend/tests
        ruff check --fix backend/app backend/tests
        Write-Host "Formatting frontend code..." -ForegroundColor Cyan
        Set-Location frontend
        if (Get-Member -InputObject (pnpm run) -Name "format") {
            pnpm run format
        }
        Set-Location ..
    }
    "test" {
        Write-Host "Running backend tests..." -ForegroundColor Cyan
        pytest backend/
    }
    "up" {
        Write-Host "Spinning up docker infrastructure..." -ForegroundColor Cyan
        docker compose up -d
    }
    "down" {
        Write-Host "Stopping docker infrastructure..." -ForegroundColor Cyan
        docker compose down
    }
    "clean" {
        Write-Host "Cleaning temporary folders..." -ForegroundColor Cyan
        Get-ChildItem -Path . -Filter "__pycache__" -Recurse -Directory | Remove-Item -Force -Recurse
        Get-ChildItem -Path . -Filter "*.pyc" -Recurse | Remove-Item -Force
        Get-ChildItem -Path . -Filter ".pytest_cache" -Recurse -Directory | Remove-Item -Force -Recurse
        Get-ChildItem -Path . -Filter ".mypy_cache" -Recurse -Directory | Remove-Item -Force -Recurse
        if (Test-Path frontend/node_modules) { Remove-Item frontend/node_modules -Force -Recurse }
        if (Test-Path frontend/dist) { Remove-Item frontend/dist -Force -Recurse }
        Write-Host "Cleanup completed!" -ForegroundColor Green
    }
}
