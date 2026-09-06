"""Genera documentación automática HTML con pdoc para los módulos del proyecto.

Uso (entorno oficial, dentro del contenedor web):

    python scripts/generate_docs.py

Requisitos:
    - pdoc instalado (ver requirements.txt).
    - Variables cargadas desde .env (load_dotenv en config.settings).
    - No requiere PostgreSQL ni Keycloak para importar los módulos.

Salida:
    docs/generated/ (index.html + un archivo HTML por módulo).
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import pdoc  # noqa: E402

MODULOS = [
    "usuarios.models",
    "usuarios.views",
    "usuarios.urls",
    "usuarios.api_urls",
    "usuarios.decorators",
    "usuarios.context_processors",
    "usuarios.keycloak",
    "usuarios.services",
    "clientes.models",
    "clientes.views",
    "clientes.urls",
    "clientes.api_urls",
    "monedas.models",
    "monedas.views",
    "monedas.urls",
    "metodos_pago.models",
    "metodos_pago.views",
    "metodos_pago.urls",
    "tasas.models",
    "tasas.views",
    "tasas.urls",
    "tasas.services",
    "tasas.providers",
    "tasas.simulador",
    "config.settings",
    "config.urls",
]

OUTPUT_DIR = BASE_DIR / "docs" / "generated"


def main():
    pdoc.pdoc(*MODULOS, output_directory=OUTPUT_DIR)
    print(f"Documentación generada en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()