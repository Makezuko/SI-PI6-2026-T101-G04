import unittest

from src.matching.adherence import calculate_adherence, evaluate_requirements


class AdherenceTests(unittest.TestCase):
    def requirements(self, levels):
        return [dict(id=str(i), text='Python', nivel=level) for i, level in enumerate(levels)]

    def decisions(self, states):
        return [dict(id=str(i), estado=state, justificativa='Revisado documentalmente',
                     origem='humana', evidencias=[dict(text='Python', source='skill')])
                for i, state in enumerate(states)]

    def test_six_of_eight_equal_weights(self):
        result = calculate_adherence(self.requirements(['obrigatorio'] * 8),
                                    self.decisions(['atendido'] * 6 + ['nao_identificado'] * 2))
        self.assertEqual(result['score'], 75)
        self.assertEqual(result['mandatory_alert_ids'], ['6', '7'])

    def test_default_weights_and_provisional_interval(self):
        result = calculate_adherence(self.requirements(['obrigatorio', 'obrigatorio', 'desejavel']),
                                    self.decisions(['atendido', 'revisao_necessaria', 'nao_identificado']))
        self.assertEqual(result['weights'], {'obrigatorio': 2, 'desejavel': 1})
        self.assertEqual(result['score'], 40)
        self.assertEqual(result['maximum_score'], 80)
        self.assertTrue(result['provisional'])
        self.assertEqual(result['mandatory_alert_ids'], ['1'])

    def test_missing_decision_and_invalid_weights_are_errors(self):
        requirements = self.requirements(['obrigatorio'])
        with self.assertRaises(ValueError):
            calculate_adherence(requirements, [])
        for weight in (True, 0, -1, float('nan')):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                calculate_adherence(requirements, self.decisions(['atendido']), {'obrigatorio': weight})

    def test_cosine_does_not_contribute_and_ambiguous_mentions_need_review(self):
        requirements = self.requirements(['obrigatorio'])
        def result(text, cosine):
            return [dict(id='0', top_similarity=cosine, ranking=[dict(text=text, source='skill',
                         similarity=cosine, input_index=0, chunk_index=0)])]
        for cosine in (.1, .99):
            decisions = evaluate_requirements(requirements, result('Python', cosine))
            self.assertEqual(calculate_adherence(requirements, decisions)['score'], 100)
        for text in ('No Python experience', 'Learning Python', 'Python development planned', 'Next.js'):
            decisions = evaluate_requirements(requirements, result(text, .99))
            self.assertEqual(decisions[0]['estado'], 'revisao_necessaria')
        requirements[0]['text'] = 'Git e Docker'
        self.assertEqual(evaluate_requirements(requirements, result('Git, Docker', 1))[0]['estado'],
                         'revisao_necessaria')

    def test_retrieval_failure_is_not_zero(self):
        with self.assertRaises(ValueError):
            evaluate_requirements(self.requirements(['obrigatorio']),
                                  [dict(id='0', top_similarity=None, ranking=[])])

    def test_human_review_recalculates_without_mutating_previous_decisions(self):
        requirements = self.requirements(['obrigatorio', 'obrigatorio', 'desejavel'])
        decisions = self.decisions(['atendido', 'revisao_necessaria', 'nao_identificado'])
        previous = calculate_adherence(requirements, decisions)
        decisions[1]['estado'] = 'atendido'
        revised = calculate_adherence(requirements, decisions)
        self.assertEqual(previous['score'], 40)
        self.assertEqual(previous['details'][1]['estado'], 'revisao_necessaria')
        self.assertEqual(revised['score'], 80)
        self.assertFalse(revised['provisional'])


if __name__ == '__main__':
    unittest.main()
