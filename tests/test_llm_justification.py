import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret')

from app.analysis import ensure_candidate_justification
from src.matching.llm_justification import (
    SCHEMA_VERSION,
    UNAVAILABLE_MESSAGE,
    generate_llm_justification,
    is_justification_available,
)
import test_web_filters as web


def sample_v2_payload(resumo='Perfil alinhado ao desenvolvimento backend em Python.'):
    return {
        'parecer_executivo': {
            'classificacao_aderencia': 'forte',
            'nivel_aparente': 'Desenvolvedora backend com experiência prática em APIs.',
            'resumo_analitico': resumo,
        },
        'analise_requisitos': [
            {
                'requisito': 'Experiência com Python e Flask',
                'nivel': 'obrigatorio',
                'status': 'atendido',
                'analise_contextual': 'Demonstra aplicação prática em desenvolvimento backend.',
            }
        ],
        'pontos_fortes': [
            {
                'titulo': 'Domínio de APIs Python',
                'justificativa': 'Atuação direta com Flask em serviços backend.',
            }
        ],
        'lacunas_e_riscos': [
            {
                'ponto': 'Bancos de dados relacionais',
                'impacto': 'medio',
                'observacao': 'Não detalha uso de SQL no texto analisado.',
            }
        ],
        'equivalencias_e_transferiveis': [
            {
                'requisito_relacionado': 'FastAPI',
                'experiencia_equivalente': 'Flask em produção',
                'observacao': 'Base sólida em microframeworks web Python facilita transição.',
            }
        ],
        'curva_de_adaptacao': {
            'nivel': 'baixa',
            'justificativa': 'Domina o ecossistema principal e precisa apenas aprofundar SQL.',
            'areas_de_ramp_up': ['Otimização de queries SQL'],
        },
        'nota_transparencia': 'Currículo resumido sem datas detalhadas de cada projeto.',
    }


class FakeAuthClient:
    def __init__(self):
        self.auth = self

    def set_session(self, access, refresh):
        return SimpleNamespace(
            user=SimpleNamespace(id='user-1', email='ana@example.com'),
            session=SimpleNamespace(access_token=access, refresh_token=refresh),
        )

    def get_user(self, token):
        return SimpleNamespace(user=SimpleNamespace(id='user-1', email='ana@example.com'))


