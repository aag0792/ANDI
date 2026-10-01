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
GATEWAY_TOKEN = _required("GATEWAY_TOKEN")
HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")   # solo local por defecto
PORT = int(os.getenv("GATEWAY_PORT", "8000"))
LOG_DIR = os.getenv("LOG_DIR", r"C:\ANDI\logs")

# --- OpenAI (opcional) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
