"""Contrato do payload; não substitui execução das CHECKs em PostgreSQL."""
import copy
from datetime import datetime, timedelta
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

os.environ.setdefault('FLASK_SECRET_KEY', 'test-only-secret-not-for-deployment')
from app.repositories import AnalysisSchemaError, list_analyses, save_analysis


class AnalysisPersistenceTests(unittest.TestCase):
    def client(self):
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(data=[{'id': 1}])
        return client

    def test_calculated_preserves_real_score_and_metadata(self):
        client = self.client()
        payload = {'result': {'status': 'calculado', 'score': 73.456789},
                   'requirements_hash': 'req', 'text_hash': 'text', 'config_hash': 'config'}
        before = copy.deepcopy(payload)
        save_analysis(client, '5', '7', payload)
        values = client.table.return_value.upsert.call_args.args[0]
        self.assertEqual(values['pontuacao_aderencia'], 73.456789)
        self.assertEqual(values['pontuacao_aderencia'], values['result']['score'])
        self.assertEqual((values['vaga_id'], values['curriculo_id']), (5, 7))
        self.assertEqual(values['requirements_hash'], 'req')
        self.assertIn('analisado_em', values)
        self.assertEqual(payload, before)

    def test_incomplete_sends_explicit_null_in_both_fields(self):
        client = self.client()
        save_analysis(client, 5, 7, {'result': {'status': 'analise_incompleta', 'score': None}})
        values = client.table.return_value.upsert.call_args.args[0]
        self.assertIn('pontuacao_aderencia', values)
        self.assertIsNone(values['pontuacao_aderencia'])
        self.assertIsNone(values['result']['score'])

    def test_rejects_missing_status_or_score_and_non_object_before_write(self):
        for result in [{}, {'score': 20}, {'status': 'calculado'},
                       {'status': 'analise_incompleta'}, None, [], 'calculado']:
            with self.subTest(result=result):
                client = self.client()
                with self.assertRaises(ValueError):
                    save_analysis(client, 5, 7, {'result': result})
                client.table.assert_not_called()

    def test_status_and_score_must_agree(self):
        for status, score in [('calculado', None), ('calculado', '20'),
                              ('calculado', True), ('calculado', -1),
                              ('calculado', 101), ('calculado', float('nan')),
                              ('calculado', float('inf')), ('analise_incompleta', 0),
                              ('analise_incompleta', 'null'), ('unknown', 20), (None, None)]:
            with self.subTest(status=status, score=score):
                client = self.client()
                with self.assertRaises(ValueError):
                    save_analysis(client, 5, 7, {'result': {'status': status, 'score': score}})
                client.table.assert_not_called()

    def test_zero_is_valid_only_when_calculated_and_not_a_fallback(self):
        for score in [0, 100]:
            client = self.client()
            save_analysis(client, 5, 7, {'result': {'status': 'calculado', 'score': score}})
            self.assertEqual(client.table.return_value.upsert.call_args.args[0]['pontuacao_aderencia'], score)

    def test_missing_schema_has_clear_error_without_empty_fallback(self):
        class MissingColumn(Exception):
            code = '42703'
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.side_effect = MissingColumn()
        with self.assertRaisesRegex(AnalysisSchemaError, '004_integracao_aderencia.sql'):
            list_analyses(client, 5)

    def test_other_database_errors_are_not_hidden_as_schema_errors(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.side_effect = RuntimeError('offline')
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            list_analyses(client, 5)

    def test_write_date_is_explicit_utc_iso_for_both_column_types(self):
        client = self.client()
        save_analysis(client, 5, 7, {'result': {'status': 'calculado', 'score': 42}})
        sent = client.table.return_value.upsert.call_args.args[0]['analisado_em']
        parsed = datetime.fromisoformat(sent)
        self.assertEqual(parsed.utcoffset(), timedelta(0))
        # O payload não depende do tipo remoto; não converte datas preexistentes.
        self.assertIsInstance(sent, str)

    def test_read_keeps_timestamp_and_timestamptz_without_assigning_timezone(self):
        for date in ['2026-11-12T20:00:00', '2026-11-12T23:00:00+00:00',
                     '2026-11-12T20:00:00-03:00', None]:
            with self.subTest(date=date):
                client = MagicMock()
                rows = [{'id': 1, 'analisado_em': date}]
                query = client.table.return_value.select.return_value.eq.return_value
                query.order.return_value.execute.return_value = SimpleNamespace(data=rows)
                self.assertEqual(list_analyses(client, 5), rows)
                query.order.assert_called_once_with('analisado_em', desc=True)
