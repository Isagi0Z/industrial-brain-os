$ErrorActionPreference = "Stop"

Write-Host "Verifying Backend..."
cd backend
$env:PYTHONPATH="."
$env:MYPYPATH="."
ruff check .
black --check .
mypy --explicit-package-bases .
pytest

Write-Host "Testing backend startup and endpoints..."
# start background job
$backendJob = Start-Job { 
    $env:PYTHONPATH="."
    cd d:\industrial-brain\backend
    uvicorn app.main:app --host 127.0.0.1 --port 8000 
}
Start-Sleep -Seconds 5

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -Method Get
    Write-Host "Health check passed."
    
    # Run seeder to ensure user exists
    python app/infrastructure/database/seeder.py
    
    # Test login
    $loginData = @{
        username = "admin@industrialbrain.local"
        password = "ChangeMe123!"
    }
    $login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method Post -Body $loginData
    Write-Host "Login passed. Got token."
} catch {
    Write-Host "Endpoint test failed: $_"
    throw
} finally {
    Stop-Job $backendJob
    Remove-Job $backendJob
}
cd ..

Write-Host "Verifying Frontend..."
cd frontend
pnpm run lint
pnpm run typecheck
cd ..

Write-Host "Committing changes..."
git add .
git commit -m "feat(auth): finalize production-ready authentication and RBAC foundation"
git push

Write-Host "Verification and Commit Complete!"
