"""Regresiones del endpoint MCP y Cliente 360, sin conexión a Softland."""
import json
from unittest.mock import patch

import pytest

from starlette.testclient import TestClient

import config
import main


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app, base_url="http://127.0.0.1:8000") as client:
        yield client


def rpc(client, method, params=None):
    return client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {config.GATEWAY_TOKEN}",
            "Accept": "application/json, text/event-stream",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        follow_redirects=False,
    )


def tool_result(response):
    result = response.json()["result"]
    assert not result.get("isError", False), result
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def test_mcp_endpoint_auth_and_existing_routes(client):
    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/terms").status_code == 200
    assert client.get("/assets/Andi%20blanco.jpeg").status_code == 200
    for path in ("/assets/.env", "/assets/conexion.env", "/assets/main.py"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={
            "Authorization": f"Bearer {config.GATEWAY_TOKEN}",
        }).status_code == 404
    assert client.post("/mcp", json={}).status_code == 401
    assert client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
    response = rpc(client, "tools/list")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {"cliente_360", "buscar_cliente", "generar_cotizacion"} <= names
    assert client.post(
        "/mcp/mcp", headers={"Authorization": f"Bearer {config.GATEWAY_TOKEN}"}
    ).status_code == 404


def test_cliente_360_over_mcp_preserves_result_and_summary(client):
    sets = [
        [{"CLIENTE": "C0090", "NOMBRE": "Cliente demo"}],
        [{"SALDO_DOLAR": 12.5, "SALDO_LOCAL": 6300}],
        [
            {"FACTURA": "F1", "FECHA": "2026-09-01", "TOTAL_LINEA": 20},
            {"FACTURA": "F1", "FECHA": "2026-09-01", "TOTAL_LINEA": 5},
        ],
    ]
    with patch.object(main.db, "call_procedure_sets", return_value=sets) as call, patch.object(main.db, "audit") as audit:
        response = rpc(client, "tools/call", {"name": "cliente_360", "arguments": {"codigo_cliente": " C0090 "}})
        assert response.status_code == 200
        result = tool_result(response)
        assert result["cliente"] == sets[0][0]
        assert result["cuentas_por_cobrar"] == sets[1]
        assert result["historial_compras"] == sets[2]
        assert result["resumen"] == {
            "saldo_dolar": 12.5, "saldo_local": 6300,
            "documentos_pendientes": 1, "total_facturado_usd": 25,
            "cantidad_facturas": 1, "ultima_compra": "2026-09-01",
        }
        call.assert_called_once_with("andi.sp_cliente_360", "C0090")
        audit.assert_called_once_with("cliente_360", {"codigo_cliente": "C0090"}, 4, True)


def test_cliente_360_invalid_missing_and_database_error(client):
    with patch.object(main.db, "call_procedure_sets", return_value=[[], [], []]) as call, patch.object(main.db, "audit"):
        invalid = rpc(client, "tools/call", {"name": "cliente_360", "arguments": {"codigo_cliente": ""}})
        assert "error" in tool_result(invalid)
        call.assert_not_called()
        missing = rpc(client, "tools/call", {"name": "cliente_360", "arguments": {"codigo_cliente": "unknown"}})
        assert tool_result(missing)["codigo_cliente"] == "unknown"
        call.side_effect = RuntimeError("private database detail")
        failed = rpc(client, "tools/call", {"name": "cliente_360", "arguments": {"codigo_cliente": "C0090"}})
        assert "error" in tool_result(failed)
        assert "private database detail" not in failed.text
