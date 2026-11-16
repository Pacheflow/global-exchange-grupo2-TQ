#!/usr/bin/env python3
"""Valida despliegue sin modificar servicios y registra evidencia sin secretos.

Modo estático: sintaxis bash y configuración Compose. --runtime agrega salud,
revisión de imagen y comprobaciones Django; debe ejecutarse en la VM desplegada.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def run(args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=120)


def validate(env_file, compose_file, runtime=False):
    evidence = {"fecha_utc": datetime.now(timezone.utc).isoformat(),
                "modo": "runtime" if runtime else "estatico", "checks": []}

    def check(name, args, predicate=None):
        try:
            result = run(args)
            ok = result.returncode == 0
            if ok and predicate:
                ok = bool(predicate(result.stdout))
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
            ok = False
        # No persistir stdout/stderr: config y errores pueden contener secretos.
        evidence["checks"].append({"nombre": name, "ok": ok})
        return ok

    revision = run(["git", "rev-parse", "HEAD"])
    evidence["commit"] = revision.stdout.strip() if revision.returncode == 0 else None
    compose = ["docker", "compose", "--env-file", str(env_file), "-f", str(compose_file)]
    check("sintaxis_script", ["bash", "-n", "scripts/deploy-production.sh"])
    config_ok = check("compose_valido", compose + ["config", "--quiet"])
    if runtime and config_ok:
        for service in ("postgres", "keycloak", "web", "nginx"):
            try:
                result = run(compose + ["ps", "-q", service])
                container_id = result.stdout.strip()
                if result.returncode or not container_id:
                    raise ValueError
                check("salud_" + service,
                      ["docker", "inspect", "--format",
                       '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}', container_id],
                      lambda output: output.strip() == "running healthy")
                if service == "web":
                    check("imagen_commit", ["docker", "inspect", "--format",
                          '{{index .Config.Labels "org.opencontainers.image.revision"}}', container_id],
                          lambda output: bool(evidence["commit"]) and output.strip() == evidence["commit"])
            except (OSError, subprocess.TimeoutExpired, ValueError):
                evidence["checks"].append({"nombre": "salud_" + service, "ok": False})
        for name, command in (
            ("migraciones_aplicadas", ["python", "manage.py", "migrate", "--check"]),
            ("django_deploy", ["python", "manage.py", "check", "--deploy", "--fail-level", "WARNING"]),
        ):
            check(name, compose + ["exec", "-T", "web"] + command)
        check("nginx_http", compose + ["exec", "-T", "nginx", "wget", "-qO-",
              "http://127.0.0.1:8080/nginx-health"], lambda output: output.strip() == "ok")
    evidence["ok"] = all(item["ok"] for item in evidence["checks"])
    evidence["validacion_productiva_completa"] = runtime and config_ok and evidence["ok"]
    return evidence


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.project_dir.resolve()
    evidence = validate(args.env_file or ROOT / ".env.production",
                        args.compose_file or ROOT / "compose.prod.yaml", args.runtime)
    # Creación exclusiva: evita sobrescribir evidencia o seguir enlaces existentes.
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as target:
        json.dump(evidence, target, indent=2, ensure_ascii=False)
        target.write("\n")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
