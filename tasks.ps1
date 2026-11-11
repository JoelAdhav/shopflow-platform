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

# ---------- Kubernetes (Phase 3) ----------
$Cluster = "shopflow"
$GatewayApiVersion = "v1.6.3"
$TraefikChartVersion = "42.3.2"
$Envs = "dev", "prod"

function Ensure-Secret([string]$EnvName) {
    # Secret values live in a gitignored file. First run: generate a random password.
    $file = "k8s/secrets/$EnvName.env"
    if (-not (Test-Path $file)) {
        $chars = [char[]](48..57 + 65..90 + 97..122)
        $password = -join (1..24 | ForEach-Object { $chars | Get-Random })
        (Get-Content k8s/secrets/dev.env.example) -replace "^POSTGRES_PASSWORD=.*", "POSTGRES_PASSWORD=$password" |
            Set-Content $file -Encoding ascii
        Write-Host "Created $file with a generated password (gitignored)"
    }
    # "create --dry-run | apply" = create the Secret, or update it if it exists.
    kubectl create secret generic shopflow-db -n "shopflow-$EnvName" --from-env-file=$file --dry-run=client -o yaml |
        kubectl apply -f - | Out-Null
    Assert-Ok "create secret for $EnvName"
}

function Get-ImageTag {
    # Tag = git commit. Uncommitted changes add a time suffix so the tag is
    # always new and Kubernetes rolls the pods.
    $tag = (git rev-parse --short HEAD).Trim()
    if (git status --porcelain) { $tag = "$tag-" + (Get-Date -Format "HHmmss") }
    return $tag
}

function Deploy-Apps {
    $tag = Get-ImageTag
    Write-Host "== build images, tag $tag"
    docker compose build --quiet; Assert-Ok "compose build"
    foreach ($s in "api", "worker", "web") {
        docker tag "shopflow-${s}:local" "shopflow-${s}:$tag"
        # kind nodes cannot see the laptop's Docker images; copy them into the node.
        kind load docker-image "shopflow-${s}:$tag" --name $Cluster; Assert-Ok "kind load $s"
    }
    foreach ($e in $Envs) {
        Write-Host "== deploy $e"
        kubectl apply -f "k8s/namespaces/shopflow-$e.yaml" | Out-Null; Assert-Ok "namespace $e"
        Ensure-Secret $e
        helm upgrade --install shopflow charts/shopflow -n "shopflow-$e" `
            -f "charts/shopflow/values-$e.yaml" --set "image.tag=$tag" --wait --timeout 5m
        Assert-Ok "helm upgrade $e"
    }
}

switch ($Task) {
    "k8s-up" {
        if (-not ((kind get clusters) -contains $Cluster)) {
            kind create cluster --config k8s/kind/cluster.yaml --wait 180s; Assert-Ok "kind create cluster"
        }
        Write-Host "== Gateway API CRDs $GatewayApiVersion"
        kubectl apply --server-side -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/$GatewayApiVersion/standard-install.yaml" | Out-Null
        Assert-Ok "gateway api crds"
        Write-Host "== Traefik chart $TraefikChartVersion"
        helm upgrade --install traefik traefik --repo https://traefik.github.io/charts --version $TraefikChartVersion `
            -n traefik --create-namespace -f k8s/gateway/traefik-values.yaml --wait --timeout 5m
        Assert-Ok "helm upgrade traefik"
        kubectl apply -f k8s/gateway/gateway.yaml | Out-Null; Assert-Ok "gateway"
        Deploy-Apps
        Write-Host "dev:  http://dev.shopflow.localhost:8090    prod: http://prod.shopflow.localhost:8090"
    }
    "k8s-deploy" { Deploy-Apps }
    "k8s-status" {
        kubectl get gateway, httproute -A
        foreach ($e in $Envs) { Write-Host "`n== shopflow-$e"; kubectl get pods, svc, pvc -n "shopflow-$e" }
    }
    "k8s-smoke" {
        foreach ($e in $Envs) {
            # curl.exe resolves *.localhost itself; Windows PowerShell's web cmdlets do not.
            $base = "http://$e.shopflow.localhost:8090/api"
            $order = curl.exe -s -X POST "$base/orders" -H "Content-Type: application/json" -d '{\"product_id\":1,\"quantity\":1}' | ConvertFrom-Json
            Start-Sleep -Seconds 3
            $after = curl.exe -s "$base/orders/$($order.id)" | ConvertFrom-Json
            Write-Host "$e : order $($after.id) $($order.status) -> $($after.status)"
            if ($after.status -ne "processed") { Write-Host "FAILED: $e order not processed" -ForegroundColor Red; exit 1 }
        }
    }
    "k8s-down" { kind delete cluster --name $Cluster }
    "up"     { Ensure-Env; docker compose up -d --build --wait; Assert-Ok "compose up"; Write-Host "Shop: http://localhost:8080   API docs: http://localhost:8000/docs" }
    "down"   { docker compose down }
    "clean"  { docker compose down --volumes --remove-orphans }
    "ps"     { docker compose ps }
    "logs"   { docker compose logs -f --tail 50 }
    "test"   { Test-Service api; Test-Service worker }
    "build"  { docker compose build; Assert-Ok "compose build" }
    "scan"   {
        # Same check as CI: fail on HIGH/CRITICAL vulnerabilities that have a fix.
        foreach ($s in "api", "worker", "web") {
            Write-Host "== trivy: shopflow-${s}:local"
            docker run --rm -v //var/run/docker.sock:/var/run/docker.sock -v shopflow-trivy-cache:/root/.cache `
                aquasec/trivy:0.76.2 image --quiet --scanners vuln --severity HIGH,CRITICAL `
                --ignore-unfixed --exit-code 1 "shopflow-${s}:local"
            Assert-Ok "trivy found HIGH/CRITICAL vulnerabilities in $s"
        }
        Write-Host "scan passed: no fixable HIGH/CRITICAL vulnerabilities"
    }
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
        Write-Host "  build  build the three images"
        Write-Host "  scan   Trivy scan of the three images (fails on fixable HIGH/CRITICAL)"
        Write-Host "  smoke  place one order through nginx and check the worker processes it"
        Write-Host "Kubernetes:"
        Write-Host "  k8s-up      create kind cluster, install Gateway API + Traefik, deploy dev and prod"
        Write-Host "  k8s-deploy  rebuild images, load into kind, helm upgrade dev and prod"
        Write-Host "  k8s-status  show gateway, routes, pods, services, volumes"
        Write-Host "  k8s-smoke   place one order in dev and prod through the gateway"
        Write-Host "  k8s-down    delete the kind cluster"
    }
}
