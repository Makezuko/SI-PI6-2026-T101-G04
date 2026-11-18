"""Diagnóstico de Auth com credenciais e persistência exclusivamente simuladas."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from supabase_auth.errors import AuthRetryableError
import test_web_filters as web


class LoginDiagnosticsTests(unittest.TestCase):
    setUp = web.WebFiltersTestCase.setUp
    tearDown = web.WebFiltersTestCase.tearDown
    post = web.WebFiltersTestCase.post
    login = web.WebFiltersTestCase.login

    def events(self, logs):
        return [json.loads(line[line.index('{'):]) for line in logs.output]

    def test_transport_failure_is_sanitized_and_precedes_profile_and_session(self):
        permission = PermissionError(13, 'password-token-sensitive')
        permission.winerror = 10013
        retry = AuthRetryableError('password-token-sensitive', 0)
        retry.__cause__ = permission
        class Broken:
            def sign_in_with_password(self, payload):
                raise retry
        client = SimpleNamespace(auth=Broken())
        with patch('app.routes.create_supabase_client', return_value=client), self.assertLogs(
                'talentmatch.auth', level='INFO') as logs:
            response = self.login()
        self.assertEqual(response.status_code, 503)
        error = self.events(logs)[-1]
        self.assertEqual(error['event'], 'AUTH_ERROR')
        self.assertEqual(error['stage'], 'AUTH_SIGN_IN')
        self.assertEqual(error['exceptions'][-1]['winerror'], 10013)
        for sensitive in ['password-token-sensitive', 'ana@example.test', 'password1']:
            self.assertNotIn(sensitive, '\n'.join(logs.output))
        self.assertFalse(self.db['profiles'])
        self.assertNotIn('migração', response.data.decode())

    def test_success_profiles_and_real_local_session_storage(self):
        with self.assertLogs('talentmatch.auth', level='INFO') as logs:
            self.assertEqual(self.login().status_code, 302)
        stages = [e['stage'] for e in self.events(logs)]
        for name in ['CLIENT_CREATE', 'AUTH_SIGN_IN', 'AUTH_VERIFY_USER', 'PROFILE_READ',
                     'PROFILE_CREATE', 'PROFILE_READ_AFTER_CREATE', 'SESSION_CREATE', 'SESSION_READY']:
            self.assertIn(name, stages)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['auth_user_id'], 'u1')
            self.assertIn('sb_access_token', sess)
        self.assertEqual(self.client.get('/').status_code, 200)
        with self.assertLogs('talentmatch.auth', level='INFO') as repeated:
            self.login()
        self.assertNotIn('PROFILE_CREATE', [e['stage'] for e in self.events(repeated)])

    def test_profile_read_failure_is_identified_before_session_creation(self):
        execute = web.FakeQuery.execute
        def broken(query):
            if query.table_name == 'usuarios':
                raise RuntimeError('sensitive profile payload')
            return execute(query)
        with patch.object(web.FakeQuery, 'execute', broken), self.assertLogs('talentmatch.auth', level='INFO') as logs:
            self.assertEqual(self.login().status_code, 503)
        events = self.events(logs)
        self.assertEqual(events[-1]['stage'], 'PROFILE_READ')
        self.assertNotIn('SESSION_CREATE', [e['stage'] for e in events])
        self.assertNotIn('sensitive profile payload', '\n'.join(logs.output))
