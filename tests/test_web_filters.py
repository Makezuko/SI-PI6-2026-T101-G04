"""Testes da etapa Auth/vagas, com Supabase simulado e os HTMLs existentes."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('FLASK_SECRET_KEY', 'test-only-secret-not-for-deployment')

from app import app
from app.repositories import PROFILE_FIELDS
from supabase_auth.errors import AuthApiError


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table_name = client, table
        self.filters, self.payload, self.columns = {}, None, None
        self.limit_value, self.bounds, self.desc = None, None, False
        self.returning, self.update_payload = 'representation', None

    def select(self, columns): self.columns = columns; return self
    def eq(self, key, value): self.filters[key] = value; return self
    def limit(self, value): self.limit_value = value; return self
    def order(self, key, desc=False): self.desc = desc; return self
    def range(self, start, end): self.bounds = (start, end); return self
    def insert(self, value, returning='representation'):
        self.payload, self.returning = value, returning
        return self
    def update(self, value):
        assert set(value) <= {'titulo', 'descricao', 'requisitos', 'status'}
        self.update_payload = value
        return self

    def execute(self):
        db, uid = self.client.db, self.client.uid
        if self.table_name == 'usuarios':
            rows = db['profiles']
            visible = [r for r in rows if r['auth_user_id'] == uid]
        else:
            rows = db['jobs']
            profile_ids = {r['id'] for r in db['profiles'] if r['auth_user_id'] == uid}
            visible = [r for r in rows if r['criado_por'] in profile_ids]
        if self.payload is not None:
            if self.table_name == 'vagas' and db.get('fail_insert'):
                raise RuntimeError('database unavailable')
            value = dict(self.payload)
            if self.table_name == 'usuarios':
                assert value['auth_user_id'] == uid
                assert self.returning == 'minimal', 'Não retornar senha_hash na criação de perfil.'
            else:
                assert value['criado_por'] in profile_ids
            value.update(id=len(rows)+1, criado_em='2026-10-22T10:00:00')
            if self.table_name == 'vagas': value['status'] = 'Aberta'
            rows.append(value)
            return SimpleNamespace(data=[] if self.returning == 'minimal' else [dict(value)])
        for key, value in self.filters.items():
            visible = [r for r in visible if str(r.get(key)) == str(value)]
        if self.update_payload is not None:
            if db.get('fail_update'):
                raise RuntimeError('database unavailable')
            for row in visible: row.update(self.update_payload)
            return SimpleNamespace(data=[dict(r) for r in visible])
        if self.desc: visible = sorted(visible, key=lambda r:r['id'], reverse=True)
        if self.bounds: visible = visible[self.bounds[0]:self.bounds[1]+1]
        if self.limit_value is not None: visible = visible[:self.limit_value]
        if self.table_name == 'usuarios': assert self.columns == PROFILE_FIELDS
        return SimpleNamespace(data=[dict(r) for r in visible])


class FakeClient:
    def __init__(self, db): self.db, self.uid, self.auth = db, None, self
    def table(self, name): return FakeQuery(self, name)
    def user(self):
        info = self.db['users'][self.uid]
        return SimpleNamespace(id=self.uid, email=info['email'], user_metadata=info.get('metadata', {}))
    def response(self):
        return SimpleNamespace(user=self.user(), session=SimpleNamespace(access_token='access-'+self.uid, refresh_token='refresh-'+self.uid))
    def sign_in_with_password(self, values):
        for uid, info in self.db['users'].items():
            if info['email'] == values['email'] and info['password'] == values['password']:
                self.uid = uid
                return self.response()
        raise AuthApiError('invalid', 400, 'invalid_credentials')
    def set_session(self, access, refresh):
        uid=access.removeprefix('access-')
        if uid not in self.db['users'] or refresh != 'refresh-'+uid:
            raise AuthApiError('invalid', 401, 'invalid_token')
        self.uid=uid
        return self.response()
    def get_user(self, token): return SimpleNamespace(user=self.user())
    def sign_up(self, values):
        if self.db.get('confirmation_required'):
            return SimpleNamespace(user=None, session=None)
        self.uid = 'new-user'
        self.db['users'][self.uid] = {'email':values['email'], 'password':values['password'], 'metadata':values['options']['data']}
        return self.response()
    def sign_out(self, *args): pass


class WebFiltersTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.tmp=tempfile.TemporaryDirectory()
        from cachelib import FileSystemCache
        self.previous_cache=app.session_interface.cache
        app.session_interface.cache=FileSystemCache(self.tmp.name, mode=0o600)
        self.db={'profiles':[], 'jobs':[], 'users':{
            'u1':{'email':'ana@example.test','password':'password1'},
            'u2':{'email':'bia@example.test','password':'password2'},
        }}
        self.patch=patch('app.routes.create_supabase_client', side_effect=lambda:FakeClient(self.db))
        self.patch.start()
        self.client=app.test_client()

    def tearDown(self):
        self.patch.stop()
        app.session_interface.cache=self.previous_cache
        self.tmp.cleanup()

    def post(self, path, data, client=None):
        return (client or self.client).post(path,data=data,headers={'Origin':'http://localhost'})
    def login(self, client=None, email='ana@example.test', password='password1'):
        return self.post('/login',{'email':email,'password':password},client)
    def create(self, title='Vaga de teste'):
        return self.post('/nova-vaga',{'title':title,'description':'Python\nSQL'})

    def test_requires_real_session(self):
        with self.client.session_transaction() as sess: sess['user_email']='mock@example.test'
        self.assertEqual(self.client.get('/').status_code,302)
    def test_invalid_login(self):
        self.assertEqual(self.login(password='wrong').status_code,401)
        self.assertFalse(self.db['profiles'])
    def test_profile_and_server_side_session(self):
        response=self.login()
        self.assertEqual(response.status_code,302)
        self.assertEqual(len(self.db['profiles']),1)
        self.assertNotIn('password',self.db['profiles'][0])
        self.assertNotIn('senha_hash',self.db['profiles'][0])
        self.assertNotIn('access-u1',str(response.headers.getlist('Set-Cookie')))
        self.assertEqual(self.client.get('/').status_code,200)
    def test_create_and_reopen_job(self):
        self.login();response=self.create()
        self.assertEqual(response.status_code,302)
        row=self.db['jobs'][0]
        self.assertEqual(row['descricao'],'Python\nSQL')
        self.assertEqual(row['criado_por'],self.db['profiles'][0]['id'])
        self.assertEqual(json.loads(row['requisitos'])['status'],'pendente_revisao')
        self.assertIn(b'Vaga de teste',self.client.get('/').data)
        self.assertEqual(self.client.get('/vagas/1').status_code,200)
    def test_persists_after_logout(self):
        self.login();self.create();self.client.get('/logout');self.login()
        self.assertIn(b'Vaga de teste',self.client.get('/').data)
        self.assertEqual(len(self.db['jobs']),1)
    def test_other_owner_not_visible(self):
        self.login();self.create()
        second=app.test_client()
        self.login(second,'bia@example.test','password2')
        self.assertEqual(second.get('/vagas/1').status_code,404)
        self.assertNotIn(b'Vaga de teste',second.get('/').data)
    def test_invalid_job_does_not_fallback(self):
        self.login();self.create()
        for identifier in ['999','abc','-1']:
            self.assertEqual(self.client.get('/vagas/'+identifier).status_code,404)
    def test_save_failure_not_success(self):
        self.login();self.db['fail_insert']=True
        response=self.create()
        self.assertEqual(response.status_code,503)
        self.assertFalse(self.db['jobs'])
    def test_empty_job_rejected(self):
        self.login()
        self.assertEqual(self.post('/nova-vaga',{'title':'','description':''}).status_code,400)
        self.assertFalse(self.db['jobs'])
    def test_no_fake_upload(self):
        self.login();self.create()
        response=self.post('/vagas/1/adicionar-curriculos',{'selected_candidates':['5']})
        self.assertEqual(response.status_code,501)
    def test_original_filters_render(self):
        self.login();self.create()
        page=self.client.get('/vagas/1').data.decode()
        for identifier in ['filter-search','filter-status','filter-date','filter-sort','select-job-rank']:
            self.assertIn('id="'+identifier+'"',page)
        upload=self.client.get('/vagas/1/adicionar-curriculos').data.decode()
        for identifier in ['triagem-search','triagem-status','triagem-date','btn-ver-ranking']:
            self.assertIn('id="'+identifier+'"',upload)
    def test_email_confirmation_does_not_login(self):
        self.db['confirmation_required']=True
        response=self.post('/cadastro',{'name':'Ana','company':'Empresa','email':'new@example.test','password':'password123','password_confirm':'password123'})
        self.assertEqual(response.status_code,200)
        with self.client.session_transaction() as sess:self.assertNotIn('sb_access_token',sess)
    def test_signup_without_confirmation_session(self):
        response=self.post('/cadastro',{'name':'Ana','company':'Empresa','email':'new@example.test','password':'password123','password_confirm':'password123'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.db['profiles'][0]['nome'],'Ana')
    def test_cross_origin_rejected(self):
        self.login()
        response=self.client.post('/nova-vaga',data={'title':'X','description':'Y'},headers={'Origin':'https://other.test'})
        self.assertEqual(response.status_code,403)
    def test_no_origin_rejected(self):
        self.assertEqual(self.client.post('/login',data={'email':'a','password':'b'}).status_code,403)
    def test_logout_clears_local_session(self):
        self.login();self.client.get('/logout')
        with self.client.session_transaction() as sess:self.assertNotIn('sb_access_token',sess)
    def test_vagas_redirects_to_first_job(self):
        self.login();self.create()
        response=self.client.get('/vagas')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.headers['Location'],'/vagas/1')
    def test_edit_job_prefilled_and_updates(self):
        self.login();self.create()
        get_res=self.client.get('/vagas/1/editar')
        self.assertEqual(get_res.status_code,200)
        self.assertIn('Vaga de teste',get_res.data.decode())
        post_res=self.post('/vagas/1/editar',{'title':'Vaga Atualizada','description':'Python avançado','status':'Encerrada'})
        self.assertEqual(post_res.status_code,302)
        row=self.db['jobs'][0]
        self.assertEqual(row['titulo'],'Vaga Atualizada')
        self.assertEqual(row['status'],'Encerrada')
        self.assertEqual(row['descricao'],'Python avançado')
    def test_edit_other_owner_job_forbidden(self):
        self.login();self.create()
        second=app.test_client();self.login(second,'bia@example.test','password2')
        self.assertEqual(second.get('/vagas/1/editar').status_code,404)
        self.assertEqual(self.post('/vagas/1/editar',{'title':'Hacked','description':'X','status':'Aberta'},second).status_code,404)
        self.assertEqual(self.db['jobs'][0]['titulo'],'Vaga de teste')
    def test_create_and_edit_job_with_classified_requirements(self):
        self.login()
        res=self.post('/nova-vaga',{
            'title':'Vaga Completa','description':'Texto da vaga',
            'req_id':['',''],'req_text':['Python','Trabalho em equipe'],
            'req_tipo':['tecnico','comportamental'],'req_nivel':['obrigatorio','desejavel'],
        })
        self.assertEqual(res.status_code,302)
        job=self.db['jobs'][-1]
        import json
        reqs=json.loads(job['requisitos'])
        self.assertEqual(reqs['status'],'revisado')
        self.assertEqual(len(reqs['items']),2)
        self.assertEqual(reqs['items'][0]['tipo'],'tecnico')
        self.assertEqual(reqs['items'][1]['tipo'],'comportamental')
        res_edit=self.post(f"/vagas/{job['id']}/editar",{
            'title':'Vaga Completa','description':'Texto da vaga','status':'Aberta',
            'req_id':[reqs['items'][0]['id'],''],'req_text':['Python Avançado','Comunicação'],
            'req_tipo':['tecnico','comportamental'],'req_nivel':['obrigatorio','obrigatorio'],
        })
        self.assertEqual(res_edit.status_code,302)
        updated=json.loads(self.db['jobs'][-1]['requisitos'])
        self.assertEqual(updated['items'][0]['id'],'R1')
        self.assertEqual(updated['items'][0]['text'],'Python Avançado')
        self.assertEqual(updated['items'][1]['id'],'R3')

if __name__=='__main__': unittest.main()
