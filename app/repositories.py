"""Consultas compatíveis com as tabelas informadas pela equipe."""
from datetime import datetime
from pathlib import Path
import re

from app.requisitos import STATUS_VAGA, draft_from_description, parse_requirements, serialize
from src.data.clean import extract_contact_info, extract_education_blocks
from src.nlp.skills_extractor import extract_skills

PROFILE_FIELDS = 'id,email,auth_user_id,nome,empresa,criado_em'
JOB_FIELDS = 'id,titulo,descricao,requisitos,criado_por,criado_em,status'
RESUME_FIELDS = 'id,vaga_id,nome_arquivo,texto_extraido,texto_anonimizado,status,enviado_em'


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
        'candidate_count': 0,
        'status': row.get('status') or 'Aberta',
    }


def resume_for_template(row):
    date = row.get('enviado_em')
    try:
        display_date = datetime.fromisoformat(date.replace('Z', '+00:00')).strftime('%d/%m/%Y') if date else '—'
    except (ValueError, AttributeError):
        display_date = '—'

    text = row.get('texto_extraido') or ''
    filename = row.get('nome_arquivo') or 'curriculo.pdf'
    clean_name = Path(filename).stem.replace('_', ' ').replace('-', ' ').title()

    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:5]
    name = clean_name
    if first_lines and len(first_lines[0].split()) <= 4 and re.search(r'^[A-Za-zÀ-ÖØ-öø-ÿ\s]+$', first_lines[0]):
        name = first_lines[0].title()

    initials = ''.join(part[0] for part in name.split()[:2]).upper() or 'CV'
    contact = extract_contact_info(text) if text else {'email': None, 'phone': None}
    education_blocks = extract_education_blocks(text) if text else []
    skills_data = extract_skills(text=text) if text else {'skills': [], 'context_blocks': []}

    skills = skills_data.get('skills', [])
    education = education_blocks[0]['text'].splitlines()[0] if education_blocks else 'Não especificada'
    context_blocks = skills_data.get('context_blocks', [])
    last_role = context_blocks[0]['text'].splitlines()[0] if context_blocks else 'Não especificada'

    return {
        'id': str(row['id']),
        'job_id': str(row.get('vaga_id', '')),
        'name': name,
        'initials': initials,
        'score': 80,
        'filename': filename,
        'submitted_at': display_date,
        'status': row.get('status') or 'Analisado',
        'email': contact.get('email') or 'contato@candidato.com',
        'phone': contact.get('phone') or 'Telefone não informado',
        'education': education,
        'last_role': last_role,
        'skills': skills,
        'met': skills[:4] if skills else ['Requisitos Básicos da Vaga'],
        'missing': ['Certificações adicionais'],
        'raw_text': text,
        'anonymized_text': row.get('texto_anonimizado') or '',
    }


def list_jobs(client):
    result = []
    offset, batch_size = 0, 500
    while True:
        response = client.table('vagas').select(JOB_FIELDS).order('id', desc=True).range(offset, offset + batch_size - 1).execute()
        rows = response.data or []
        result.extend(job_for_template(row) for row in rows)
        if len(rows) < batch_size:
            break
        offset += batch_size

    try:
        resumes_resp = client.table('curriculos').select('vaga_id').execute()
        counts = {}
        for r in (resumes_resp.data or []):
            vid = str(r.get('vaga_id'))
            counts[vid] = counts.get(vid, 0) + 1
        for j in result:
            j['candidate_count'] = counts.get(j['id'], 0)
    except Exception:
        pass

    return result


def get_job(client, job_id):
    response = client.table('vagas').select(JOB_FIELDS).eq('id', job_id).limit(1).execute()
    if not response.data:
        return None
    job = job_for_template(response.data[0])
    try:
        resumes_resp = client.table('curriculos').select('id').eq('vaga_id', int(job_id)).execute()
        job['candidate_count'] = len(resumes_resp.data or [])
    except Exception:
        pass
    return job


def validate_job_text(title, description):
    title, description = title.strip(), description.strip()
    if not title or not description:
        raise ValueError('Preencha o título e a descrição da vaga.')
    if len(title) > 200 or len(description) > 30000:
        raise ValueError('Use título de até 200 caracteres e descrição de até 30.000.')
    return title, description


def create_job(client, profile_id, title, description, requirements=None):
    title, description = validate_job_text(title, description)
    if not requirements or not requirements.get('items'):
        requirements = draft_from_description(description)
    response = client.table('vagas').insert({
        'titulo': title, 'descricao': description,
        'requisitos': serialize(requirements),
        'criado_por': profile_id,
    }).execute()
    if not response.data:
        raise RuntimeError('Gravação sem retorno. Confira o banco antes de reenviar.')
    return job_for_template(response.data[0])


def update_job(client, job_id, title, description, status='Aberta', requirements=None):
    title, description = validate_job_text(title, description)
    if status not in STATUS_VAGA:
        raise ValueError('Status inválido.')
    values = {'titulo': title, 'descricao': description, 'status': status}
    if requirements is not None:
        if not requirements.get('items'):
            requirements = draft_from_description(description)
        values['requisitos'] = serialize(requirements)
    response = client.table('vagas').update(values).eq('id', job_id).execute()
    if not response.data:
        raise LookupError('Nenhuma linha foi alterada. Confira a migração sql/002_editar_vagas.sql.')
    return job_for_template(response.data[0])


def list_resumes(client, job_id):
    response = client.table('curriculos').select(RESUME_FIELDS).eq('vaga_id', int(job_id)).order('id', desc=True).execute()
    rows = response.data or []
    return [resume_for_template(row) for row in rows]


def get_resume(client, job_id, resume_id):
    response = client.table('curriculos').select(RESUME_FIELDS).eq('vaga_id', int(job_id)).eq('id', int(resume_id)).limit(1).execute()
    return resume_for_template(response.data[0]) if response.data else None


def create_resume(client, job_id, filename, raw_text, anonymized_text, status='Analisado'):
    response = client.table('curriculos').insert({
        'vaga_id': int(job_id),
        'nome_arquivo': filename,
        'texto_extraido': raw_text,
        'texto_anonimizado': anonymized_text,
        'status': status,
    }).execute()
    if not response.data:
        raise RuntimeError('Gravação do currículo sem retorno. Confira o banco.')
    return resume_for_template(response.data[0])


def update_resume_status(client, job_id, resume_id, status):
    if status not in ('Aprovado', 'Descartado', 'Analisado', 'Pendente'):
        raise ValueError('Status de currículo inválido.')
    response = client.table('curriculos').update({'status': status}).eq('vaga_id', int(job_id)).eq('id', int(resume_id)).execute()
    if not response.data:
        raise LookupError('Nenhum currículo alterado. Confira o RLS.')
    return resume_for_template(response.data[0])
