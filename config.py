"""Configuración del Gateway. Todo sale de variables de entorno.

Acepta tanto .env como conexion.env para no romper el flujo de trabajo
actual del proyecto.
"""
import os
from dotenv import load_dotenv

for _candidate in (
    os.path.join(os.path.dirname(__file__), ".env"),
    os.path.join(os.path.dirname(__file__), "conexion.env"),
    ".env",
    "conexion.env",
):
    if os.path.exists(_candidate):
        load_dotenv(_candidate)
        break


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


# --- SQL Server ---
SQL_SERVER = os.getenv("SQL_SERVER", "localhost")
SQL_DATABASE = _required("SQL_DATABASE")
SQL_USER = _required("SQL_USER")
SQL_PASSWORD = _required("SQL_PASSWORD")
SQL_DRIVER = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")

# --- Gateway ---
# Token que deben enviar los clientes en: Authorization: Bearer <token>
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")  # legado, no se acepta en modo Entra
HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")   # solo local por defecto
PORT = int(os.getenv("GATEWAY_PORT", "8000"))
LOG_DIR = os.getenv("LOG_DIR", r"C:\ANDI\logs")

# --- OpenAI (opcional) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# --- Microsoft Entra ID ---
GATEWAY_AUTH_MODE = os.getenv("GATEWAY_AUTH_MODE", "entra").strip().lower()
if GATEWAY_AUTH_MODE != "entra":
    raise RuntimeError("Esta versión requiere GATEWAY_AUTH_MODE=entra")
ENTRA_TENANT_ID = _required("ENTRA_TENANT_ID").strip()
ENTRA_CLIENT_ID = _required("ENTRA_CLIENT_ID").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://andi.and.cr").rstrip("/")
# Si PUBLIC_BASE_URL incluye /mcp, se normaliza al origen público.
if PUBLIC_BASE_URL.endswith("/mcp"):
    PUBLIC_BASE_URL = PUBLIC_BASE_URL[:-4]
ENTRA_AUDIENCE_V1 = os.getenv("ENTRA_AUDIENCE_V1", PUBLIC_BASE_URL + "/mcp").strip()
ENTRA_REQUIRED_SCOPE = os.getenv("ENTRA_REQUIRED_SCOPE", "andi.access").strip()
if not ENTRA_REQUIRED_SCOPE or "/" in ENTRA_REQUIRED_SCOPE:
    raise RuntimeError("ENTRA_REQUIRED_SCOPE debe ser el nombre corto, por ejemplo andi.access")

def _allowed(plural, singular):
    value = os.getenv(plural, os.getenv(singular, ""))
    return {v.strip().lower() for v in value.replace(";", ",").split(",") if v.strip()}

ENTRA_ALLOWED_USERS = _allowed("ENTRA_ALLOWED_USERS", "ENTRA_ALLOWED_USER")
ENTRA_ALLOWED_CLIENTS = _allowed("ENTRA_ALLOWED_CLIENTS", "ENTRA_ALLOWED_CLIENT")
