import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProductionSettingsTests(SimpleTestCase):
    maxDiff = None

    def _load_settings(self, **overrides):
        environment = os.environ.copy()
        environment.update(
            {
                "DJANGO_ENVIRONMENT": "production",
                "DJANGO_SECRET_KEY": "test-only-production-secret",
                "DJANGO_DEBUG": "false",
                "DJANGO_ALLOWED_HOSTS": "app.example.test",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.test",
                "KEYCLOAK_PUBLIC_URL": "https://auth.example.test",
                "KEYCLOAK_INTERNAL_URL": "http://keycloak:8080",
                "BACKEND_PUBLIC_URL": "https://app.example.test",
                "OIDC_CALLBACK_URL": "https://app.example.test/callback/",
                "SESSION_COOKIE_SECURE": "true",
                "CSRF_COOKIE_SECURE": "true",
                "DJANGO_SECURE_SSL_REDIRECT": "true",
                "DJANGO_SECURE_HSTS_SECONDS": "31536000",
                "DJANGO_BEHIND_HTTPS_PROXY": "true",
            }
        )
        environment.update(overrides)
        code = """
import json
from config import settings
print(json.dumps({
    "debug": settings.DEBUG,
    "allowed_hosts": settings.ALLOWED_HOSTS,
    "csrf_origins": getattr(settings, "CSRF_TRUSTED_ORIGINS", []),
    "proxy_header": getattr(settings, "SECURE_PROXY_SSL_HEADER", None),
    "forwarded_host": getattr(settings, "USE_X_FORWARDED_HOST", False),
    "ssl_redirect": getattr(settings, "SECURE_SSL_REDIRECT", False),
    "hsts": getattr(settings, "SECURE_HSTS_SECONDS", 0),
    "session_secure": settings.SESSION_COOKIE_SECURE,
    "csrf_secure": settings.CSRF_COOKIE_SECURE,
    "keycloak_public": settings.KEYCLOAK_PUBLIC_URL,
    "keycloak_internal": settings.KEYCLOAK_INTERNAL_URL,
    "mailer": settings.MAILERS,
    "from_email": settings.DEFAULT_FROM_EMAIL,
}))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        return result

    def test_https_proxy_settings_are_explicit_and_consistent(self):
        result = self._load_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertFalse(values["debug"])
        self.assertEqual(values["allowed_hosts"], ["app.example.test"])
        self.assertEqual(values["csrf_origins"], ["https://app.example.test"])
        self.assertEqual(
            values["proxy_header"],
            ["HTTP_X_FORWARDED_PROTO", "https"],
        )
        self.assertFalse(values["forwarded_host"])
        self.assertTrue(values["ssl_redirect"])
        self.assertEqual(values["hsts"], 31536000)
        self.assertTrue(values["session_secure"])
        self.assertTrue(values["csrf_secure"])
        self.assertEqual(values["keycloak_public"], "https://auth.example.test")
        self.assertEqual(values["keycloak_internal"], "http://keycloak:8080")

    def test_http_mode_does_not_trust_https_forwarding(self):
        result = self._load_settings(
            DJANGO_BEHIND_HTTPS_PROXY="false",
            DJANGO_SECURE_SSL_REDIRECT="false",
            DJANGO_SECURE_HSTS_SECONDS="0",
            SESSION_COOKIE_SECURE="false",
            CSRF_COOKIE_SECURE="false",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertIsNone(values["proxy_header"])
        self.assertFalse(values["ssl_redirect"])
        self.assertEqual(values["hsts"], 0)
        self.assertFalse(values["session_secure"])
        self.assertFalse(values["csrf_secure"])

    def test_correo_desarrollo_mailpit_y_produccion_conserva_variables(self):
        """Django desarrollo usa Mailpit sin TLS/auth; producción conserva SMTP y remitente configurados."""
        resultado = self._load_settings(DJANGO_ENVIRONMENT="development")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        valores = json.loads(resultado.stdout)
        self.assertEqual(valores["mailer"]["default"], {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "mailpit", "port": 1025, "username": "", "password": "",
                        "use_tls": False, "use_ssl": False, "timeout": 8},
        })
        resultado = self._load_settings(EMAIL_HOST="smtp.example.test", EMAIL_PORT="587", EMAIL_USE_TLS="true",
                                        DEFAULT_FROM_EMAIL="tasas@example.test")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        valores = json.loads(resultado.stdout)
        self.assertEqual(valores["mailer"]["default"]["OPTIONS"],
                         {"host": "smtp.example.test", "port": 587, "use_tls": True, "timeout": 8})
        self.assertEqual(valores["from_email"], "tasas@example.test")

    def test_production_rejects_default_secret(self):
        result = self._load_settings(DJANGO_SECRET_KEY="django-dev-only-change-me")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_production_example_contains_no_loopback_urls(self):
        example = (PROJECT_ROOT / ".env.production.example").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("localhost", example)
        self.assertNotIn("127.0.0.1", example)
        self.assertIn("DJANGO_BEHIND_HTTPS_PROXY", example)
        self.assertIn("KEYCLOAK_PUBLIC_URL", example)

    def test_realm_bootstrap_is_sanitized_and_importable(self):
        realm_text = (
            PROJECT_ROOT / "keycloak" / "global-exchange-realm.json"
        ).read_text(encoding="utf-8")
        realm = json.loads(realm_text)
        role_names = {role["name"] for role in realm["roles"]["realm"]}
        self.assertTrue(
            {"USUARIO", "CAJERO", "ANALISTA_CAMBIARIO", "ADMINISTRADOR"}
            <= role_names
        )
        self.assertNotIn('"secret"', realm_text)
        self.assertNotIn("localhost", realm_text)
        self.assertNotIn("127.0.0.1", realm_text)

        web_client = next(
            client
            for client in realm["clients"]
            if client["clientId"] == "global-exchange-web"
        )
        self.assertTrue(web_client["publicClient"])
        self.assertTrue(web_client["standardFlowEnabled"])
        self.assertEqual(
            web_client["attributes"]["pkce.code.challenge.method"],
            "S256",
        )
