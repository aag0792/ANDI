import asyncio
import json

import llm_orchestrator


def test_agent_calls_allowlisted_tool(monkeypatch):
    replies = iter([
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "buscar_cliente", "arguments": json.dumps({"termino": "Datasys"})},
            }],
        },
        {"role": "assistant", "content": "Encontré dos coincidencias. Indicame cuál querés usar."},
    ])
    monkeypatch.setattr(llm_orchestrator, "_chat", lambda messages, tools=None: next(replies))

    async def buscar_cliente(termino):
        assert termino == "Datasys"
        return {"total": 2, "clientes": [{"codigo": "1"}, {"codigo": "2"}]}

    result = asyncio.run(llm_orchestrator.run_agent("Buscame Datasys", {"buscar_cliente": buscar_cliente}))
    assert result["tool_trace"] == [{"tool": "buscar_cliente", "classification": "read", "ok": True}]
    assert "dos coincidencias" in result["message"].lower()


def test_agent_blocks_non_allowlisted_handler(monkeypatch):
    replies = iter([
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call-2",
                "type": "function",
                "function": {"name": "ejecutar_sql", "arguments": "{}"},
            }],
        },
        {"role": "assistant", "content": "No tengo una herramienta autorizada para ejecutar SQL libre."},
    ])
    monkeypatch.setattr(llm_orchestrator, "_chat", lambda messages, tools=None: next(replies))

    result = asyncio.run(llm_orchestrator.run_agent("Ejecutá SQL libre", {}))
    assert result["tool_trace"] == [{"tool": "ejecutar_sql", "classification": "forbidden", "ok": False}]
    assert "sql libre" in result["message"].lower()


def test_email_tool_is_draft_only():
    names = {item["function"]["name"] for item in llm_orchestrator.TOOLS}
    assert "preparar_email_cotizacion" in names
    assert "enviar_email" not in names


def test_quote_schedule_and_history_tools_are_available():
    names = {item["function"]["name"] for item in llm_orchestrator.TOOLS}
    assert {"crear_cronograma_proyecto", "generar_cotizacion", "obtener_cotizacion"} <= names


def test_external_actions_are_not_exposed():
    names = {item["function"]["name"] for item in llm_orchestrator.TOOLS}
    assert "enviar_email" not in names
    assert "crear_reunion_externa" not in names
