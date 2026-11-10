<#
Task runner for shopflow (PowerShell stand-in for a Makefile).
Usage:  .\tasks.ps1 <task>       Example:  .\tasks.ps1 up
#>
param([Parameter(Position = 0)][string]$Task = "help")

# Not "Stop": docker writes normal progress to stderr, and Windows PowerShell 5.1
# turns redirected stderr lines into errors. We check exit codes instead.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

function Ensure-Env {
    if (-not (Test-Path .env)) {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example"
    }
}

function Assert-Ok([string]$What) {
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $What" -ForegroundColor Red; exit 1 }
}

function Test-Service([string]$Name) {
    docker build --quiet --target test -t "shopflow-$Name-test" "services/$Name" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "test image build failed for $Name" }
    docker run --rm "shopflow-$Name-test"
    if ($LASTEXITCODE -ne 0) { throw "lint or tests failed for $Name" }
}

switch ($Task) {
    "up"     { Ensure-Env; docker compose up -d --build --wait; Assert-Ok "compose up"; Write-Host "Shop: http://localhost:8080   API docs: http://localhost:8000/docs" }
    "down"   { docker compose down }
    "clean"  { docker compose down --volumes --remove-orphans }
    "ps"     { docker compose ps }
    "logs"   { docker compose logs -f --tail 50 }
    "test"   { Test-Service api; Test-Service worker }
    "smoke"  {
        Invoke-RestMethod http://localhost:8080/api/readyz | ConvertTo-Json -Compress
        $order = Invoke-RestMethod -Method Post http://localhost:8080/api/orders -ContentType application/json -Body '{"product_id":1,"quantity":1}'
        Write-Host "order $($order.id) status: $($order.status)"
        Start-Sleep -Seconds 2
        $after = Invoke-RestMethod "http://localhost:8080/api/orders/$($order.id)"
        Write-Host "order $($after.id) status after 2s: $($after.status)"
        if ($after.status -ne "processed") { throw "order was not processed" }
    }
    default  {
        Write-Host "Tasks:"
        Write-Host "  up     build and start the stack, wait until healthy"
        Write-Host "  down   stop the stack (keeps database data)"
        Write-Host "  clean  stop the stack and delete database data"
        Write-Host "  ps     show container status"
        Write-Host "  logs   follow logs of all services"
        Write-Host "  test   run ruff + pytest for api and worker in containers"
        Write-Host "  smoke  place one order through nginx and check the worker processes it"
    }
}
