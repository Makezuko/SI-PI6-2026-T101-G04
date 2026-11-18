import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('FLASK_SECRET_KEY', 'test-only-secret-not-for-deployment')

from cachelib import FileSystemCache
from app import app
from app.supabase_client import _http_client
import test_web_filters as web


class PerformancePathsTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_cache = app.session_interface.cache
        app.session_interface.cache = FileSystemCache(self.tmp.name, mode=0o600)
        self.db = {
            'profiles': [],
            'jobs': [],
            'resumes': [],
            'analyses': [],
            'users': {
                'u1': {'email': 'ana@example.test', 'password': 'password1'},
            },
        }
        self.patch = patch('app.routes.create_supabase_client', side_effect=lambda: web.FakeClient(self.db))
        self.patch.start()
        self.client = app.test_client()

    def tearDown(self):
        self.patch.stop()
        app.session_interface.cache = self.previous_cache
        self.tmp.cleanup()

    def post(self, path, data):
        return self.client.post(path, data=data, headers={'Origin': 'http://localhost'})

    def login(self):
        return self.post('/login', {'email': 'ana@example.test', 'password': 'password1'})

    def create_job(self, title='Vaga de teste'):
        return self.post('/nova-vaga', {'title': title, 'description': 'Python\nSQL'})

    def test_thread_http_client_is_reused(self):
        c1 = _http_client()
        c2 = _http_client()
        self.assertIs(c1, c2)

    def test_login_required_skips_redundant_get_user_and_profile_query_when_cached(self):
        self.login()
        called = {'get_user': 0, 'usuarios': 0}
        orig_get_user = web.FakeClient.get_user
        orig_execute = web.FakeQuery.execute

        def spy_get_user(client_self, token):
            called['get_user'] += 1
            return orig_get_user(client_self, token)

        def spy_execute(query_self):
            if query_self.table_name == 'usuarios':
                called['usuarios'] += 1
            return orig_execute(query_self)

        with patch.object(web.FakeClient, 'get_user', spy_get_user), \
                patch.object(web.FakeQuery, 'execute', spy_execute):
            resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(called['get_user'], 0)
        self.assertEqual(called['usuarios'], 0)

    def test_vagas_does_not_call_get_job_when_already_in_list(self):
        self.login()
        self.create_job('Backend Python')
        with patch('app.routes.get_job', side_effect=AssertionError('get_job should not be called')) as mocked_get:
            resp = self.client.get('/vagas/1')
        self.assertEqual(resp.status_code, 200)
        mocked_get.assert_not_called()

    def test_dashboard_uses_batch_queries_without_n_plus_one_or_resume_parsing(self):
        self.login()
        self.create_job('Vaga 1')
        self.create_job('Vaga 2')
        self.create_job('Vaga 3')

        queries = {'curriculos': 0, 'analises_aderencia': 0}
        orig_execute = web.FakeQuery.execute

        def spy_execute(query_self):
            if query_self.table_name in queries:
                queries[query_self.table_name] += 1
            return orig_execute(query_self)

        with patch.object(web.FakeQuery, 'execute', spy_execute), \
                patch('app.repositories.extract_skills', side_effect=AssertionError('extract_skills must not run on dashboard')):
            resp = self.client.get('/')

        self.assertEqual(resp.status_code, 200)
        # 1 query em list_jobs (contagem) + 1 query batch em dashboard_scores = 2 no total para 3 vagas
        self.assertEqual(queries['curriculos'], 2)
        self.assertEqual(queries['analises_aderencia'], 1)


if __name__ == '__main__':
    unittest.main()
