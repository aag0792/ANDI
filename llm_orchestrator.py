"""LLM orchestrator for ANDI v0.2.

The model decides which safe Gateway tool to request. It never receives arbitrary
SQL execution or external-message sending capabilities.
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import requests

import config

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]

SYSTEM_PROMPT = """Eres ANDI, asistente interno de Andrés y AND.
Tu función es comprender lenguaje natural y usar herramientas del Gateway cuando sean necesarias.

Reglas:
- Nunca inventes clientes, cotizaciones, datos de SQL, reuniones ni resultados de herramientas.
- Si necesitas datos de Softland, usa buscar_cliente.
- Si hay varias coincidencias de cliente, muéstralas y pide selección; no elijas arbitrariamente.
- Si faltan datos esenciales para una estimación/cotización, pregunta antes de crearla.
- Una estimación es preliminar; no la presentes como compromiso comercial confirmado.
- Puedes preparar borradores de correo, pero nunca enviar comunicaciones a clientes o compañeros.
- No existe una herramienta de SQL libre. No solicites ni construyas SQL para ejecución.
- Responde en español claro y natural.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_cliente",
            "description": "Busca clientes reales en Softland por nombre, alias o código.",
            "parameters": {
                "type": "object",
                "properties": {"termino": {"type": "string"}},
                "required": ["termino"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_estimacion_proyecto",
            "description": "Crea una estimación preliminar cuando ya hay suficiente alcance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "client_name": {"type": "string"},
                    "description": {"type": "string"},
                    "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "modules": {"type": "array", "items": {"type": "string"}},
                    "integrations": {"type": "integer", "minimum": 0},
                    "users": {"type": "integer", "minimum": 1},
                    "localization": {"type": "boolean"},
                },
                "required": ["project_name", "client_name", "description"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumir_reunion",
            "description": "Resume notas o una transcripción de reunión.",
            "parameters": {
                "type": "object",
                "properties": {"notes": {"type": "string"}},
                "required": ["notes"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_cotizaciones",
            "description": "Consulta el historial local de cotizaciones de ANDI.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 25}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preparar_email_cotizacion",
            "description": "Prepara un borrador de email. NO lo envía.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "client_email": {"type": "string"},
                    "proposal_pdf_path": {"type": "string"},
                },
                "required": ["project_name", "client_email", "proposal_pdf_path"],
                "additionalProperties": False,
            },
        },
    },
]


def _chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY no está configurada.")
    payload: dict[str, Any] = {
        "model": config.OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    response = requests.post(
        f"{config.OPENAI_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]


async def run_agent(message: str, handlers: dict[str, ToolHandler]) -> dict[str, Any]:
    """Run a bounded tool-calling loop and return a natural-language response."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    trace: list[dict[str, Any]] = []

    for _ in range(5):
        assistant = _chat(messages, TOOLS)
        messages.append(assistant)
        calls = assistant.get("tool_calls") or []
        if not calls:
            return {"message": assistant.get("content") or "No pude completar la respuesta.", "tool_trace": trace}

        for call in calls:
            fn = call.get("function") or {}
            name = fn.get("name")
            handler = handlers.get(name)
            if handler is None:
                result = {"error": f"Herramienta no permitida: {name}"}
            else:
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                    result = await handler(**args)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    result = {"error": f"Argumentos inválidos para {name}: {type(exc).__name__}"}
                except Exception as exc:
                    result = {"error": f"No se pudo ejecutar {name}: {type(exc).__name__}"}

            trace.append({"tool": name, "ok": "error" not in result})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id"),
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return {"message": "Necesito más contexto para completar la solicitud con seguridad.", "tool_trace": trace}
