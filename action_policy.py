"""Central action policy for ANDI.

The LLM may choose tools, but this module decides whether a requested capability
is executable without a human approval.
"""
from __future__ import annotations

TOOL_POLICY = {
    "buscar_cliente": "read",
    "crear_estimacion_proyecto": "prepare",
    "crear_cronograma_proyecto": "prepare",
    "listar_cotizaciones": "read",
    "obtener_cotizacion": "read",
    "resumir_reunion": "prepare",
    "preparar_email_cotizacion": "prepare",
    "generar_cotizacion": "prepare",
}

AUTO_ALLOWED = {"read", "prepare"}


def classify_tool(name: str) -> str:
    return TOOL_POLICY.get(name, "forbidden")


def can_execute(name: str) -> bool:
    return classify_tool(name) in AUTO_ALLOWED


def decision(name: str) -> dict:
    level = classify_tool(name)
    if level == "forbidden":
        return {"allowed": False, "classification": level, "reason": "Herramienta no autorizada."}
    if level == "external_action":
        return {
            "allowed": False,
            "classification": level,
            "requires_approval": True,
            "reason": "Las acciones que hablan por Andrés con terceros requieren aprobación explícita.",
        }
    return {"allowed": True, "classification": level, "requires_approval": False}
