import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault('FLASK_SECRET_KEY', 'test-only-secret-not-for-deployment')
from src.data.privacy import anonymize_for_analysis, latest_role, personal_spans
from src.data.clean import anonymize_resume_text
from app.repositories import resume_for_template
from app.analysis import analyze, attach_analysis, versions, configuration, fingerprint
from app.requisitos import build_requirements


def entity(text, value, label='NAME'):
    start = text.index(value)
    return dict(text=value, label=label, start=start, end=start + len(value))


class PrivacyTests(unittest.TestCase):
    def test_partial_predictions_do_not_corrupt_words_or_expand(self):
        text = 'ajudando planejamento analítica Proatividade governança atendimento'
        fragments = [entity(text, 'an'), entity(text, 'Pro'), entity(text, 'govern')]
        self.assertEqual(anonymize_for_analysis(text, fragments), text)
        self.assertEqual(anonymize_for_analysis(text, [entity(text, 'Proatividade', 'LOCATION')]), text)
        self.assertEqual(anonymize_for_analysis('an\n' + text, [entity('an\n' + text, 'an')]), 'an\n' + text)

    def test_full_name_and_contacts_redacted_only_at_their_positions(self):
        text = 'Ana Ferreira\nana@example.com\n(11) 98765-4321\nPython 3.11; SQL Server 2022; 2020-2024'
        safe = anonymize_for_analysis(text, [entity(text, 'Ana Ferreira')])
        self.assertNotIn('Ana Ferreira', safe)
        self.assertNotIn('ana@example.com', safe)
        self.assertNotIn('98765-4321', safe)
        self.assertIn('Python 3.11; SQL Server 2022; 2020-2024', safe)

    def test_invalid_foreign_and_overlapping_spans(self):
        text = 'Ana Maria Silva\nSkills: Python'
        valid = [entity(text, 'Ana Maria'), entity(text, 'Maria Silva')]
        self.assertEqual(personal_spans(text, valid), [(0, 15)])
        self.assertEqual(anonymize_for_analysis(text, valid), '[DADO PESSOAL OCULTO]\nSkills: Python')
        invalid = [dict(label='NAME', text='Ana Maria', start=-1, end=8),
                   dict(label='NAME', text='Ana Maria', start=0, end=999),
                   dict(label='NAME', text='Other Name', start=0, end=10),
                   dict(label='NAME', text='Ana Maria', start=True, end=9),
                   dict(label='NAME', text='Ana Maria')]
        self.assertEqual(anonymize_for_analysis(text, invalid), text)

    def test_contact_rules_keep_qualifications_and_versions(self):
        text = 'Python 3.11, .NET 8, ISO 27001, ITIL 4, v123456789, 2019-2023'
        self.assertEqual(anonymize_resume_text(text), text)
        self.assertEqual(anonymize_resume_text('Proatividade', 'Proatividade'), 'Proatividade')

    def test_requirements_and_embedding_inputs_do_not_use_global_name_rules(self):
        text = 'Ana Ferreira\nSKILLS\nPython\nEXPERIENCE\n- ajudando planejamento analítica proatividade governança atendimento'
        entities = [entity(text, 'Ana Ferreira'), entity(text, 'an'), entity(text, 'Python', 'SKILLS')]
        captured = []
        class Embedder:
            def encode(self, inputs):
                captured.extend(inputs)
                return dict(records=[dict(item, input_index=i, chunk_index=0) for i, item in enumerate(inputs)],
                            embeddings=[[1., 0.] for item in inputs])
        requirement = 'Ana Ferreira: planejamento, analítica e proatividade'
        job = {'requirements_data': build_requirements([dict(text=requirement, tipo='tecnico', nivel='obrigatorio')])}
        resume = dict(raw_text=text, name='Ana Ferreira')
        with patch('app.analysis.load_models', return_value=(SimpleNamespace(predict=lambda **kw: {'entities': entities}), Embedder())):
            result = analyze(job, resume)
        self.assertEqual(captured[0]['text'], requirement)
        self.assertEqual(result['result']['details'][0]['text'], requirement)
        evidence = ' '.join(item['text'] for item in captured[1:])
        for word in ['ajudando', 'planejamento', 'analítica', 'proatividade', 'governança', 'atendimento']:
            self.assertIn(word, evidence)
        self.assertNotIn('Ana Ferreira', evidence)

    def test_responsibilities_are_not_roles(self):
        text = 'EXPERIENCE\n- Helping with project planning and customer service'
        self.assertEqual(latest_role(text, []), 'Não identificado')
        self.assertEqual(resume_for_template(dict(id=1, texto_extraido=text))['last_role'], 'Não identificado')

    def test_role_requires_designation_header_and_dates(self):
        text = 'EXPERIENCE\nSoftware Engineer\n2020-2022\n- Built APIs\n\nSenior Engineer\n2023-Present\n- Led projects'
        entities = [entity(text, 'Software Engineer', 'DESIGNATION'), entity(text, 'Senior Engineer', 'DESIGNATION')]
        self.assertEqual(latest_role(text, entities), 'Senior Engineer')
        self.assertEqual(latest_role(text, [entity(text, 'Built APIs', 'DESIGNATION')]), 'Não identificado')
        self.assertEqual(latest_role('EXPERIENCE\nSoftware Engineer\n- Built APIs',
                                    [entity('EXPERIENCE\nSoftware Engineer\n- Built APIs', 'Software Engineer', 'DESIGNATION')]), 'Não identificado')

    def test_old_configuration_is_stale_and_history_remains(self):
        job = dict(id='1', requirements_data=build_requirements([dict(text='Python', tipo='tecnico')]))
        resume = dict(id='1', raw_text='SKILLS\nPython', last_role='activity')
        old_config = dict(configuration(), pipeline_version='web-1')
        row = dict(curriculo_id=1, **versions(job, resume), result=dict(score=45.99))
        row['config_hash'] = fingerprint(old_config)
        with patch('app.repositories.list_analyses', return_value=[row]):
            candidate = attach_analysis(None, job, [resume])[0]
        self.assertEqual(candidate['analysis_state'], 'Desatualizada')
        self.assertIsNone(candidate['score'])
        self.assertEqual(row['result']['score'], 45.99)

    def test_role_entity_from_another_section_is_not_header_evidence(self):
        text = 'SUMMARY\nSoftware Engineer\nEXPERIENCE\nSoftware Engineer\n2020-2022\n- Built APIs'
        self.assertEqual(latest_role(text, [entity(text, 'Software Engineer', 'DESIGNATION')]),
                         'Não identificado')

    def test_role_with_ambiguous_or_unsupported_dates_is_not_guessed(self):
        for date in ['2024-2020', '01/2020-12/2024', '2020-2022 and 2023-2024']:
            text = 'EXPERIENCE\nSoftware Engineer\n' + date + '\n- Built APIs'
            self.assertEqual(latest_role(text, [entity(text, 'Software Engineer', 'DESIGNATION')]),
                             'Não identificado')
        text = ('EXPERIENCE\nSoftware Engineer\n2020-2024\n- Built APIs\n\n'
                'Data Engineer\n2020-2024\n- Built pipelines')
        self.assertEqual(latest_role(text, [entity(text, role, 'DESIGNATION')
                                          for role in ['Software Engineer', 'Data Engineer']]),
                         'Não identificado')

    def test_identical_name_elsewhere_does_not_become_a_global_rule(self):
        text = 'Ana Ferreira\nProjeto Ana Ferreira: planejamento e atendimento'
        self.assertEqual(anonymize_for_analysis(text, [entity(text, 'Ana Ferreira')]),
                         '[DADO PESSOAL OCULTO]\nProjeto Ana Ferreira: planejamento e atendimento')
