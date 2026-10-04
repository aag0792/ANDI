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


def test_quote_commercial_fields_softland_and_history(client, tmp_path):
    profile = {'NOMBRE': 'BARLY de Softland', 'DIRECCION': 'Heredia',
               'TELEFONO1': '00000000', 'E_MAIL': 'cliente@example.test'}
    with patch.object(main.db, 'call_procedure_sets', return_value=[[profile], [], []]) as call, patch.object(main.db, 'audit'), patch.object(main, 'save_quote_history', side_effect=lambda r:r) as history:
        result = tool_result(rpc(client, 'tools/call', {'name':'generar_cotizacion','arguments':{
            'project_name':'Consultoría', 'client_name':'Barly', 'description':'ERP',
            'codigo_cliente':'C001', 'currency':'USD', 'tax_rate':.13,
            'lines':[{'quantity':2,'description':'ERP','unit_price':60}],
            'quote_number':'P02435','quote_date':'2026-09-16',
            'output_path':str(tmp_path/'mcp.pdf')}}))
        assert result['final_cost'] == 135.60
        assert result['quotation']['client'] == profile
        assert result['client_name'] == profile['NOMBRE']
        assert result['pdf']['quotation']['total'] == result['final_cost']
        assert history.call_args.args[0]['final_cost'] == 135.60
        call.assert_called_once_with('andi.sp_cliente_360', 'C001')


def test_legacy_quote_pdf_and_history_agree(client,tmp_path):
    with patch.object(main, 'save_quote_history', side_effect=lambda r:r) as history:
        result = tool_result(rpc(client,'tools/call',{'name':'generar_cotizacion','arguments':{
            'project_name':'Proyecto', 'client_name':'Cliente', 'description':'Software',
            'discount_percent':.1,'margin_percent':.2,'output_path':str(tmp_path/'legacy.pdf')}}))
        assert result['final_cost'] == result['pdf']['quotation']['total']
        assert result['quotation']['discount_amount'] > 0
        assert history.call_args.args[0]['final_cost'] == result['final_cost']


def test_quote_invalid_data_does_not_save(client,tmp_path):
    with patch.object(main,'save_quote_history') as history:
        result=tool_result(rpc(client,'tools/call',{'name':'generar_cotizacion','arguments':{
            'project_name':'Proyecto','client_name':'Cliente','description':'ERP',
            'lines':[],'output_path':str(tmp_path/'invalid.pdf')}}))
        assert 'error' in result
        history.assert_not_called()
        assert not (tmp_path/'invalid.pdf').exists()
