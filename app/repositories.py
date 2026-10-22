"""Consultas compatíveis com as tabelas informadas pela equipe."""
import json
from datetime import datetime

PROFILE_FIELDS = 'id,email,auth_user_id,nome,empresa,criado_em'
JOB_FIELDS = 'id,titulo,descricao,requisitos,criado_por,criado_em,status'


class LegacyProfileError(Exception):
    pass


def ensure_profile(client, user):
    response = client.table('usuarios').select(PROFILE_FIELDS).eq('auth_user_id', str(user.id)).limit(1).execute()
    if response.data:
        return response.data[0]
    metadata = user.user_metadata or {}
    try:
        response = client.table('usuarios').insert({
            'auth_user_id': str(user.id),
            'email': user.email.lower(),
            'nome': str(metadata.get('name') or user.email.split('@')[0])[:120],
            'empresa': str(metadata.get('company') or '')[:120],
        }, returning='minimal').execute()
    except Exception as error:
        if str(getattr(error, 'code', '')) == '23505':
            # Reconsulta no caso de duas requisições criarem o mesmo perfil.
            retry = client.table('usuarios').select(PROFILE_FIELDS).eq('auth_user_id', str(user.id)).limit(1).execute()
            if retry.data:
                return retry.data[0]
            raise LegacyProfileError('E-mail de um perfil antigo precisa ser vinculado ao Auth pela equipe.') from error
        raise
    response = client.table('usuarios').select(PROFILE_FIELDS).eq('auth_user_id', str(user.id)).limit(1).execute()
    if not response.data:
        raise RuntimeError('O perfil não foi retornado pelo banco. Confira a migração e o RLS.')
    return response.data[0]


def job_for_template(row):
    date = row.get('criado_em')
    try:
        display_date = datetime.fromisoformat(date.replace('Z', '+00:00')).strftime('%d/%m/%Y') if date else '—'
    except (ValueError, AttributeError):
        display_date = '—'
    return {
        'id': str(row['id']), 'title': row['titulo'],
        'description': row['descricao'], 'requirements': row['requisitos'],
        'created_at': display_date,
        'candidate_count': '—',  # Upload/análises ainda não conectados nesta etapa.
        'status': row.get('status') or 'Aberta',
    }


def list_jobs(client):
    result = []
    offset, batch_size = 0, 500
    while True:
        response = client.table('vagas').select(JOB_FIELDS).order('id', desc=True).range(offset, offset + batch_size - 1).execute()
        rows = response.data or []
        result.extend(job_for_template(row) for row in rows)
        if len(rows) < batch_size:
            return result
        offset += batch_size


def get_job(client, job_id):
    response = client.table('vagas').select(JOB_FIELDS).eq('id', job_id).limit(1).execute()
    return job_for_template(response.data[0]) if response.data else None


def create_job(client, profile_id, title, description):
    title, description = title.strip(), description.strip()
    if not title or not description:
        raise ValueError('Preencha o título e a descrição da vaga.')
    if len(title) > 200 or len(description) > 30000:
        raise ValueError('Use título de até 200 caracteres e descrição de até 30.000.')
    # Não chama isto de extração semântica: é um rascunho para revisão posterior.
    draft = {'status': 'pendente_revisao', 'items': [
        {'id': f'R{i}', 'text': line.strip()}
        for i, line in enumerate((line for line in description.splitlines() if line.strip()), 1)
    ]}
    response = client.table('vagas').insert({
        'titulo': title, 'descricao': description,
        'requisitos': json.dumps(draft, ensure_ascii=False),
        'criado_por': profile_id,
    }).execute()
    if not response.data:
        raise RuntimeError('Gravação sem retorno. Confira o banco antes de reenviar.')
    return job_for_template(response.data[0])
