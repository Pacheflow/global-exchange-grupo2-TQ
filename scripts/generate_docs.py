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

# La documentación debe ser reproducible sin incorporar credenciales del
# entorno que ejecuta pdoc. Estos valores existen únicamente en este proceso.
for variable in (
    "DJANGO_SECRET_KEY",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "KEYCLOAK_ADMIN_CLIENT_SECRET",
    "TASAS_PROVIDER_API_KEY",
):
    os.environ[variable] = f"[REDACTED_{variable}]"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import pdoc  # noqa: E402

pdoc.render.configure(show_source=False)

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
    "clientes.forms",
    "monedas.models",
    "monedas.views",
    "monedas.urls",
    "monedas.forms",
    "metodos_pago.models",
    "metodos_pago.views",
    "metodos_pago.urls",
    "metodos_pago.forms",
    "tasas.models",
    "tasas.views",
    "tasas.urls",
    "tasas.services",
    "tasas.providers",
    "tasas.simulador",
    "operaciones.models",
    "operaciones.views",
    "operaciones.urls",
    "operaciones.services",
    "clientes.tests",
    "monedas.tests",
    "metodos_pago.tests",
    "tasas.tests",
    "tasas.test_reference_rates",
    "tasas.test_simulator",
    "usuarios.tests",
    "config.settings",
    "config.urls",
]

OUTPUT_DIR = BASE_DIR / "docs" / "generated"


def normalizar_salida_generada():
    """Elimina espacios finales introducidos por las plantillas de pdoc.

    Recorre de forma recursiva todos los archivos generados en
    ``OUTPUT_DIR`` y reescribe el contenido sin espacios en blanco al
    final de cada línea, preservando el salto de línea final.

    Returns:
        None: La función solo modifica archivos en el directorio de salida.

    Side effects:
        Reescribe (en modo texto UTF-8) cada archivo HTML generado por pdoc
        dentro de ``docs/generated/``.
    """
    for archivo in OUTPUT_DIR.rglob("*"):
        if not archivo.is_file():
            continue

        contenido = archivo.read_text(encoding="utf-8")
        normalizado = "\n".join(linea.rstrip() for linea in contenido.splitlines())
        if contenido.endswith(("\n", "\r")):
            normalizado += "\n"
        archivo.write_text(normalizado, encoding="utf-8")


def main():
    """Genera la documentación HTML del proyecto con pdoc.

    Escribe la documentación de todos los módulos listados en ``MODULOS``
    dentro de ``OUTPUT_DIR`` y luego normaliza los archivos resultantes.

    Side effects:
        Crea o sobrescribe la documentación en ``docs/generated/``
        (``index.html`` y un archivo HTML por módulo documentado).
    """
    pdoc.pdoc(*MODULOS, output_directory=OUTPUT_DIR)
    normalizar_salida_generada()
    print(f"Documentación generada en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
