$ErrorActionPreference = "Stop"

Write-Host "====================================="
Write-Host " Global Exchange - Desarrollo"
Write-Host "====================================="

Write-Host ""
Write-Host "[1/5] Verificando Docker..."
docker --version
docker compose version

Write-Host ""
Write-Host "[2/5] Levantando servicios..."
docker compose up -d --build

Write-Host ""
Write-Host "[3/5] Esperando servicios..."

$maxIntentos = 30
$intento = 0
$webHealthy = $false

while ($intento -lt $maxIntentos) {

    $estado = docker inspect `
        --format='{{.State.Health.Status}}' `
        global-exchange-web 2>$null

    if ($estado -eq "healthy") {
        $webHealthy = $true
        break
    }

    Write-Host "Django todavía está iniciando... ($($intento + 1)/$maxIntentos)"

    Start-Sleep -Seconds 5
    $intento++
}

if (-not $webHealthy) {
    Write-Host ""
    Write-Host "ERROR: Django no quedó healthy."
    Write-Host "Últimos logs:"
    docker compose logs --tail=50 web
    exit 1
}

Write-Host "Django está healthy."

Write-Host ""
Write-Host "[4/5] Verificando Django..."
docker compose exec -T web python manage.py check

Write-Host ""
Write-Host "[5/5] Estado de servicios..."
docker compose ps

Write-Host ""
Write-Host "====================================="
Write-Host " Global Exchange listo"
Write-Host "====================================="
Write-Host ""
Write-Host "App:      http://localhost:8000"
Write-Host "Keycloak: http://localhost:8080"
Write-Host "Mailpit:  http://localhost:8025"