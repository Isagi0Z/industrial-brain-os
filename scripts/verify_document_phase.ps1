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
$backendJob = Start-Job { 
    $env:PYTHONPATH="."
    cd d:\industrial-brain\backend
    uvicorn app.main:app --host 127.0.0.1 --port 8000 
}
Start-Sleep -Seconds 7

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -Method Get
    Write-Host "Health check passed."
    
    python app/infrastructure/database/seeder.py
    
    $loginData = @{
        username = "admin@industrialbrain.local"
        password = "ChangeMe123!"
    }
    $login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method Post -Body $loginData
    $token = $login.access_token
    Write-Host "Login passed. Got token."

    # Test Document Upload
    $filePath = "test_document.txt"
    Set-Content -Path $filePath -Value "This is a test document."
    
    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"
    $bodyLines = (
        "--$boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"test_document.txt`"",
        "Content-Type: text/plain",
        "",
        "This is a test document.",
        "--$boundary--"
    ) -join $LF
    
    $uploadParams = @{
        Uri = "http://127.0.0.1:8000/api/v1/documents/"
        Method = "Post"
        Headers = @{
            "Authorization" = "Bearer $token"
            "Content-Type" = "multipart/form-data; boundary=$boundary"
        }
        Body = $bodyLines
    }
    $uploadRes = Invoke-RestMethod @uploadParams
    $docId = $uploadRes.id
    Write-Host "Document Upload passed. ID: $docId"

    # Test Metadata Update
    $metaParams = @{
        Uri = "http://127.0.0.1:8000/api/v1/documents/$docId/metadata"
        Method = "Put"
        Headers = @{
            "Authorization" = "Bearer $token"
            "Content-Type" = "application/json"
        }
        Body = '{"test_key": "test_value"}'
    }
    $metaRes = Invoke-RestMethod @metaParams
    Write-Host "Metadata update passed."

    # Test Fetch List
    $listRes = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/documents/" -Headers @{"Authorization" = "Bearer $token"}
    Write-Host "Document list passed. Total: $($listRes.total)"
    
    # Clean up test file
    Remove-Item $filePath
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
git commit -m "feat(document): implement document management foundation"
git push origin feature/bootstrap

Write-Host "Verification and Commit Complete!"
