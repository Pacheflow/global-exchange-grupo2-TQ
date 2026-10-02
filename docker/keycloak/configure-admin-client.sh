#!/bin/sh
# Este archivo debe conservar finales de línea LF para ejecutarse en Linux.
set -eu

KCADM=/opt/keycloak/bin/kcadm.sh
SERVER_URL=${KEYCLOAK_INTERNAL_URL:-http://keycloak:8080}
REALM=${KEYCLOAK_REALM:-global-exchange}
CLIENT_ID=${KEYCLOAK_ADMIN_CLIENT_ID:-global-exchange-admin-api}
CLIENT_SECRET=${KEYCLOAK_ADMIN_CLIENT_SECRET:?KEYCLOAK_ADMIN_CLIENT_SECRET es obligatorio}

echo "Configurando cliente técnico de administración de Keycloak..."
"$KCADM" config credentials \
  --server "$SERVER_URL" \
  --realm master \
  --user "$KEYCLOAK_ADMIN" \
  --password "$KEYCLOAK_ADMIN_PASSWORD"

client_uuid=$("$KCADM" get clients -r "$REALM" -q clientId="$CLIENT_ID" --fields id \
  | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)

if [ -z "$client_uuid" ]; then
  "$KCADM" create clients -r "$REALM" \
    -s clientId="$CLIENT_ID" \
    -s name="Global Exchange Admin API" \
    -s enabled=true \
    -s publicClient=false \
    -s secret="$CLIENT_SECRET" \
    -s serviceAccountsEnabled=true \
    -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -s fullScopeAllowed=false
  client_uuid=$("$KCADM" get clients -r "$REALM" -q clientId="$CLIENT_ID" --fields id \
    | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)
else
  "$KCADM" update "clients/$client_uuid" -r "$REALM" \
    -s enabled=true \
    -s publicClient=false \
    -s secret="$CLIENT_SECRET" \
    -s serviceAccountsEnabled=true \
    -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -s fullScopeAllowed=false
fi

realm_management_uuid=$("$KCADM" get clients -r "$REALM" -q clientId=realm-management --fields id \
  | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)

for role in query-users view-users manage-users view-realm; do
  "$KCADM" add-roles -r "$REALM" \
    --uusername "service-account-$CLIENT_ID" \
    --cclientid realm-management \
    --rolename "$role"

  # Además de asignarlo a la cuenta de servicio, incluir únicamente este rol
  # en el scope del token emitido para el cliente confidencial.
  role_json=$("$KCADM" get "clients/$realm_management_uuid/roles/$role" -r "$REALM" -c)
  "$KCADM" create "clients/$client_uuid/scope-mappings/clients/$realm_management_uuid" \
    -r "$REALM" -b "[$role_json]"
done

# Crear los roles de negocio también en realms persistidos que fueron importados
# antes de que estos roles formaran parte del archivo de configuración.
for business_role in USUARIO CAJERO ANALISTA_CAMBIARIO ADMINISTRADOR; do
  if ! "$KCADM" get "roles/$business_role" -r "$REALM" >/dev/null 2>&1; then
    "$KCADM" create roles -r "$REALM" -s name="$business_role"
  fi
done

# Todo autorregistro recibe el rol base de negocio. La operación es idempotente
# y también actualiza realms creados antes de incorporar esta configuración.
"$KCADM" add-roles -r "$REALM" \
  --rname "default-roles-$REALM" \
  --rolename USUARIO

echo "Cliente técnico y roles de Keycloak configurados."
