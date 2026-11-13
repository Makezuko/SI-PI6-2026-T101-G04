"""Fixtures sintéticas: nenhuma leitura do dataset real ou carga de modelos."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.avaliacao_semantica import (annotation_template, code_hashes, consolidate,
    digest, fingerprint, metrics_for, pipeline_version, save, select_sample, validate_annotation)
from scripts.avaliar_amostra_semantica import evaluate, preflight, render, write_reports


def row(rid, rank=None, gold=None, failure=False):
    requirement = dict(id='R1', text='Synthetic requirement', category='literal',
        acceptable_input_indices=gold if gold is not None else [7],
        extraction_failure=failure, evidence_in_original=bool(gold != []) or failure,
        expected_evidence='Synthetic expected evidence', notes='Reviewed', human_analysis={})
    indices = [0, 1, 2, 3]
    if rank:
        indices[rank - 1] = 7
    ranking = [dict(input_index=i, similarity=1 - n * .1, text='Synthetic evidence', source='experience')
               for n, i in enumerate(indices)]
    return dict(resume_id=rid, requirement=requirement,
                result=dict(id='R1', ranking=ranking), expected_inputs=[])


class ExpandedSemanticTests(unittest.TestCase):
    def annotation(self):
        inputs = [dict(input_index=0, text='Built synthetic APIs', source='experience')]
        annotation = annotation_template(dict(resume_id='synthetic'), fingerprint(inputs))
        annotation['human_review'].update(completed=True, reviewer='Synthetic reviewer')
        for r in annotation['requirements']:
            r.update(text='Synthetic requirement', acceptable_input_indices=[], evidence_in_original=False)
        return inputs, annotation

    def test_global_aggregation_uses_requirements_not_mean_of_resumes(self):
        rows = [row('a', 1), row('b', 2), row('b', 3), row('b', 4)]
        result = consolidate(rows, ['a', 'b'])
        self.assertEqual(result['overall']['denominator'], 4)
        self.assertEqual(result['overall']['hit_at_1'], .25)
        self.assertEqual(result['overall']['hit_at_3'], .75)
        self.assertAlmostEqual(result['overall']['mrr'], (1 + .5 + 1/3 + .25)/4)
        self.assertEqual(result['by_resume']['a']['denominator'], 1)
        self.assertEqual(result['by_resume']['b']['denominator'], 3)

    def test_extraction_failure_is_zero_positive_in_end_to_end(self):
        rows = [row('a', 1), row('a', gold=[], failure=True), row('a', gold=[])]
        result = metrics_for(rows)
        self.assertEqual(result['denominator'], 2)
        self.assertEqual(result['extraction_lost_positive_count'], 1)
        self.assertEqual(result['no_evidence_count'], 1)
        self.assertEqual(result['hit_at_1'], .5)
        self.assertEqual(result['mrr'], .5)
        ranking = metrics_for(rows, ranking_only=True)
        self.assertEqual(ranking['denominator'], 1)
        self.assertEqual(ranking['excluded_extraction_failures'], 1)
        self.assertEqual(ranking['hit_at_1'], 1)

    def test_no_evidence_has_no_metric_denominator(self):
        result = metrics_for([row('a', gold=[])])
        self.assertEqual(result['denominator'], 0)
        self.assertIsNone(result['hit_at_1'])
        self.assertIsNone(result['mrr'])

    def test_unannotated_and_pending_review_are_rejected(self):
        inputs, annotation = self.annotation()
        annotation['requirements'][0]['acceptable_input_indices'] = None
        with self.assertRaisesRegex(ValueError, 'não anotado'):
            validate_annotation(annotation, inputs, fingerprint(inputs))
        inputs, annotation = self.annotation()
        annotation['human_review']['completed'] = False
        with self.assertRaisesRegex(ValueError, 'Revisão humana'):
            validate_annotation(annotation, inputs, fingerprint(inputs))

    def test_hash_and_indices_must_match(self):
        inputs, annotation = self.annotation()
        with self.assertRaisesRegex(ValueError, 'Hash'):
            validate_annotation(annotation, inputs, 'different hash')
        annotation['requirements'][0].update(acceptable_input_indices=[99], evidence_in_original=True)
        with self.assertRaisesRegex(ValueError, 'Índice'):
            validate_annotation(annotation, inputs, fingerprint(inputs))
        inputs[0]['input_index'] = 1
        annotation['inputs_sha256'] = fingerprint(inputs)
        with self.assertRaisesRegex(ValueError, 'Índices'):
            validate_annotation(annotation, inputs, fingerprint(inputs))

    def test_extraction_failure_requires_original_evidence_and_explanation(self):
        inputs, annotation = self.annotation()
        r = annotation['requirements'][0]
        r.update(evidence_in_original=True, extraction_failure=True,
                 expected_evidence='Original synthetic evidence omitted', notes='Missing in inputs')
        self.assertEqual(len(validate_annotation(annotation, inputs, fingerprint(inputs))), 6)
        r['extraction_failure'] = False
        with self.assertRaisesRegex(ValueError, 'inconsistentes'):
            validate_annotation(annotation, inputs, fingerprint(inputs))

    def test_categories_and_gold_do_not_enter_compare(self):
        inputs, annotation = self.annotation()
        embeddings = dict(records=[dict(input_index=0, chunk_index=0, source='experience', text='Synthetic')],
                          embeddings=[[1., 0.]])
        class Embedder:
            def encode(self, values):
                return dict(records=[dict(input_index=i) for i in range(len(values))],
                            embeddings=[[1., 0.]] * len(values))
        from src.matching.semantic import compare
        with patch('scripts.avaliar_amostra_semantica.compare', wraps=compare) as mock:
            rows = evaluate([('synthetic', annotation['requirements'], embeddings, inputs, annotation)], Embedder())
        self.assertEqual(set(mock.call_args.args[0][0]), {'id', 'text'})
        self.assertEqual(len(rows), 6)
        empty = dict(records=[], embeddings=[])
        self.assertFalse(evaluate([('synthetic', annotation['requirements'], empty, inputs, annotation)], None)[0]['result']['ranking'])

    def test_preflight_blocks_before_loading_model_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            entries = []
            for i in range(10):
                rid = f'synthetic_{i}'
                target = folder / rid
                target.mkdir()
                inputs, annotation = self.annotation()
                annotation['resume_id'] = rid
                embedded = dict(model_name='synthetic', records=[], embeddings=[])
                (target / 'curriculo.txt').write_bytes(b'Synthetic CV')
                save(target / 'entradas.json', inputs)
                save(target / 'anotacoes.json', annotation)
                save(target / 'embeddings.json', embedded)
                entries.append(dict(resume_id=rid, text_sha256=digest(b'Synthetic CV'),
                                    inputs_sha256=fingerprint(inputs), embeddings_sha256=fingerprint(embedded)))
            manifest = dict(status='awaiting_human_review', selected_resumes=entries,
                            code_hashes=code_hashes(), pipeline_version=pipeline_version(), embedding_model='synthetic')
            save(folder / 'manifest.json', manifest)
            with patch('scripts.avaliar_amostra_semantica.private_output', return_value=folder):
                self.assertEqual(len(preflight(folder)[1]), 10)
                inputs, annotation = self.annotation()
                annotation.update(resume_id='synthetic_0')
                annotation['human_review']['completed'] = False
                save(folder / 'synthetic_0/anotacoes.json', annotation)
                with self.assertRaisesRegex(ValueError, 'Revisão humana'):
                    preflight(folder)
                annotation['human_review']['completed'] = True
                save(folder / 'synthetic_0/anotacoes.json', annotation)
                save(folder / 'synthetic_0/entradas.json', [])
                with self.assertRaisesRegex(ValueError, 'Hash'):
                    preflight(folder)

    def test_reports_include_denominators_and_na(self):
        rows = [row('a', 1), row('b', gold=[]), row('a', gold=[], failure=True)]
        summary = consolidate(rows, ['a', 'b'])
        content = render(rows, summary)
        self.assertIn('N/A', content)
        self.assertIn('Falha de extração', content)
        self.assertIn('<td>b</td><td>0</td><td>N/A</td>', content)
        self.assertIn('cosseno', content)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'out'
            with patch('scripts.avaliar_amostra_semantica.private_output', return_value=target):
                write_reports(target, rows, summary, dict(commit='synthetic', pipeline_version='synthetic'), [])
            self.assertEqual({p.name for p in target.iterdir()}, {
                'resultados.json', 'comparacao.csv', 'metricas.csv', 'relatorio.html',
                'agregados_sem_dados_pessoais.json'})

    def test_selection_is_reproducible_and_does_not_replace_empty_cases(self):
        data = [dict(content=f'Synthetic CV {i}') for i in range(20)]
        excluded = [f'cv_{i:03d}_{digest(data[i]["content"].encode())[:8]}' for i in range(5)]
        with patch('scripts.avaliacao_semantica.EXCLUDED', excluded):
            first = select_sample(data)
            self.assertEqual(first, select_sample(data))
            self.assertEqual(len({x['source_index'] for x in first}), 10)
            self.assertFalse(set(excluded) & {x['resume_id'] for x in first})
            chosen = first[0]['source_index']
            data[chosen]['content'] = ''
            second = select_sample(data)
            self.assertEqual([x['source_index'] for x in first], [x['source_index'] for x in second])
            self.assertEqual(next(x['text'] for x in second if x['source_index'] == chosen), '')


if __name__ == '__main__':
    unittest.main()
