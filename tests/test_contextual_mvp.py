import copy
import unittest
from unittest.mock import patch

from app.analysis import AnalysisError, analyze, versions
from src.matching.adherence import calculate_adherence


class ContextualMvpTests(unittest.TestCase):
    def setUp(self):
        self.job = {'requirements_data': {'items': [
            {'id': 'R1', 'text': 'Python', 'tipo': 'tecnico', 'nivel': 'obrigatorio'}]}}
        self.resume = {'raw_text': 'Experiência com Python'}

    def test_missing_contextual_configuration_never_loads_models(self):
        with patch('app.analysis.configuration', return_value={'contextual': {'enabled': False}}), \
             patch('app.analysis.load_models') as models:
            with self.assertRaisesRegex(AnalysisError, 'contextual'):
                analyze(self.job, self.resume)
            models.assert_not_called()

    def test_legacy_condition_does_not_change_fingerprint(self):
        changed = copy.deepcopy(self.job)
        changed['requirements_data']['items'][0]['condition'] = {'arbitrary': 'legacy'}
        self.assertEqual(versions(self.job, self.resume), versions(changed, self.resume))

    def test_weights_and_formula(self):
        reqs = [dict(id='R1', text='Python', nivel='obrigatorio'),
                dict(id='R2', text='SQL', nivel='desejavel')]
        decisions = [dict(id='R1', estado='atendido', justificativa='Comprovado',
                          evidencias=[dict(text='Python', source='skill')]),
                     dict(id='R2', estado='nao_identificado', justificativa='Ausente', evidencias=[])]
        result = calculate_adherence(reqs, decisions)
        self.assertEqual(result['weights'], {'obrigatorio': 2.0, 'desejavel': 1.0})
        self.assertAlmostEqual(result['score'], 200 / 3)


if __name__ == '__main__':
    unittest.main()
