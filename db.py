"""Acceso a SQL Server.

Regla de oro: aquí NO existe una función que ejecute SQL libre.
Solo se llama a procedimientos almacenados con parámetros.
"""
import json
import logging
import os
import time
from decimal import Decimal

import pyodbc

try:
    from . import config
except ImportError:  # Ejecutado como `python main.py`
    import config

os.makedirs(config.LOG_DIR, exist_ok=True)

# Log de auditoría: una línea JSON por cada herramienta ejecutada.
# Guarda QUÉ se consultó y cuántas filas salieron, NO los datos devueltos.
_audit = logging.getLogger("andi.audit")
_audit.setLevel(logging.INFO)
if not _audit.handlers:
    _h = logging.FileHandler(os.path.join(config.LOG_DIR, "audit.log"), encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(message)s"))
    _audit.addHandler(_h)


def audit(tool: str, params: dict, rows: int | None, ok: bool, error: str | None = None) -> None:
    _audit.info(json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": tool,
        "params": params,
        "rows": rows,
        "ok": ok,
        "error": error,
    }, ensure_ascii=False))


def _connection_string() -> str:
    return (
        f"DRIVER={{{config.SQL_DRIVER}}};"
        f"SERVER={config.SQL_SERVER};"
        f"DATABASE={config.SQL_DATABASE};"
        f"UID={config.SQL_USER};PWD={config.SQL_PASSWORD};"
        "Encrypt=yes;TrustServerCertificate=yes;"  # conexión local al mismo servidor
        "ApplicationIntent=ReadOnly;"
    )


def _clean(value):
    """Convierte tipos de SQL a tipos JSON-friendly."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def call_procedure(proc: str, *args) -> list[dict]:
    """Ejecuta `EXEC proc ?, ?, ...` y devuelve lista de diccionarios."""
    placeholders = ", ".join("?" for _ in args)
    sql = f"EXEC {proc} {placeholders}".strip()
    with pyodbc.connect(_connection_string(), timeout=5) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, *args)
        if cursor.description is None:
            return []
        cols = [c[0] for c in cursor.description]
        return [{c: _clean(v) for c, v in zip(cols, row)} for row in cursor.fetchall()]


def call_procedure_sets(proc: str, *args) -> list[list[dict]]:
    """Ejecuta un procedimiento y devuelve todos sus result sets tabulares.

    Mantiene la misma restricción de seguridad: no acepta SQL libre, solo el
    nombre de un procedimiento y parámetros posicionales.
    """
    placeholders = ", ".join("?" for _ in args)
    sql = f"EXEC {proc} {placeholders}".strip()
    result_sets: list[list[dict]] = []
    with pyodbc.connect(_connection_string(), timeout=5) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, *args)
        while True:
            if cursor.description is not None:
                cols = [c[0] for c in cursor.description]
                rows = [
                    {c: _clean(v) for c, v in zip(cols, row)}
                    for row in cursor.fetchall()
                ]
                result_sets.append(rows)
            if not cursor.nextset():
                break
    return result_sets
