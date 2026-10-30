#!/usr/bin/env bash
set -Eeuo pipefail

# Despliegue productivo reproducible para Global Exchange.
umask 077
export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/compose.prod.yaml}"
BACKUP_DIR="${BACKUP_DIR:-$(dirname -- "${PROJECT_DIR}")/global-exchange-backups}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
REMOTE_NAME="${REMOTE_NAME:-origin}"
LOCK_FILE="${LOCK_FILE:-/tmp/global-exchange-production-deploy.lock}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PREVIOUS_COMMIT=""

compose() {
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

log() {
  printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

diagnostics() {
  status=$?
  if [ "${status}" -eq 0 ]; then return; fi
  printf '\nEl despliegue falló (código %s). El código anterior era %s.\n' \
    "${status}" "${PREVIOUS_COMMIT:-no registrado}" >&2
  compose ps -a >&2 || true
  compose logs --tail=120 web nginx keycloak postgres >&2 || true
  printf '\nNo ejecute down --volumes. Revise los logs y el backup %s.\n' \
    "${BACKUP_DIR}/${STAMP}" >&2
}
trap diagnostics EXIT

for command in git docker flock sha256sum; do
  command -v "${command}" >/dev/null 2>&1 || die "Falta el comando requerido: ${command}"
done
docker compose version >/dev/null 2>&1 || die "Docker Compose no está disponible."

exec 9>"${LOCK_FILE}"
flock -n 9 || die "Ya existe otro despliegue en ejecución."

cd "${PROJECT_DIR}"
[ -f "${ENV_FILE}" ] || die "No existe ${ENV_FILE}."
[ ! -L "${ENV_FILE}" ] || die "El archivo de entorno no puede ser un enlace simbólico."
chmod 600 "${ENV_FILE}"
[ -f "${COMPOSE_FILE}" ] || die "No existe ${COMPOSE_FILE}."

if grep -Eq '(^|=)(REEMPLAZAR_|CAMBIAR_)' "${ENV_FILE}"; then
  die "El archivo de entorno todavía contiene marcadores REEMPLAZAR_/CAMBIAR_."
fi

log "Validando Compose y estado del repositorio"
compose config --quiet
[ "$(git branch --show-current)" = "${DEPLOY_BRANCH}" ] || die "La rama activa debe ser ${DEPLOY_BRANCH}."
[ -z "$(git status --porcelain)" ] || die "El repositorio tiene cambios locales. Guárdelos o descártelos antes de desplegar."

PREVIOUS_COMMIT="$(git rev-parse HEAD)"
mkdir -p "${BACKUP_DIR}/${STAMP}"
chmod 700 "${BACKUP_DIR}" "${BACKUP_DIR}/${STAMP}"

postgres_id="$(compose ps -q postgres 2>/dev/null || true)"
if [ -n "${postgres_id}" ] && [ "$(docker inspect -f '{{.State.Running}}' "${postgres_id}")" = "true" ]; then
  log "Creando backups privados de PostgreSQL"
  compose exec -T postgres sh -eu -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"${BACKUP_DIR}/${STAMP}/django.dump"
  compose exec -T postgres sh -eu -c 'pg_dump -U "$POSTGRES_USER" -d keycloak -Fc' >"${BACKUP_DIR}/${STAMP}/keycloak.dump"
  [ -s "${BACKUP_DIR}/${STAMP}/django.dump" ] || die "El backup de Django está vacío."
  [ -s "${BACKUP_DIR}/${STAMP}/keycloak.dump" ] || die "El backup de Keycloak está vacío."
  sha256sum "${BACKUP_DIR}/${STAMP}/django.dump" "${BACKUP_DIR}/${STAMP}/keycloak.dump" >"${BACKUP_DIR}/${STAMP}/SHA256SUMS"
  chmod 600 "${BACKUP_DIR}/${STAMP}"/*
else
  log "PostgreSQL aún no está iniciado; se omite el backup por tratarse de un primer despliegue"
fi

log "Actualizando ${DEPLOY_BRANCH} desde ${REMOTE_NAME} (solo fast-forward)"
git fetch --prune "${REMOTE_NAME}" "${DEPLOY_BRANCH}"
git merge --ff-only "${REMOTE_NAME}/${DEPLOY_BRANCH}"
DEPLOY_COMMIT="$(git rev-parse HEAD)"
printf '%s\n' "${PREVIOUS_COMMIT}" >"${BACKUP_DIR}/${STAMP}/PREVIOUS_COMMIT"
printf '%s\n' "${DEPLOY_COMMIT}" >"${BACKUP_DIR}/${STAMP}/DEPLOY_COMMIT"

log "Construyendo imágenes de forma secuencial"
compose build --pull --build-arg "BUILD_COMMIT=${DEPLOY_COMMIT}" web
compose build --pull nginx

wait_for_health() {
  service="$1"
  timeout_seconds="$2"
  elapsed=0
  while [ "${elapsed}" -lt "${timeout_seconds}" ]; do
    container_id="$(compose ps -q "${service}" 2>/dev/null || true)"
    if [ -n "${container_id}" ]; then
      state="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "${container_id}")"
      case "${state}" in
        "running healthy") return 0 ;;
        "exited "*|"dead "*|"running unhealthy") die "El servicio ${service} terminó en estado: ${state}" ;;
      esac
    fi
    sleep 5
    elapsed=$((elapsed + 5))
  done
  die "El servicio ${service} no quedó saludable después de ${timeout_seconds}s."
}

wait_for_completion() {
  service="$1"
  timeout_seconds="$2"
  elapsed=0
  while [ "${elapsed}" -lt "${timeout_seconds}" ]; do
    container_id="$(compose ps -a -q "${service}" 2>/dev/null || true)"
    if [ -n "${container_id}" ]; then
      state="$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "${container_id}")"
      case "${state}" in
        "exited 0") return 0 ;;
        "exited "*|"dead "*) die "El servicio ${service} terminó en estado: ${state}" ;;
      esac
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  die "El servicio ${service} no terminó correctamente después de ${timeout_seconds}s."
}

log "Iniciando dependencias persistentes"
compose up -d postgres keycloak
wait_for_health postgres 180
wait_for_health keycloak 240

log "Aplicando configuración idempotente de Keycloak"
compose up -d --force-recreate keycloak-config
wait_for_completion keycloak-config 180
compose up -d --force-recreate keycloak-web-config
wait_for_completion keycloak-web-config 180

log "Recreando Django con la imagen recién construida"
compose up -d --force-recreate --no-deps web
wait_for_health web 300

log "Recreando Nginx para renovar la resolución interna de Django"
compose up -d --force-recreate --no-deps --remove-orphans nginx
wait_for_health nginx 180

log "Ejecutando comprobaciones posteriores"
web_container_id="$(compose ps -q web)"
deployed_commit="$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${web_container_id}")"
[ "${deployed_commit}" = "${DEPLOY_COMMIT}" ] || \
  die "La imagen web no corresponde al commit desplegado (${deployed_commit:-sin etiqueta})."
compose exec -T web python -c 'import facturacion; print("Módulo facturacion:", facturacion.__file__)'
compose exec -T web python manage.py migrate --check
compose exec -T web python manage.py showmigrations facturacion --plan
compose exec -T web python manage.py check --deploy
compose exec -T nginx wget -qO- http://127.0.0.1:8080/nginx-health | grep -qx 'ok'
compose ps -a

trap - EXIT
log "Despliegue completado: ${PREVIOUS_COMMIT:0:12} -> ${DEPLOY_COMMIT:0:12}"
printf 'Backup: %s\n' "${BACKUP_DIR}/${STAMP}"