class LlmJustificationTests(unittest.TestCase):
    def setUp(self):
        self.job = {
            'id': '1',
            'title': 'Desenvolvedor Python',
            'description': 'Atuação com Flask e APIs REST.',
            'requirements_data': {
                'status': 'revisado',
                'items': [{'id': 'r1', 'text': 'Experiência com Python e Flask', 'nivel': 'obrigatorio'}],
            },
        }
        self.candidate = {
            'id': '10',
            'job_id': '1',
            'name': 'Candidato #10',
            'real_name': 'Maria Oliveira',
            'initials': 'C10',
            'filename': 'curriculo_10.pdf',
            'submitted_at': '17/11/2026',
            'status': 'Pendente',
            'email': 'Oculto',
            'phone': 'Oculto',
            'raw_text': 'Maria Oliveira\nmaria@example.com\n(11) 99999-8888\nDesenvolvedora Python com Flask.',
            'anonymized_text': '[NOME OCULTO]\n[EMAIL OCULTO]\n[TELEFONE OCULTO]\nDesenvolvedora Python com Flask.',
            'education': 'Sistemas de Informação',
            'last_role': 'Desenvolvedora Python',
            'skills': ['Python', 'Flask'],
            'score': None,
            'analysis': None,
            'analysis_state': 'Pendente',
        }

    def test_missing_api_key_returns_unavailable_fallback(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}, clear=False):
            result = generate_llm_justification(self.job, candidate=self.candidate)
        self.assertEqual(result['status'], 'indisponivel')
        self.assertEqual(result['message'], UNAVAILABLE_MESSAGE)
        self.assertFalse(is_justification_available(result))

    def test_api_error_returns_unavailable_fallback(self):
        def broken_transport(url, api_key, body, timeout):
            raise RuntimeError('Timeout na API')

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key'}, clear=False):
            result = generate_llm_justification(self.job, candidate=self.candidate, transport=broken_transport)
        self.assertEqual(result['status'], 'indisponivel')
        self.assertEqual(result['message'], UNAVAILABLE_MESSAGE)

    def test_invalid_schema_payload_returns_unavailable_fallback(self):
        def incomplete_transport(url, api_key, body, timeout):
            return {'candidates': [{'content': {'parts': [{'text': json.dumps({'resumo_geral': 'v1 antigo'})}]}}]}

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key'}, clear=False):
            result = generate_llm_justification(self.job, candidate=self.candidate, transport=incomplete_transport)
        self.assertEqual(result['status'], 'indisponivel')
        self.assertEqual(result['reason'], 'api_error')

    def test_uses_anonymized_data_only_and_returns_v2_structured_content(self):
        captured = {}

        def fake_transport(url, api_key, body, timeout):
            captured['url'] = url
            captured['prompt'] = body['contents'][0]['parts'][0]['text']
            captured['schema'] = body['generationConfig']['responseSchema']
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(sample_v2_payload())}]}}]}

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key', 'GEMINI_MODEL': 'gemini-3.5-flash-lite'}, clear=False):
            result = generate_llm_justification(self.job, candidate=self.candidate, transport=fake_transport)

        self.assertTrue(is_justification_available(result))
        self.assertEqual(result['schema_version'], SCHEMA_VERSION)
        self.assertEqual(result['provider'], 'gemini')
        self.assertNotIn('roteiro_entrevista', captured['schema']['properties'])
        self.assertEqual(result['content']['parecer_executivo']['classificacao_aderencia'], 'forte')
        self.assertEqual(result['content']['analise_requisitos'][0]['status'], 'atendido')
        self.assertEqual(result['content']['curva_de_adaptacao']['nivel'], 'baixa')
        self.assertEqual(result['content']['equivalencias_e_transferiveis'][0]['experiencia_equivalente'], 'Flask em produção')
        self.assertNotIn('Maria Oliveira', captured['prompt'])
        self.assertNotIn('maria@example.com', captured['prompt'])
        self.assertNotIn('99999-8888', captured['prompt'])
        self.assertIn('[NOME OCULTO]', captured['prompt'])

    def test_retries_next_model_on_503_service_unavailable(self):
        import httpx

        calls = []

        def flaky_transport(url, api_key, body, timeout):
            calls.append(url)
            if len(calls) == 1:
                req = httpx.Request('POST', url)
                resp = httpx.Response(503, request=req)
                raise httpx.HTTPStatusError('503', request=req, response=resp)
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(sample_v2_payload())}]}}]}

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key', 'GEMINI_MODEL': ''}, clear=False):
            result = generate_llm_justification(self.job, candidate=self.candidate, transport=flaky_transport)

        self.assertTrue(is_justification_available(result))
        self.assertEqual(len(calls), 2)
        self.assertIn('gemini-3.1-flash-lite', calls[0])
        self.assertIn('gemini-3.5-flash-lite', calls[1])

    def test_pr30_documental_and_contextual_context_included_without_pii(self):
        captured = {}

        def fake_transport(url, api_key, body, timeout):
            captured['prompt'] = body['contents'][0]['parts'][0]['text']
            return {'candidates': [{'content': {'parts': [{'text': json.dumps(sample_v2_payload())}]}}]}

        pr30_analysis = {
            'formula_version': '3.1-experimental',
            'score': 61.54,
            'maximum_score': 92.31,
            'provisional': True,
            'undecided': False,
            'counts': {'atendido': 1, 'nao_identificado': 0, 'revisao_necessaria': 1},
            'mandatory_status': 'atencao',
            'contextual_configuration': {'enabled': True},
            'details': [
                {
                    'text': 'Experiência com Python e Flask',
                    'nivel': 'obrigatorio',
                    'peso': 2.0,
                    'estado': 'revisao_necessaria',
                    'compatible': False,
                    'justificativa': 'Maria Oliveira atuou em backend Python.',
                    'original_cosine': 0.72,
                    'best_evidence': {'source': 'experience', 'text': 'Maria Oliveira - maria@example.com - Flask'},
                    'diagnostic': {
                        'contextual': {
                            'estado': 'parcialmente_sustentado',
                            'base': 'ambiguidade',
                            'limitacoes': ['Revisão humana necessária.'],
                        }
                    },
                }
            ],
        }

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key'}, clear=False):
            result = generate_llm_justification(
                self.job,
                candidate=self.candidate,
                analysis_result=pr30_analysis,
                transport=fake_transport,
            )

        self.assertTrue(is_justification_available(result))
        prompt = captured['prompt']
        self.assertIn('minimo_confirmado', prompt)
        self.assertIn('92.31', prompt)
        self.assertIn('parcialmente_sustentado', prompt)
        self.assertIn('avaliacao_contextual_local', prompt)
        self.assertNotIn('Maria Oliveira', prompt)
        self.assertNotIn('maria@example.com', prompt)

    def test_ensure_candidate_justification_skips_when_v2_already_available(self):
        existing = {
            'status': 'disponivel',
            'schema_version': SCHEMA_VERSION,
            'model': 'gemini-2.5-flash',
            'content': sample_v2_payload('Já gerado.'),
        }
        candidate = dict(self.candidate, llm_justification=existing)
        called = False

        def should_not_run(*args, **kwargs):
            nonlocal called
            called = True
            return {}

        result = ensure_candidate_justification(None, self.job, candidate, transport=should_not_run)
        self.assertFalse(called)
        self.assertEqual(result, existing)

    def test_ensure_candidate_justification_retries_when_unavailable_or_old_schema_and_persists(self):
        candidate = dict(
            self.candidate,
            llm_justification={'status': 'indisponivel', 'message': UNAVAILABLE_MESSAGE},
            analysis={'status': 'calculado', 'score': 80.0, 'details': []},
        )

        def ok_transport(url, api_key, body, timeout):
            return {
                'candidates': [{
                    'content': {'parts': [{'text': json.dumps(sample_v2_payload('Gerado na nova tentativa.'))}]}
                }]
            }

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key'}, clear=False), \
                patch('app.repositories.save_analysis') as mocked_save:
            result = ensure_candidate_justification('fake-client', self.job, candidate, transport=ok_transport)

        self.assertTrue(is_justification_available(result))
        self.assertEqual(
            candidate['analysis']['llm_justification']['content']['parecer_executivo']['resumo_analitico'],
            'Gerado na nova tentativa.',
        )
        mocked_save.assert_called_once()

    def _logged_in_client(self):
        client = web.app.test_client()
        with client.session_transaction() as sess:
            sess['auth_user_id'] = 'user-1'
            sess['sb_access_token'] = 'access-user-1'
            sess['sb_refresh_token'] = 'refresh-user-1'
            sess['user_name'] = 'Ana'
            sess['user_initials'] = 'A'
        return client

    def test_candidate_detail_route_renders_fallback_when_unavailable(self):
        client = self._logged_in_client()
        fake_job = {
            'id': '1',
            'title': 'Python Dev',
            'description': 'Backend Python',
            'status': 'Aberta',
            'requirements_data': {'status': 'revisado', 'items': []},
        }
        candidate = dict(self.candidate, llm_justification=None)

        with patch('app.routes.create_supabase_client', return_value=FakeAuthClient()), \
                patch('app.routes.ensure_profile', return_value={'id': 1, 'nome': 'Ana'}), \
                patch('app.routes.database_job', return_value=fake_job), \
                patch('app.routes.get_resume', return_value=candidate), \
                patch('app.routes.attach_analysis', side_effect=lambda c, j, items: items), \
                patch.dict(os.environ, {'GEMINI_API_KEY': ''}, clear=False):
            resp = client.get('/vagas/1/candidato/10')

        self.assertEqual(resp.status_code, 200)
        self.assertIn(UNAVAILABLE_MESSAGE, resp.data.decode('utf-8'))

    def test_candidate_detail_route_retries_unavailable_and_renders_v2_sections(self):
        client = self._logged_in_client()
        fake_job = {
            'id': '1',
            'title': 'Python Dev',
            'description': 'Backend Python',
            'status': 'Aberta',
            'requirements_data': {'status': 'revisado', 'items': []},
        }
        candidate = dict(self.candidate, llm_justification={'status': 'indisponivel', 'message': UNAVAILABLE_MESSAGE})

        with patch('app.routes.create_supabase_client', return_value=FakeAuthClient()), \
                patch('app.routes.ensure_profile', return_value={'id': 1, 'nome': 'Ana'}), \
                patch('app.routes.database_job', return_value=fake_job), \
                patch('app.routes.get_resume', return_value=candidate), \
                patch('app.routes.attach_analysis', side_effect=lambda c, j, items: items), \
                patch('src.matching.llm_justification._default_transport',
                      return_value={'candidates': [{'content': {'parts': [{'text': json.dumps(sample_v2_payload())}]}}]}), \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-key'}, clear=False):
            resp = client.get('/vagas/1/candidato/10')

        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('Aderência Forte', html)
        self.assertIn('Análise Contextual por Requisito', html)
        self.assertIn('Domínio de APIs Python', html)
        self.assertIn('Impacto Médio', html)
        self.assertIn('Equivalências e Competências Transferíveis', html)
        self.assertIn('Flask em produção', html)
        self.assertIn('Curva de Adaptação', html)
        self.assertIn('Curva Baixa', html)
        self.assertIn('Otimização de queries SQL', html)
        self.assertIn('Transparência da análise:', html)
        self.assertIn('data-cand-tab="resumo"', html)
        self.assertIn('data-cand-tab="requisitos"', html)
        self.assertIn('data-cand-tab="curriculo"', html)
        self.assertIn('class="resume-text-view"', html)
        self.assertNotIn('class="pdf-bar"', html)


if __name__ == '__main__':
    unittest.main()
