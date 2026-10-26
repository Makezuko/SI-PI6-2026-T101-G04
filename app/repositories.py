"""Consultas compatíveis com as tabelas informadas pela equipe."""
from datetime import datetime

from app.requisitos import STATUS_VAGA, draft_from_description, parse_requirements, serialize

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
    requirements = parse_requirements(row.get('requisitos'))
    items = requirements['items']
    return {
        'id': str(row['id']), 'title': row['titulo'],
        'description': row['descricao'], 'requirements': row['requisitos'],
        'requirements_data': requirements,
        'requirements_status': requirements['status'],
        'technical': [item for item in items if item['tipo'] == 'tecnico'],
        'behavioral': [item for item in items if item['tipo'] == 'comportamental'],
        'unclassified': [item for item in items if item['tipo'] is None],
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


def validate_job_text(title, description):
    title, description = title.strip(), description.strip()
    if not title or not description:
        raise ValueError('Preencha o título e a descrição da vaga.')
    if len(title) > 200 or len(description) > 30000:
        raise ValueError('Use título de até 200 caracteres e descrição de até 30.000.')
    return title, description


def create_job(client, profile_id, title, description, requirements=None):
    """Grava a vaga. ``requirements`` é a estrutura de app.requisitos.build_requirements.

    Sem ela, grava só um rascunho mecânico (uma linha da descrição por item), que não
    é extração por IA nem requisitos confirmados.
    """
    title, description = validate_job_text(title, description)
    if requirements is None:
        requirements = draft_from_description(description)
    response = client.table('vagas').insert({
        'titulo': title, 'descricao': description,
        'requisitos': serialize(requirements),
        'criado_por': profile_id,
    }).execute()
    if not response.data:
        raise RuntimeError('Gravação sem retorno. Confira o banco antes de reenviar.')
    return job_for_template(response.data[0])


def update_job(client, job_id, title, description, status, requirements=None):
    """Atualiza a vaga do próprio usuário (RLS). Sem ``requirements``, não os altera.

    Levanta LookupError se nenhuma linha for alterada: como a vaga já foi lida pelo
    mesmo usuário, isso indica falta da política de UPDATE (sql/002_editar_vagas.sql).
    """
    title, description = validate_job_text(title, description)
    if status not in STATUS_VAGA:
        raise ValueError('Status inválido.')
    values = {'titulo': title, 'descricao': description, 'status': status}
    if requirements is not None:
        values['requisitos'] = serialize(requirements)
    response = client.table('vagas').update(values).eq('id', job_id).execute()
    if not response.data:
        raise LookupError('Nenhuma linha foi alterada. Confira a migração sql/002_editar_vagas.sql.')
    return job_for_template(response.data[0])
