import sys
from pathlib import Path
import unittest

# Adiciona a raiz do projeto ao sys.path para garantir portabilidade
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import app
from app.routes import JOBS, CANDIDATES_BY_JOB

class WebFiltersTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_email'] = 'carlos@nexora.com'
            sess['user_name'] = 'Carlos Andrade'
            sess['user_role'] = 'RH Sênior'
            sess['user_initials'] = 'CA'

    def test_vagas_page_renders_with_filters(self):
        response = self.client.get('/vagas/1')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        # Verifica se os elementos de filtro estão presentes
        self.assertIn('id="filter-search"', content)
        self.assertIn('id="filter-status"', content)
        self.assertIn('id="filter-date"', content)
        self.assertIn('id="filter-sort"', content)
        self.assertIn('id="select-job-rank"', content)
        # Verifica se os novos atributos e badges estão no HTML
        self.assertIn('data-filename', content)
        self.assertIn('data-status', content)
        self.assertIn('data-date', content)

    def test_adicionar_curriculos_page_renders_selection_and_filters(self):
        response = self.client.get('/vagas/1/adicionar-curriculos')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        # Verifica se os seletores e checkboxes estão presentes
        self.assertIn('id="triagem-search"', content)
        self.assertIn('id="triagem-status"', content)
        self.assertIn('id="triagem-date"', content)
        self.assertIn('id="check-all"', content)
        self.assertIn('name="selected_candidates"', content)
        self.assertIn('id="btn-ver-ranking"', content)

    def test_adicionar_curriculos_post_updates_status_and_redirects(self):
        # Envia seleção de candidato pendente (id 5)
        response = self.client.post('/vagas/1/adicionar-curriculos', data={
            'job_id': '1',
            'selected_candidates': ['5']
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        # Verifica se o candidato 5 agora é Analisado
        cands = CANDIDATES_BY_JOB['1']
        cand5 = next(c for c in cands if c['id'] == '5')
        self.assertEqual(cand5['status'], 'Analisado')

    def test_atualizar_status_candidato(self):
        response = self.client.post('/vagas/1/candidato/1/status', data={
            'status': 'Aprovado'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        cand1 = next(c for c in CANDIDATES_BY_JOB['1'] if c['id'] == '1')
        self.assertEqual(cand1['status'], 'Aprovado')

if __name__ == '__main__':
    unittest.main()
