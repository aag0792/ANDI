"""Verifica totales de listados y líneas sin acceder a SQL."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, main

spec = importlib.util.spec_from_file_location('softland_totals_under_test', Path(__file__).resolve().parents[1] / 'softland_tools.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Registry:
    def __init__(self):
        self.tools = {}
    def tool(self):
        def decorate(function):
            self.tools[function.__name__] = function
            return function
        return decorate

class TotalsTests(IsolatedAsyncioTestCase):
    async def invoke(self, name, rows, **kwargs):
        registry = Registry()
        db = SimpleNamespace(call_procedure=lambda *args: [dict(row) for row in rows], audit=lambda *args: None)
        module.register(registry, db)
        return await registry.tools[name](**kwargs)

    async def test_invoice_lines_without_count(self):
        result = await self.invoke('factura_lineas', [{'LINEA': 0}, {'LINEA': 1}], tipo_documento='F', factura='test')
        self.assertEqual(result, {'total': 2, 'devueltos': 2, 'datos': [{'LINEA': 0}, {'LINEA': 1}]})

    async def test_order_line_without_count(self):
        result = await self.invoke('pedido_lineas', [{'PEDIDO_LINEA': 1}], pedido='test')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['devueltos'], 1)

    async def test_preserves_paginated_total(self):
        result = await self.invoke('listar_facturas', [{'FACTURA': 'test', '_total_registros': 27}], pagina=2, tamano=1)
        self.assertEqual(result['total'], 27)
        self.assertEqual(result['devueltos'], 1)
        self.assertNotIn('_total_registros', result['datos'][0])

    async def test_empty_results(self):
        result = await self.invoke('pedido_lineas', [], pedido='test')
        self.assertEqual(result, {'total': 0, 'devueltos': 0, 'datos': []})

if __name__ == '__main__':
    main()
