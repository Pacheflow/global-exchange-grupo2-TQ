$ErrorActionPreference = "Stop"

Write-Host "====================================="
Write-Host " Global Exchange - Desarrollo"
Write-Host "====================================="

try {
    $etapa = "[1/5] Verificando Docker"
    Write-Host "`n$etapa..."
    docker --version
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) { throw "docker --version termino con codigo $codigo." }
    docker compose version
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) { throw "docker compose version termino con codigo $codigo." }

    $etapa = "[2/5] Construyendo y levantando servicios"
    Write-Host "`n$etapa..."
    docker compose up -d --build
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) { throw "docker compose up -d --build termino con codigo $codigo." }

    $etapa = "[3/5] Esperando servicios"
    Write-Host "`n$etapa..."
    # Compose: 180s de inicio + 6 * (15s de intervalo + 10s de timeout)
    # y 30s de margen. Revisar este presupuesto si cambia el healthcheck.
    $maxEsperaSegundos = 360
    $reloj = [System.Diagnostics.Stopwatch]::StartNew()

    while ($true) {
        $respuesta = docker inspect `
            --format='{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}sin-healthcheck{{end}}' `
            global-exchange-web
        $codigo = $LASTEXITCODE
        if ($codigo -ne 0) { throw "docker inspect no pudo consultar web (codigo $codigo)." }

        $estado = ($respuesta -join "").Trim().Split('|')
        if ($estado.Count -ne 2) { throw "docker inspect devolvio un estado no reconocido." }
        if ($estado[0] -eq "running" -and $estado[1] -eq "healthy") { break }
        if ($estado[0] -notin @("running", "created", "restarting")) {
            throw "El servicio web no esta iniciando: estado=$($estado[0])."
        }
        if ($estado[1] -notin @("starting", "healthy")) {
            throw "El servicio web no esta listo: health=$($estado[1])."
        }

        $transcurrido = $reloj.Elapsed.TotalSeconds
        $restante = $maxEsperaSegundos - $transcurrido
        if ($restante -le 0) {
            throw "Se agoto la espera de $maxEsperaSegundos segundos; web sigue en $($estado -join '/')."
        }
        Write-Host "Django sigue iniciando: $($estado -join '/') ($([int]$transcurrido)/$maxEsperaSegundos s)."
        Start-Sleep -Milliseconds ([int][Math]::Min(5000, [Math]::Ceiling($restante * 1000)))
    }

    Write-Host "Django esta healthy."
    $etapa = "[4/5] Verificando Django"
    Write-Host "`n$etapa..."
    docker compose exec -T web python manage.py check
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) { throw "manage.py check termino con codigo $codigo." }

    $etapa = "[5/5] Consultando estado de servicios"
    Write-Host "`n$etapa..."
    docker compose ps
    $codigo = $LASTEXITCODE
    if ($codigo -ne 0) { throw "docker compose ps termino con codigo $codigo." }
}
catch {
    Write-Host "`nERROR en $etapa`: $($_.Exception.Message)"
    if ($etapa -eq "[3/5] Esperando servicios") {
        Write-Host "Ultimos logs de web (diagnostico):"
        try {
            docker compose logs --tail=50 web
            $codigoLogs = $LASTEXITCODE
            if ($codigoLogs -ne 0) { Write-Host "No se pudieron consultar los logs (codigo $codigoLogs)." }
        }
        catch { Write-Host "No se pudieron consultar los logs de diagnostico." }
    }
    exit 1
}

Write-Host ""
Write-Host "====================================="
Write-Host " Global Exchange listo"
Write-Host "====================================="
Write-Host ""
Write-Host "App:      http://localhost:8000"
Write-Host "Keycloak: http://localhost:8080"
Write-Host "Mailpit:  http://localhost:8025"
exit 0
