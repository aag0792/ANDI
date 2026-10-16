"""Pruebas aisladas de resultados ODBC; no abren conexiones SQL."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

class ProcedureResultsTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = SimpleNamespace(LOG_DIR=self.tmp.name)
        self.odbc = MagicMock()
        spec = importlib.util.spec_from_file_location('db_results_under_test', Path(__file__).resolve().parents[1] / 'db.py')
        self.db = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'config': config, 'pyodbc': self.odbc}):
            spec.loader.exec_module(self.db)
        self.db._connection_string = lambda: 'test'
        self.cursor = self.odbc.connect.return_value.__enter__.return_value.cursor.return_value
        self.addCleanup(self.close_handler)

    def close_handler(self):
        for handler in self.db._audit.handlers[:]:
            handler.close()
            self.db._audit.removeHandler(handler)

    def test_skips_row_counts_before_select(self):
        self.cursor.description = None
        stages = iter([None, [('CLIENTE',), ('NOMBRE',)]])
        def advance():
            self.cursor.description = next(stages)
            return True
        self.cursor.nextset.side_effect = advance
        self.cursor.fetchall.return_value = [('C0020', 'AGRIBIO  ')]
        self.assertEqual(self.db.call_procedure('andi.sp_listar_clientes', 1, 1, None, None),
                         [{'CLIENTE': 'C0020', 'NOMBRE': 'AGRIBIO'}])
        self.cursor.execute.assert_called_once_with('EXEC andi.sp_listar_clientes ?, ?, ?, ?', 1, 1, None, None)
        self.assertEqual(self.cursor.nextset.call_count, 2)

    def test_direct_select(self):
        self.cursor.description = [('CLIENTE',)]
        self.cursor.fetchall.return_value = [('C0020',)]
        self.assertEqual(self.db.call_procedure('andi.sp_buscar_cliente', 'C0020'), [{'CLIENTE':'C0020'}])
        self.cursor.nextset.assert_not_called()

    def test_empty_select_does_not_advance(self):
        self.cursor.description = [('CLIENTE',)]
        self.cursor.fetchall.return_value = []
        self.assertEqual(self.db.call_procedure('andi.sp_listar_clientes'), [])
        self.cursor.nextset.assert_not_called()

    def test_no_select(self):
        self.cursor.description = None
        self.cursor.nextset.return_value = False
        self.assertEqual(self.db.call_procedure('andi.sp_listar_clientes'), [])
        self.cursor.fetchall.assert_not_called()

    def test_nextset_error_is_not_hidden(self):
        self.cursor.description = None
        self.cursor.nextset.side_effect = RuntimeError('SQL error')
        with self.assertRaisesRegex(RuntimeError, 'SQL error'):
            self.db.call_procedure('andi.sp_listar_clientes')

if __name__ == '__main__':
    main()
