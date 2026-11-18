import json
import unittest
from src.matching.contextual import evaluate, evaluate_batch, retrieve


class FakeAdapter:
    """Dublê de contrato; nenhuma inferência real."""
    def __init__(self, state='sustentado', ids=None):
        self.state, self.ids = state, ids if ids is not None else ['e0']

    def generate(self, payload):
        return json.dumps(dict(estado=self.state, evidence_ids=self.ids,
            justificativa='Teste de contrato', limitacoes=[], base='evidencia'))


class ContextualTests(unittest.TestCase):
    req = dict(id='r1', text='Análise de dados', nivel='obrigatorio')
    evidence = [dict(id='e0', text='Analisei dados', source='project')]

    def test_pdf_wrapping_and_project_boundaries(self):
        from src.nlp.skills_extractor import extract_context_blocks
        blocks = extract_context_blocks('Projetos\nProjeto A | 2023\n- Desenvolvi proces-\nsamento de dados\nProjeto B | 2024\n- Criei relatórios')
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]['text'], 'Desenvolvi processamento de dados')
        self.assertNotIn('Projeto A', blocks[1]['context_header'])

    def test_section_boundaries_and_wrapped_summary(self):
        from src.nlp.skills_extractor import extract_context_blocks
        blocks = extract_context_blocks('Resumo profissional\nDesenvolvo APIs e testes\nautomatizados em equipe.\nFormação acadêmica\nBacharelado em Sistemas de Informação\nConclusão: Dez/2025\nCompetências técnicas & ferramentas\nPython, Git, Docker')
        summary = next(b for b in blocks if b['source'] == 'summary')
        education = next(b for b in blocks if b['source'] == 'education')
        self.assertIn('testes automatizados', summary['text'])
        self.assertIn('Conclusão: Dez/2025', education['text'])
        self.assertNotIn('Docker', education['text'])
        self.assertTrue(any(b['source'] == 'skill_context' and 'Docker' in b['text'] for b in blocks))

    def test_invented_citation_rejected(self):
        self.assertEqual(evaluate(self.req, self.evidence, FakeAdapter(ids=['inventada']))['estado'], 'indeterminado')

    def test_missing_model_and_evidence(self):
        self.assertEqual(evaluate(self.req, self.evidence, None)['estado'], 'indeterminado')
        self.assertEqual(evaluate(self.req, [], FakeAdapter())['base'], 'ausencia')

    def test_invalid_json(self):
        class Invalid:
            def generate(self, payload):
                return '```json {} ```'
        self.assertEqual(evaluate(self.req, self.evidence, Invalid())['estado'], 'indeterminado')

    def test_support_requires_citation(self):
        self.assertEqual(evaluate(self.req, self.evidence, FakeAdapter(ids=[]))['estado'], 'indeterminado')

    def test_extra_fields_rejected(self):
        class Extra(FakeAdapter):
            def generate(self, payload):
                value = json.loads(super().generate(payload))
                value['confidence'] = .99
                return json.dumps(value)
        self.assertEqual(evaluate(self.req, self.evidence, Extra())['estado'], 'indeterminado')

    def test_no_support_is_not_pending(self):
        result = evaluate_batch([self.req], [dict(id='r1', ranking=[dict(input_index=0, similarity=.99)])],
                                self.evidence, FakeAdapter('nao_sustentado_pelas_evidencias'))
        self.assertEqual((result['score'], result['maximum_score']), (0, 0))
        self.assertFalse(result['provisional'])

    def test_displayed_evidence_is_actually_cited(self):
        entries = [dict(text='Trecho relacionado', source='summary'),
                   dict(text='Trecho que sustenta', source='project')]
        row = dict(id='r1', ranking=[dict(input_index=0, similarity=.9), dict(input_index=1, similarity=.8)])
        result = evaluate_batch([self.req], [row], entries, FakeAdapter(ids=['e1']))
        self.assertEqual(result['details'][0]['best_evidence']['text'], 'Trecho que sustenta')
        self.assertEqual(len(result['details'][0]['diagnostic']['retrieved_evidence']), 2)

    def test_full_evidence_not_chunk(self):
        entries = [dict(text='Texto completo', source='experience', context_header='Empresa 2024')]
        row = dict(id='r1', ranking=[dict(input_index=0, text='Texto', similarity=.8)])
        self.assertEqual(retrieve(row, entries)[0]['text'], 'Texto completo')
        result = evaluate_batch([self.req], [row], entries, FakeAdapter('parcialmente_sustentado'))
        self.assertEqual((result['score'], result['maximum_score']), (0, 100))
        self.assertTrue(result['provisional'])

    def test_weighted_decisions(self):
        reqs = [self.req, dict(id='r2', text='Outro', nivel='desejavel')]
        rows = [dict(id='r1', ranking=[dict(input_index=0, similarity=.1)]), dict(id='r2', ranking=[])]
        result = evaluate_batch(reqs, rows, self.evidence, FakeAdapter())
        self.assertAlmostEqual(result['minimum_confirmed'], 200 / 3)
        self.assertEqual(result['maximum_score'], 100)
