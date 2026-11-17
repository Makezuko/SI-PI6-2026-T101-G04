"""Fluxo real Flask/comparador/fórmula, com modelos e Supabase simulados."""
import io
import json
import os
import copy
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

    def test_existing_resume_embedding_failure_has_trace_and_visible_execution(self):
        self.prepare()
        self.upload()
        before = len(self.db['analyses'])
        class BrokenEvidence(FakeEmbedder):
            def encode(self, inputs):
                if inputs[0]['source'] != 'requirement':
                    raise ValueError('PRIVATE CURRICULUM SECRET')
                return super().encode(inputs)
        with patch.dict(os.environ, {'CONTEXTUAL_EVALUATOR': 'experimental'}), patch(
                'app.analysis.load_models', return_value=(self.predictor, BrokenEvidence())), patch(
                'app.analysis.load_contextual_model') as model, self.assertLogs('talentmatch.analysis') as logs:
            response = self.select()
            run_id = response.headers['X-Analysis-Execution-ID']
            page = self.client.get('/vagas/1').data.decode()
        self.assertEqual(len(self.db['analyses']), before)
        self.assertEqual(len(self.db['resumes']), 1)
        model.assert_not_called()
        self.assertIn(run_id, page)
        self.assertIn('Falha tecnica', page)
        trace = '\n'.join(logs.output)
        self.assertIn('evidence_embeddings', trace)
        self.assertNotIn('PRIVATE CURRICULUM', trace)
        self.assertNotIn('ANALYSIS_SAVED', trace)

    def test_contextual_mode_reaches_adapter_and_displays_method(self):
        self.prepare()
        adapter = SimpleNamespace(generate=lambda payload: json.dumps(dict(
            estado='sustentado', evidence_ids=[payload['evidencias'][0]['id']],
            justificativa='Dublê de integração, sem inferência real.', limitacoes=[], base='evidencia')))
        with patch.dict(os.environ, {'CONTEXTUAL_EVALUATOR': 'experimental'}), patch(
                'app.analysis.load_contextual_model', return_value=adapter):
            self.assertEqual(self.upload().status_code, 302)
            result = self.db['analyses'][0]['result']
            self.assertIn('contextual_configuration', result)
            self.assertEqual(result['details'][0]['diagnostic']['contextual']['estado'], 'sustentado')
            page = self.client.get('/vagas/1/candidato/1').data.decode()
            self.assertIn('Avaliação contextual local', page)

    def test_missing_contextual_model_does_not_save_fake_success(self):
        self.prepare()
        with patch.dict(os.environ, {'CONTEXTUAL_EVALUATOR': 'experimental'}), patch(
                'app.analysis.load_contextual_model', return_value=None):
            self.upload()
            self.assertFalse(self.db.get('analyses', []))

    def test_existing_post_contextual_save_read_screen_and_correlated_trace(self):
        self.prepare()
        self.upload()
        legacy = copy.deepcopy(self.db['analyses'][0])
        adapter = SimpleNamespace(generate=lambda payload: json.dumps(dict(
            estado='sustentado', evidence_ids=[payload['evidencias'][0]['id']],
            justificativa='Dublê de integração.', limitacoes=[], base='evidencia')))
        with patch.dict(os.environ, {'CONTEXTUAL_EVALUATOR': 'experimental'}), patch(
                'app.analysis.load_contextual_model', return_value=adapter), patch(
                'app.analysis.evaluate_requirements', side_effect=AssertionError('Fallback legado proibido')):
            stale = self.client.get('/vagas/1/candidato/1').data.decode()
            self.assertIn('Desatualizada', stale)
            self.assertNotIn('Avaliação por regras legadas', stale)
            form = self.client.get('/vagas/1/adicionar-curriculos').data.decode()
            self.assertIn('name="selected_candidates"', form)
            with self.assertLogs('talentmatch.analysis', level='INFO') as logs:
                self.assertEqual(self.select().status_code, 302)
                page = self.client.get('/vagas/1/candidato/1').data.decode()
            saved = self.db['analyses'][-1]
            self.assertEqual(len(self.db['analyses']), 2)
            self.assertEqual(self.db['analyses'][0], legacy)
            run_id = saved['result']['execution_id']
            self.assertIn(run_id, page)
            self.assertIn('Avaliação contextual local', page)
            events = [json.loads(line[line.index('{'):]) for line in logs.output]
            expected = ['ANALYSIS_POST_START', 'ANALYSIS_EFFECTIVE_CONFIG', 'MODEL_CALL_START',
                        'MODEL_CALL_END', 'VALIDATION_OK', 'ANALYSIS_SAVE_START', 'ANALYSIS_SAVED']
            positions = [next(i for i, e in enumerate(events) if e['event'] == name) for name in expected]
            self.assertEqual(positions, sorted(positions))
            for name in expected:
                self.assertEqual(next(e for e in events if e['event'] == name)['run_id'], run_id)
            selected = next(e for e in events if e['event'] == 'ANALYSIS_SELECTED')
            self.assertEqual(selected['analysis_id'], saved['id'])
            self.assertEqual(selected['persisted_run_id'], run_id)
            self.assertEqual(selected['method'], 'contextual')
            self.assertNotIn('Jane Smith', '\n'.join(logs.output))
            self.assertNotIn('jane@example.test', '\n'.join(logs.output))

    def test_forged_current_hash_does_not_accept_legacy_result_in_contextual_mode(self):
        from app.analysis import versions
        from app.repositories import get_job, get_resume
        self.prepare(); self.upload()
        with patch.dict(os.environ, {'CONTEXTUAL_EVALUATOR': 'experimental'}):
            # Mesmo com hashes forjados, o contrato contextual é exigido na leitura.
            from test_web_filters import FakeClient
            client = FakeClient(self.db); client.uid = 'u1'
            job, resume = get_job(client, '1'), get_resume(client, '1', '1')
            self.db['analyses'][0].update(versions(job, resume))
            page = self.client.get('/vagas/1/candidato/1').data.decode()
            self.assertIn('Desatualizada', page)
            self.assertNotIn('Avaliação por regras legadas', page)

    def test_inference_and_validation_failures_are_technical_and_not_saved(self):
        self.prepare(); self.upload()
        original_count = len(self.db['analyses'])
        class Broken:
            def generate(self, payload):
                raise TimeoutError('sensitive content must never be logged')
        for adapter, code in [(Broken(), 'MODEL_INFERENCE_ERROR'),
                              (SimpleNamespace(generate=lambda payload: '{}'), 'MODEL_OUTPUT_INVALID')]:
            with self.subTest(code=code), patch.dict(os.environ, {'CONTEXTUAL_EVALUATOR': 'experimental'}), patch(
                    'app.analysis.load_contextual_model', return_value=adapter), self.assertLogs(
                    'talentmatch.analysis', level='INFO') as logs:
                self.select()
                page = self.client.get('/vagas/1').data.decode()
                self.assertIn(code, page)
                self.assertEqual(len(self.db['analyses']), original_count)
                self.assertNotIn('ANALYSIS_SAVED', '\n'.join(logs.output))
                self.assertNotIn('sensitive content', '\n'.join(logs.output))

    def test_contextual_loader_cache_includes_runtime_revision_and_does_not_cache_failure(self):
        from app.analysis import load_contextual_model
        from src.matching.contextual import ContextualTechnicalError
        load_contextual_model.cache_clear()
        self.addCleanup(load_contextual_model.cache_clear)
        with patch('src.matching.contextual.create_adapter', return_value=object()) as factory:
            load_contextual_model('model', 'r1', 'llama_cpp', 'runtime', 'hash1')
            load_contextual_model('model', 'r1', 'llama_cpp', 'runtime', 'hash1')
            self.assertEqual(factory.call_count, 1)
            load_contextual_model('model', 'r1', 'llama_cpp', 'runtime', 'hash2')
            self.assertEqual(factory.call_count, 2)
        with patch('src.matching.contextual.create_adapter', side_effect=RuntimeError('secret')):
            with self.assertRaisesRegex(ContextualTechnicalError, '^MODEL_LOAD_ERROR$'):
                load_contextual_model('missing', 'r1')
        with patch('src.matching.contextual.create_adapter', return_value=object()) as recovered:
            self.assertIsNotNone(load_contextual_model('missing', 'r1'))
            recovered.assert_called_once()

    def test_new_upload_persistence_recovery_and_no_duplicate(self):
        self.prepare()
        self.assertEqual(self.upload().status_code, 302)
        self.assertEqual(self.db['analyses'][0]['result']['score'], 100)
        self.upload()
        self.assertEqual(len(self.db['resumes']), 1)
        self.assertEqual(len(self.db['analyses']), 1)
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('100.00%', page)
        self.assertNotIn('Similaridade: Indisponível', page)
        self.assertIn('evidência literal suficiente para python', page)
        self.assertNotIn('Alta aderência', page)

    def test_incompatible_saved_results_require_reanalysis_without_template_error(self):
        from copy import deepcopy
        self.prepare(); self.upload()
        record = self.db['analyses'][0]
        original = deepcopy(record['result'])
        variants = []
        for field in ('counts', 'weights', 'details'):
            changed = deepcopy(original)
            changed.pop(field)
            variants.append(changed)
        variants.extend([None, {}, dict(original, counts=None),
                         dict(original, score_name='indice_compatibilidade_semantica',
                              formula_version='2.1', score=21.88)])
        for result in variants:
            with self.subTest(result=result):
                # Mantém os hashes atuais para testar o contrato, não só a versão do hash.
                record['result'] = result
                response = self.client.get('/vagas/1/candidato/1')
                self.assertEqual(response.status_code, 200)
                self.assertIn('formato incompatível', response.data.decode())
                listing = self.client.get('/vagas/1').data.decode()
                self.assertIn('data-score=""', listing)
                self.assertNotIn('21.88%', listing)
                self.assertEqual(record['result'], result)
        self.select()
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('100.00%', page)
        self.assertIn('100,00% do peso total da vaga', page)
        self.assertNotIn('formato incompatível', page)

    def test_templates_handle_legacy_result_even_with_old_backend_loaded(self):
        self.prepare(); self.upload()

        def attach_legacy(client, job, candidates):
            for candidate in candidates:
                candidate.update(analysis={'score': 21.88, 'details': [],
                                           'weights': {'obrigatorio': 90, 'desejavel': 10}},
                                 score=21.88, mandatory_status='incompativel',
                                 analysis_state='Obrigatório incompatível')
            return candidates

        # Simula exatamente um processo com código Python antigo e templates novos.
        with patch('app.routes.attach_analysis', side_effect=attach_legacy):
            detail = self.client.get('/vagas/1/candidato/1')
            self.assertEqual(detail.status_code, 200)
            page = detail.data.decode()
            self.assertIn('formato incompatível', page)
            self.assertNotIn('21.88%', page)
            self.assertNotIn('Obrigatório incompatível', page)
            self.assertNotIn('Atendidos: 0', page)
            listing = self.client.get('/vagas/1')
            self.assertEqual(listing.status_code, 200)
            self.assertIn('data-score=""', listing.data.decode())
            self.assertNotIn('21.88%', listing.data.decode())

    def test_detail_counts_required_and_desirable_matches_separately(self):
        self.prepare()
        requirements = json.loads(self.db['jobs'][0]['requisitos'])
        requirements['items'].append({
            'id': 'R2', 'text': 'Collaborate with teams',
            'tipo': 'comportamental', 'nivel': 'desejavel',
        })
        self.db['jobs'][0]['requisitos'] = json.dumps(requirements)
        self.upload()
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('Obrigatórios com evidência: 1/1.', page)
        self.assertIn('Desejáveis com evidência: 0/1.', page)
        self.assertIn('Resultado provisório', page)
        self.assertIn('Peso: 2.0', page)
        self.assertIn('Peso: 1.0', page)
        self.assertIn('Collaborate with teams', page)

    def test_all_undecided_has_no_displayed_score_or_rank(self):
        self.prepare()
        self.db['jobs'][0]['requisitos'] = self.db['jobs'][0]['requisitos'].replace('Python', 'Liderança complexa')
        self.upload()
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('Avaliação pendente', page)
        self.assertIn('Nenhum requisito decidido', page)
        self.assertNotIn('0.00%', page)
        self.assertNotIn('100.00%', page)
        listing = self.client.get('/vagas/1').data.decode()
        self.assertIn('class="rank-num">—', listing)
        self.assertIn('data-score=""', listing)

    def test_conditions_are_reviewed_saved_and_invalidate_analysis(self):
        self.prepare(); self.upload()
        old_analysis = self.db['analyses'][0]
        response = self.post('/requisitos/sugerir-condicao', {'text': 'Pandas e NumPy'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['condition'], {'kind': 'all', 'terms': ['pandas', 'numpy']})
        # A sugestão não modifica a vaga nem os resultados existentes.
        self.assertNotIn('condition', json.loads(self.db['jobs'][0]['requisitos'])['items'][0])
        response = self.post('/vagas/1/editar', {
            'title': 'Python developer', 'description': 'Graduação em computação', 'status': 'Aberta',
            'req_id': ['R1'], 'req_text': ['Python'], 'req_tipo': ['tecnico'],
            'req_nivel': ['obrigatorio'], 'req_condition_mode': ['all'],
            'req_condition_terms': ['Python; Docker'],
        })
        self.assertEqual(response.status_code, 302)
        stored = json.loads(self.db['jobs'][0]['requisitos'])['items'][0]
        self.assertEqual(stored['id'], 'R1')
        self.assertEqual(stored['text'], 'Python')
        self.assertEqual(stored['condition']['terms'], ['python', 'docker'])
        page = self.client.get('/vagas/1/candidato/1').data.decode()
        self.assertIn('Desatualizada', page)
        self.assertIn('descrição menciona formação', page)
        self.assertEqual(self.db['analyses'][0], old_analysis)

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

    def test_ranking_uses_percentage_without_mandatory_exclusion(self):
        self.prepare(); self.upload(); self.upload('other.pdf', 'SQL'); self.upload('third.pdf', 'Docker')
        self.db['analyses'][0]['result']['score'] = 70.01
        self.db['analyses'][1]['result']['score'] = 70.99
        self.db['analyses'][1]['result']['undecided'] = False
        self.db['analyses'][1]['result']['details'][0]['estado'] = 'nao_identificado'
        self.db['analyses'][1]['result']['counts'] = {'atendido': 0, 'nao_identificado': 1, 'revisao_necessaria': 0}
        self.db['analyses'].pop()
        page = self.client.get('/vagas/1').data.decode()
        self.assertLess(page.index('data-score="70.99"'), page.index('data-score="70.01"'))
        self.assertLess(page.index('data-score="70.01"'), page.index('data-score=""'))
        self.assertIn('Sem rejeição automática', page)
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
