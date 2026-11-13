"""Fluxo real Flask/comparador/fórmula, com modelos e Supabase simulados."""
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_web_filters as web
from test_pdf_upload import make_sample_pdf
from app import app
from app.analysis import AnalysisError, load_models


class FakeEmbedder:
    def encode(self, inputs):
        return {'records': [dict(item, input_index=i, chunk_index=0)
                            for i, item in enumerate(inputs)],
                'embeddings': [[1., 0.] if 'Python' in item['text'] else [0., 1.]
                               for item in inputs]}


class AnalysisWebTests(unittest.TestCase):
    setUp = web.WebFiltersTestCase.setUp
    tearDown = web.WebFiltersTestCase.tearDown
    post = web.WebFiltersTestCase.post
    login = web.WebFiltersTestCase.login

    def prepare(self):
        self.login()
        self.post('/nova-vaga', {
            'title': 'Python developer', 'description': 'Build APIs',
            'req_id': [''], 'req_text': ['Python'], 'req_tipo': ['tecnico'],
            'req_nivel': ['obrigatorio'],
        })
        def predict(**kw):
            text = kw['text']
            return {'entities': [dict(label=label, text=value, start=text.index(value),
                                      end=text.index(value) + len(value), confidence=.9)
                                 for label, value in [('NAME', 'Jane Smith'), ('SKILLS', 'Python')]
                                 if value in text]}
        self.predictor = SimpleNamespace(predict=predict)
        self.models = patch('app.analysis.load_models', return_value=(self.predictor, FakeEmbedder()))
        self.models.start()
        self.addCleanup(self.models.stop)

    def upload(self, name='jane.pdf', skill='Python'):
        return self.client.post('/vagas/1/adicionar-curriculos', data={
            'files': (io.BytesIO(make_sample_pdf([
                'Jane Smith', 'jane@example.test', 'SKILLS', skill,
                'EXPERIENCE', '- Built APIs using ' + skill,
            ])), name)}, content_type='multipart/form-data', headers={'Origin': 'http://localhost'})

    def select(self, ids=('1',)):
        return self.post('/vagas/1/adicionar-curriculos', {'selected_candidates': list(ids)})

    def test_new_upload_persistence_recovery_and_no_duplicate(self):
        self.prepare()
        self.assertEqual(self.upload().status_code, 302)
        self.assertEqual(self.db['analyses'][0]['result']['score'], 100)
        self.upload()
        self.assertEqual(len(self.db['resumes']), 1)
        self.assertEqual(len(self.db['analyses']), 1)
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('100.00/100', page)
        self.assertIn('Cosseno: 1.0000', page)
        self.assertNotIn('Alta aderência', page)

    def test_existing_resume_and_manual_decision(self):
        self.prepare(); self.upload()
        self.post('/vagas/1/candidato/1/status', {'status': 'Aprovado'})
        self.select()
        self.assertEqual(len(self.db['resumes']), 1)
        self.assertEqual(self.db['resumes'][0]['status'], 'Aprovado')
        self.assertEqual(len(self.db['analyses']), 1)

    def test_old_privacy_pipeline_is_reprocessed_without_duplicate_resume(self):
        from app.analysis import configuration, fingerprint
        self.prepare(); self.upload()
        old = self.db['analyses'][0]
        old['config_hash'] = fingerprint(dict(configuration(), pipeline_version='web-1'))
        old['pipeline_version'] = 'web-1'
        old['result']['score'] = 45.99
        self.assertIn('Desatualizada', self.client.get('/vagas/1').data.decode())
        self.select()
        self.assertEqual(len(self.db['resumes']), 1)
        self.assertEqual(len(self.db['analyses']), 2)
        self.assertEqual(old['result']['score'], 45.99)
        self.assertNotIn('Desatualizada', self.client.get('/vagas/1').data.decode())

    def test_pending_requirements_no_models_and_no_fake_score(self):
        self.prepare()
        self.db['jobs'][0]['requisitos'] = 'Python'
        with patch('app.analysis.load_models') as models:
            self.upload()
            models.assert_not_called()
        self.assertFalse(self.db.get('analyses'))
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('Pendente', page)
        self.assertNotIn('80%', page)

    def test_model_unavailable_clear_failure(self):
        self.prepare()
        with patch('app.analysis.load_models', side_effect=AnalysisError('Modelo indisponível')):
            self.upload()
        self.assertFalse(self.db.get('analyses'))
        self.assertIn('Modelo indisponível', self.client.get('/vagas/1').data.decode())

    def test_missing_model_path_fails_without_loading(self):
        with self.assertRaisesRegex(AnalysisError, 'indisponível'):
            load_models('path-that-does-not-exist', 'unused')

    def test_failure_in_batch_does_not_stop_other_resume(self):
        self.prepare(); self.upload(); self.upload('other.pdf', 'SQL')
        self.db['analyses'].clear()
        from app.analysis import process_resume
        def process(client, job, resume):
            if resume['id'] == '1':
                raise AnalysisError('Falha individual')
            return process_resume(client, job, resume)
        with patch('app.routes.process_resume', side_effect=process):
            self.select(('1', '2'))
        self.assertEqual([r['curriculo_id'] for r in self.db['analyses']], [2])
        self.assertIn('Falha individual', self.client.get('/vagas/1').data.decode())

    def test_stale_requirements_and_text_excluded_from_dashboard(self):
        self.prepare(); self.upload()
        self.db['jobs'][0]['requisitos'] = self.db['jobs'][0]['requisitos'].replace('Python', 'SQL')
        self.assertIn('Desatualizada', self.client.get('/vagas/1').data.decode())
        self.assertIn('Indisponível', self.client.get('/').data.decode())
        self.select()
        self.assertEqual(len(self.db['analyses']), 2)
        self.db['resumes'][0]['texto_extraido'] += '\nNew project'
        self.assertIn('Desatualizada', self.client.get('/vagas/1').data.decode())

    def test_other_owner_cannot_read_or_process(self):
        self.prepare(); self.upload()
        other = app.test_client()
        self.login(other, 'bia@example.test', 'password2')
        self.assertEqual(other.get('/vagas/1/candidato/1').status_code, 404)
        self.assertEqual(self.post('/vagas/1/adicionar-curriculos', {'selected_candidates': ['1']}, other).status_code, 404)

    def test_sort_decimals_and_pending_last(self):
        self.prepare(); self.upload(); self.upload('other.pdf', 'SQL'); self.upload('third.pdf', 'Docker')
        self.db['analyses'][0]['result']['score'] = 70.01
        self.db['analyses'][1]['result']['score'] = 70.99
        self.db['analyses'].pop()
        page = self.client.get('/vagas/1').data.decode()
        self.assertLess(page.index('data-score="70.99"'), page.index('data-score="70.01"'))
        self.assertLess(page.index('data-score="70.01"'), page.index('data-score=""'))
        self.assertIn("parseFloat(b.getAttribute('data-score'))", page)

    def test_save_failure_never_reports_complete(self):
        self.prepare()
        with patch('app.repositories.save_analysis', side_effect=RuntimeError('Unavailable')):
            self.upload()
        self.assertIn('Pendente', self.client.get('/vagas/1/candidato/1').data.decode())

    def test_missing_migration_returns_503_with_actionable_message(self):
        from app.repositories import AnalysisSchemaError
        self.prepare(); self.upload()
        with patch('app.repositories.list_analyses', side_effect=AnalysisSchemaError(
                'Aplique sql/004_integracao_aderencia.sql antes de usar a integração.')):
            response = self.client.get('/vagas/1/adicionar-curriculos')
        self.assertEqual(response.status_code, 503)
        self.assertIn('004_integracao_aderencia.sql', response.data.decode())

    def test_anonymized_inputs_keep_professional_evidence(self):
        self.prepare()
        captured = []
        class Capture(FakeEmbedder):
            def encode(self, inputs):
                captured.extend(inputs)
                return super().encode(inputs)
        with patch('app.analysis.load_models', return_value=(self.predictor, Capture())):
            self.upload()
        self.assertTrue(any('Python' in item['text'] for item in captured))
        self.assertFalse(any('Jane Smith' in str(item) or 'jane@example.test' in str(item) for item in captured))


if __name__ == '__main__':
    unittest.main()
