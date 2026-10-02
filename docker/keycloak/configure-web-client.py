"""Sincroniza idempotentemente el cliente público OIDC mediante Admin REST."""

import json
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SERVER_URL = os.environ.get(
    "KEYCLOAK_INTERNAL_URL",
    "http://keycloak:8080",
).rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "global-exchange")
CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "global-exchange-web")
BACKEND_PUBLIC_URL = os.environ["BACKEND_PUBLIC_URL"].rstrip("/")
OIDC_CALLBACK_URL = os.environ["OIDC_CALLBACK_URL"]


def request_json(method, path, *, token=None, payload=None, form=None):
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"

    try:
        with urlopen(
            Request(
                f"{SERVER_URL}{path}",
                data=data,
                headers=headers,
                method=method,
            ),
            timeout=30,
        ) as response:
            body = response.read()
    except HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(
            f"Keycloak Admin REST devolvió HTTP {error.code}: {detail}"
        ) from error
    return json.loads(body) if body else None


token_response = request_json(
    "POST",
    "/realms/master/protocol/openid-connect/token",
    form={
        "client_id": "admin-cli",
        "username": os.environ["KEYCLOAK_ADMIN"],
        "password": os.environ["KEYCLOAK_ADMIN_PASSWORD"],
        "grant_type": "password",
    },
)
access_token = token_response["access_token"]
realm_path = f"/admin/realms/{quote(REALM, safe='')}"
query = urlencode({"clientId": CLIENT_ID, "exact": "true"})
clients = request_json(
    "GET",
    f"{realm_path}/clients?{query}",
    token=access_token,
)

if not clients:
    request_json(
        "POST",
        f"{realm_path}/clients",
        token=access_token,
        payload={
            "clientId": CLIENT_ID,
            "name": "Global Exchange Web",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": True,
        },
    )
    clients = request_json(
        "GET",
        f"{realm_path}/clients?{query}",
        token=access_token,
    )

client_uuid = clients[0]["id"]
client = request_json(
    "GET",
    f"{realm_path}/clients/{client_uuid}",
    token=access_token,
)
client.update(
    {
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": True,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "rootUrl": BACKEND_PUBLIC_URL,
        "baseUrl": f"{BACKEND_PUBLIC_URL}/",
        "adminUrl": BACKEND_PUBLIC_URL,
        "redirectUris": [OIDC_CALLBACK_URL],
        "webOrigins": [BACKEND_PUBLIC_URL],
    }
)
client.pop("secret", None)
attributes = client.setdefault("attributes", {})
attributes.update(
    {
        "post.logout.redirect.uris": f"{BACKEND_PUBLIC_URL}/*",
        "pkce.code.challenge.method": "S256",
    }
)
request_json(
    "PUT",
    f"{realm_path}/clients/{client_uuid}",
    token=access_token,
    payload=client,
)
print(f"Cliente público {CLIENT_ID} configurado para {BACKEND_PUBLIC_URL}.")
