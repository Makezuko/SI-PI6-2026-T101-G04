import json
import pickle
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.gerar_resultados_visuais import (decimal, main, numero_pt, percent, percentual_pt, read_json,
                                               read_training_args, synthetic_evidence, validate_metrics, validate_ranking)


class VisualResultsTests(unittest.TestCase):
    def test_synthetic_evidence_includes_uncited_conflicting_entry(self):
        evidence = [{'id': 'e1', 'text': 'Inglês avançado'}, {'id': 'e2', 'text': 'Inglês básico'}]
        case = {'evidence': evidence, 'verdict': {'evidence_ids': ['e1']}}
        result = synthetic_evidence(case, {'evidence': evidence})
        self.assertIn('e1: Inglês avançado', result)
        self.assertIn('e2: Inglês básico', result)
        self.assertNotIn('Inglês', synthetic_evidence(case, {'evidence': []}))

    def test_ner_protocol_and_missing_values(self):
        data = dict(evaluation_scope='document_consolidated', split='train', train_subset='original',
                    precision=.5, recall=.25, f1=1/3, accuracy=None)
        self.assertIs(validate_metrics(data, 'train_original'), data)
        self.assertEqual(percent(None), 'N/D')
        self.assertEqual(percent(.5), '50.0%')
        self.assertEqual(decimal(.123456, 4), '0.1235')
        self.assertEqual(decimal(27.312, 2), '27.31')
        self.assertEqual(decimal(None, 2), 'N/D')
        self.assertEqual(percentual_pt(.37037037037), '37,04%')
        self.assertEqual(numero_pt(.9014608, 3), '0,901')
        self.assertEqual(percentual_pt(None), 'N/D')
        with self.assertRaises(ValueError):
            validate_metrics(dict(data, train_subset='all'), 'train_original')
        with self.assertRaises(ValueError):
            validate_metrics(dict(data, evaluation_scope='window'), 'train_original')

    def test_ranking_denominators_and_units(self):
        group = dict(denominator=2, evaluated_positive_count=2, hit_at_1=.5, hit_at_3=1, mrr=.75)
        validate_ranking(dict(overall=group, ranking_only=group))
        with self.assertRaises(ValueError):
            validate_ranking(dict(overall=dict(group, denominator=3), ranking_only=group))
        with self.assertRaises(ValueError):
            validate_ranking(dict(overall=dict(group, mrr=75), ranking_only=group))

    def test_sources_are_hashed_and_missing_not_zero(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'data.json'
            path.write_text(json.dumps({'value': 0}), encoding='utf-8')
            sources = {}
            self.assertEqual(read_json(path, sources), {'value': 0})
            self.assertEqual(len(sources[str(path)]), 64)
            self.assertIsNone(read_json(path.parent / 'missing.json', sources))

    def test_training_args_extracts_literals_without_loading_pickle(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'training_args.bin'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('archive/data.pkl', pickle.dumps({'per_device_train_batch_size': 2,
                                 'gradient_accumulation_steps': 4, 'learning_rate': 2e-5}, protocol=2))
            sources = {}
            values = read_training_args(path, sources)
            self.assertEqual(values['per_device_train_batch_size'], 2)
            self.assertEqual(values['gradient_accumulation_steps'], 4)
            self.assertEqual(values['learning_rate'], 2e-5)
            self.assertIn(str(path), sources)

    def test_missing_sources_generate_offline_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'out'
            main(['--ner-dir', str(root / 'ner'), '--ner-models', str(root / 'models'),
                  '--ner-preparation', str(root / 'preparation.json'),
                  '--ner-split-manifest', str(root / 'splits.json'),
                  '--reevaluation', str(root / 'reevaluation.json'),
                  '--semantic-dir', str(root / 'semantic'), '--manifest', str(root / 'manifest.json'),
                  '--contextual-local', str(root / 'local.json'), '--contextual-operational', str(root / 'op.json'),
                  '--output-dir', str(output)])
            provenance = json.loads((output / 'fontes.json').read_text(encoding='utf-8'))
            self.assertTrue(provenance['missing'])
            self.assertIn('indisponíveis', (output / 'relatorio.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
