import unittest
from copy import deepcopy
from pathlib import Path
from werkzeug.datastructures import MultiDict

from app.requisitos import build_requirements, parse_requirements, rows_from_form, requirement_warnings
from src.matching.adherence import evaluate_requirements, calculate_adherence
from src.matching.documental_rules import suggest_condition
from src.nlp.skills_extractor import extract_skills
from src.data.privacy import anonymize_for_analysis
from src.data.privacy import uploaded_name_entities
from src.data.clean import extract_pdf_text
from test_pdf_upload import make_sample_pdf
from scripts.diagnosticar_aderencia import synthetic_diagnostic


class DocumentalRulesTests(unittest.TestCase):
    def evaluate(self, text, entries, condition=None):
        req = dict(id='R1', text=text, nivel='obrigatorio', tipo='tecnico')
        if condition:
            req['condition'] = condition
        rankings = [dict(id='R1', top_similarity=.99, ranking=[dict(
            text='Texto relacionado', source='summary', similarity=.99, input_index=99, chunk_index=0)])]
        return evaluate_requirements([req], rankings, entries)[0]

    def test_wrong_top1_does_not_hide_python(self):
        result = self.evaluate('Conhecimento em Python', [dict(text='SQL', source='skill'),
                                                       dict(text='Python, Flask', source='skill')])
        self.assertEqual(result['estado'], 'atendido')
        self.assertEqual(result['evidencias'][0]['text'], 'Python, Flask')
        self.assertEqual(result['diagnostic']['matched_terms'], ['python'])

    def test_all_and_any_conditions_with_individual_missing_terms(self):
        for terms in (['pandas', 'numpy'], ['git', 'docker']):
            condition = dict(kind='all', terms=terms)
            for present in ([], terms[:1], terms[1:], terms):
                with self.subTest(terms=terms, present=present):
                    entries = [dict(text=term, source='skill') for term in present]
                    result = self.evaluate('Requisito composto', entries, condition)
                    self.assertEqual(result['estado'], 'atendido' if len(present) == 2 else 'revisao_necessaria')
                    self.assertEqual(result['diagnostic']['missing_terms'], sorted(set(terms) - set(present)))
        result = self.evaluate('SQL ou PostgreSQL', [dict(text='Postgres', source='skill')],
                               dict(kind='any', terms=['sql', 'postgresql']))
        self.assertEqual(result['estado'], 'atendido')

    def test_activity_requires_same_activity_not_scattered_words(self):
        for entries in ([dict(text='Python', source='skill'), dict(text='Desenvolvi APIs REST.', source='project')],
                        [dict(text='Desenvolvi APIs em Java; utilizei Python em planilhas.', source='project')],
                        [dict(text='Desenvolvi painéis em Python e APIs em Java.', source='project')],
                        [dict(text='Desenvolvi APIs em Java e pipelines em Python.', source='project')],
                        [dict(text='Python, APIs', source='skill')]):
            self.assertEqual(self.evaluate('Desenvolver APIs em Python', entries)['estado'], 'revisao_necessaria')
        result = self.evaluate('Desenvolver APIs em Python', [dict(text='Desenvolvi APIs em Python.', source='experience')])
        self.assertEqual(result['estado'], 'atendido')
        self.assertEqual(result['evidencias'][0]['source'], 'experience')

    def test_negation_hypothesis_and_boundaries(self):
        for value in ('Sem experiência com Python', 'No Python experience', 'Pretendo desenvolver em Python',
                      'Aprendendo Python', 'CPython', 'Pythonista', 'Experiência da equipe com Python'):
            with self.subTest(value=value):
                self.assertEqual(self.evaluate('Python', [dict(text=value, source='experience')])['estado'],
                                 'revisao_necessaria')
        result = self.evaluate('Python', [dict(text='Python', source='skill', evidence=['Sem Python'])])
        self.assertEqual(result['estado'], 'revisao_necessaria')
        self.assertEqual(self.evaluate('Pandas', [dict(text='Python', source='skill')])['estado'], 'revisao_necessaria')
        self.assertEqual(self.evaluate('React', [dict(text='Next.js', source='skill')])['estado'], 'revisao_necessaria')

    def test_language_and_education_require_own_explicit_evidence(self):
        self.assertEqual(self.evaluate('Inglês intermediário', [dict(text='English B2', source='language')])['estado'], 'atendido')
        for text in ('English basic', 'English', 'English basic; Spanish fluent'):
            self.assertEqual(self.evaluate('Inglês intermediário', [dict(text=text, source='language')])['estado'], 'revisao_necessaria')
        req = 'Bacharelado em Sistemas de Informação'
        for value in ('Bacharelado em Sistemas de Informação concluído em 2023',
                      'Bacharelado em Sistemas de Informação em andamento', 'Sistemas de Informação'):
            expected = 'atendido' if 'concluído' in value else 'revisao_necessaria'
            self.assertEqual(self.evaluate(req, [dict(text=value, source='education')])['estado'], expected)

    def test_fixture_sections_redaction_and_decisions(self):
        diagnostic = synthetic_diagnostic()
        result = diagnostic['result']
        self.assertEqual([d['estado'] for d in result['details']], ['atendido'] * 7 + ['revisao_necessaria'] * 2)
        self.assertNotIn('Pessoa Sintética', str(diagnostic['extracted_entries']))
        sources = {entry['source'] for entry in diagnostic['extracted_entries']}
        self.assertTrue({'education', 'language', 'project', 'experience', 'skill', 'summary'} <= sources)
        for entry in diagnostic['extracted_entries']:
            if entry['source'] == 'experience':
                self.assertNotIn('Bacharelado', entry['text'])
                self.assertNotIn('Pandas e NumPy', entry['text'])

    def test_web_pipeline_passes_all_entries_beyond_wrong_semantic_candidate(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.analysis import analyze
        diagnostic = synthetic_diagnostic()
        raw = (Path(__file__).parent / 'fixtures/documental_resume.txt').read_text(encoding='utf-8')
        requirements = diagnostic['requirements_received']
        name = 'Pessoa Sintética'
        predictor = SimpleNamespace(predict=lambda **kw: {'entities': [dict(
            label='NAME', text=name, start=0, end=len(name))]})
        class Embedder:
            def encode(self, inputs):
                return dict(records=[dict(entry, input_index=i, chunk_index=0) for i, entry in enumerate(inputs)],
                            embeddings=[[1., 0.] for _ in inputs])
        rankings = [dict(id=req['id'], top_similarity=.99, ranking=[dict(
            text='SQL', source='skill', similarity=.99, input_index=0, chunk_index=0)]) for req in requirements]
        with patch('app.analysis.load_models', return_value=(predictor, Embedder())), \
                patch('src.matching.semantic.compare', return_value=(rankings, None)):
            result = analyze(dict(requirements_data=dict(items=requirements)), dict(raw_text=raw))['result']
        self.assertEqual([d['estado'] for d in result['details']], ['atendido'] * 7 + ['revisao_necessaria'] * 2)
        self.assertNotIn('Pessoa Sintética', str(result))
        self.assertEqual(result['extraction_diagnostic']['requirements_received'], [req['id'] for req in requirements])

    def test_semantic_chunk_metadata_keeps_negative_context(self):
        requirement = [dict(id='R1', text='Python', tipo='tecnico')]
        ranking = [dict(id='R1', top_similarity=.99, ranking=[dict(text='Python', source='skill',
                   metadata=dict(evidence=['Sem experiência em Python']), similarity=.99,
                   input_index=0, chunk_index=0)])]
        decision = evaluate_requirements(requirement, ranking, [dict(text='SQL', source='skill')])[0]
        self.assertEqual(decision['estado'], 'revisao_necessaria')
        self.assertEqual(decision['diagnostic']['rejected_contexts'], 1)

    def test_pt_en_pdf_text_and_first_letter_preserved(self):
        # PDF fixture in latin-1 (same helper as upload tests), without PII.
        lines = ['EXPERIENCIA PROFISSIONAL', '- Desenvolvi APIs em Python',
                 'RELEVANT PROJECTS', '- Built a service with Docker',
                 'EDUCATION & CERTIFICATIONS', 'Bachelor in Computing completed',
                 'LANGUAGES', 'English B2', 'TECHNICAL SKILLS', 'Python, Docker']
        raw = extract_pdf_text(make_sample_pdf(lines))
        self.assertIn('EXPERIENCIA', raw)
        blocks = extract_skills(raw)['context_blocks']
        self.assertTrue(any(b['source'] == 'project' for b in blocks))
        self.assertTrue(any(b['source'] == 'language' for b in blocks))

    def test_conditions_roundtrip_and_explicit_review(self):
        form = MultiDict([('req_id', 'R1'), ('req_text', 'Git e Docker'), ('req_tipo', 'tecnico'),
                          ('req_nivel', 'obrigatorio'), ('req_condition_mode', 'all'),
                          ('req_condition_terms', 'Git; Docker')])
        built = build_requirements(rows_from_form(form), ['R1'])
        self.assertEqual(parse_requirements(built)['items'][0]['condition'], dict(kind='all', terms=['git', 'docker']))
        self.assertEqual(built['items'][0]['text'], 'Git e Docker')
        self.assertEqual(suggest_condition('Pandas e NumPy'), dict(kind='all', terms=['pandas', 'numpy']))
        self.assertEqual(suggest_condition('PostgreSQL, Oracle ou MySQL')['kind'], 'any')
        original = deepcopy(built)
        warnings = requirement_warnings('Graduação em computação', built)
        self.assertTrue(warnings)
        self.assertEqual(built, original)
        broken = build_requirements([dict(id='R2', text='xperiência com Python', tipo='tecnico')])
        self.assertTrue(requirement_warnings('', broken))
        self.assertEqual(broken['items'][0]['text'], 'xperiência com Python')

    def test_all_pending_is_distinct_from_zero_attendance(self):
        decision = self.evaluate('Liderança em projetos complexos', [dict(text='Python', source='skill')])
        result = calculate_adherence([dict(id='R1', text='Liderança', nivel='obrigatorio')], [decision])
        self.assertTrue(result['undecided'])
        self.assertTrue(result['provisional'])
        self.assertEqual(result['counts']['nao_identificado'], 0)

    def test_uploaded_full_name_redacted_without_ner_in_html_fields(self):
        from app.repositories import resume_for_template
        raw = 'Pessoa Sintética\nHABILIDADES TÉCNICAS\nPython\nPessoa Sintética | Página 1'
        masked = '[NOME OCULTO]\nHABILIDADES TÉCNICAS\nPython\nPessoa Sintética | Página 1'
        entities = uploaded_name_entities(raw, masked)
        self.assertTrue(entities)
        self.assertNotIn('Pessoa Sintética', anonymize_for_analysis(raw, entities))
        candidate = resume_for_template(dict(id=7, texto_extraido=raw, texto_anonimizado=masked))
        self.assertNotIn('Pessoa Sintética', str(candidate['skills']))
        # Um fragmento previsto não passa a regra global.
        self.assertFalse(uploaded_name_entities('Python\nPythonista', '[NOME OCULTO]\nPythonista'))

    def test_embedding_windows_do_not_cut_words(self):
        from types import SimpleNamespace
        from src.nlp.embeddings import ResumeEmbedder
        class Tokenizer:
            def __call__(self, text, **kwargs):
                if kwargs.get('return_offsets_mapping'):
                    return {'offset_mapping': [(i, i + 1) for i in range(len(text))]}
                return {'input_ids': list(range(len(text) + 2))}
        embedder = ResumeEmbedder.__new__(ResumeEmbedder)
        embedder.tokenizer = Tokenizer()
        embedder.model = SimpleNamespace(max_seq_length=512)
        embedder.window_size, embedder.overlap = 8, 2
        text = 'Alpha desenvolvimento profissional Beta'
        chunks = embedder._split_text(text)
        coverage = set()
        for chunk in chunks:
            start, end = chunk['start_char'], chunk['end_char']
            self.assertEqual(chunk['text'], text[start:end])
            self.assertFalse(start > 0 and text[start-1].isalnum() and text[start].isalnum())
            self.assertFalse(end < len(text) and text[end-1].isalnum() and text[end].isalnum())
            coverage.update(range(start, end))
        self.assertEqual(coverage, set(range(len(text))))


if __name__ == '__main__':
    unittest.main()
