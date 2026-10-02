#!/bin/sh
set -eu

: "${NGINX_APP_HOST:?NGINX_APP_HOST es obligatorio}"
: "${NGINX_KEYCLOAK_HOST:?NGINX_KEYCLOAK_HOST es obligatorio}"

export NGINX_PUBLIC_HTTP_PORT=${NGINX_PUBLIC_HTTP_PORT:-80}
export NGINX_PUBLIC_HTTPS_PORT=${NGINX_PUBLIC_HTTPS_PORT:-443}
export NGINX_KEYCLOAK_PUBLIC_PORT=${NGINX_KEYCLOAK_PUBLIC_PORT:-8080}

case "${NGINX_TLS_ENABLED:-false}" in
  1|true|TRUE|yes|YES)
    template=/etc/nginx/global-exchange-templates/https.conf.template
    test -s /etc/nginx/certs/fullchain.pem || {
      echo "Falta /etc/nginx/certs/fullchain.pem para HTTPS." >&2
      exit 1
    }
    test -s /etc/nginx/certs/privkey.pem || {
      echo "Falta /etc/nginx/certs/privkey.pem para HTTPS." >&2
      exit 1
    }
    ;;
  0|false|FALSE|no|NO)
    if [ "$NGINX_APP_HOST" = "$NGINX_KEYCLOAK_HOST" ]; then
      template=/etc/nginx/global-exchange-templates/http-single-host.conf.template
    else
      template=/etc/nginx/global-exchange-templates/http.conf.template
    fi
    ;;
  *)
    echo "NGINX_TLS_ENABLED debe ser true o false." >&2
    exit 1
    ;;
esac

envsubst '${NGINX_APP_HOST} ${NGINX_KEYCLOAK_HOST} ${NGINX_PUBLIC_HTTP_PORT} ${NGINX_PUBLIC_HTTPS_PORT} ${NGINX_KEYCLOAK_PUBLIC_PORT}' \
  < "$template" > /etc/nginx/conf.d/default.conf

nginx -t
exec nginx -g 'daemon off;'
