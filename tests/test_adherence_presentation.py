import unittest
from copy import deepcopy
from app.presentation import candidate_text
from scripts.verificar_apresentacao_aderencia import render_fixture


class AdherencePresentationTests(unittest.TestCase):
    def test_blind_display_masks_known_name_and_contact_without_mutation(self):
        candidate = dict(status='Pendente', real_name='Pessoa Sintetica',
                         raw_text='Pessoa Sintetica\npessoa@example.test',
                         anonymized_text='[NOME OCULTO]\npessoa@example.test')
        before = deepcopy(candidate)
        displayed = candidate_text('Pessoa Sintetica criou APIs; pessoa@example.test', candidate)
        self.assertNotIn('Pessoa Sintetica', displayed)
        self.assertNotIn('pessoa@example.test', displayed)
        self.assertIn('criou APIs', displayed)
        self.assertEqual(candidate, before)
        candidate['status'] = 'Aprovado'
        self.assertEqual(candidate_text('Pessoa Sintetica', candidate), 'Pessoa Sintetica')

    def test_existing_results_are_rendered_with_simple_states_and_no_empty_fields(self):
        html = render_fixture()
        for label in ['Evidência identificada', 'Não identificado nas evidências analisadas',
                      'Requer revisão', 'Contribuição: 15,38 pontos percentuais de 15,38 possíveis.',
                      '61,54% do peso total da vaga', 'Há 3 requisitos pendentes de revisão.',
                      'Máximo possível: 84,62%', 'Experiência profissional', 'Projeto']:
            self.assertIn(label, html)
        self.assertEqual(html.count('<summary>Detalhes da análise</summary>'), 8)
        self.assertEqual(html.count('<summary>Informações técnicas</summary>'), 1)
        self.assertNotIn('Regra:', html)
        self.assertNotIn('Limitações:', html)
        self.assertNotIn('Similaridade: Indisponível', html)
