"""Estrutura dos requisitos de uma vaga (técnicos e comportamentais).

Os requisitos são gravados como JSON em texto na coluna ``vagas.requisitos``,
sem alterar o esquema do banco:

    {"versao": 2, "status": "revisado" | "pendente_revisao",
     "items": [{"id": "R1", "text": "...", "tipo": "tecnico" | "comportamental",
                "nivel": "obrigatorio" | "desejavel"}]}

O ``id`` (R1, R2, ...) é estável: não muda ao editar nem ao reordenar e nunca é
reaproveitado, para que comparações futuras com currículos possam referenciá-lo.
"""
import json
import re

TIPOS = {'tecnico': 'Técnico', 'comportamental': 'Comportamental'}
NIVEIS = {'obrigatorio': 'Obrigatório', 'desejavel': 'Desejável'}
STATUS_VAGA = ('Aberta', 'Encerrada')

SCHEMA_VERSION = 2
MAX_ITEMS = 50
MAX_TEXT = 300  # Requisitos devem ser curtos e atômicos.

_ID_PATTERN = re.compile(r'^R(\d+)$')


def clean_text(value):
    return ' '.join(str(value or '').split())


def _id_number(identifier):
    match = _ID_PATTERN.match(identifier) if isinstance(identifier, str) else None
    return int(match.group(1)) if match else None


def _assign_ids(items, known_ids=()):
    """Mantém ids válidos e únicos; atribui novos acima de qualquer id já usado."""
    used = {n for n in map(_id_number, known_ids) if n is not None}
    kept = set()
    for item in items:
        number = _id_number(item.get('id'))
        if number is not None and number not in kept:
            kept.add(number)
            used.add(number)
        else:
            item['id'] = None
    next_number = max(used, default=0) + 1
    for item in items:
        if item['id'] is None:
            item['id'] = f'R{next_number}'
            next_number += 1
    return items


def requirements_status(items):
    """'revisado' só quando há requisitos e todos estão classificados."""
    if items and all(item.get('tipo') in TIPOS for item in items):
        return 'revisado'
    return 'pendente_revisao'


def draft_from_description(description):
    """Rascunho mecânico (uma linha = um item, sem tipo). Não é extração por IA."""
    lines = (clean_text(line) for line in description.splitlines())
    items = [{'id': f'R{i}', 'text': text, 'tipo': None, 'nivel': 'obrigatorio'}
             for i, text in enumerate((l for l in lines if l), 1)]
    return {'versao': SCHEMA_VERSION, 'status': 'pendente_revisao', 'items': items}


def parse_requirements(raw):
    """Lê o valor gravado, aceitando o rascunho da etapa 1 e texto livre antigo."""
    data = raw
    if isinstance(raw, str):
        if not raw.strip():
            return {'versao': SCHEMA_VERSION, 'status': 'pendente_revisao', 'items': []}
        try:
            data = json.loads(raw)
        except ValueError:
            return draft_from_description(raw)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        return {'versao': SCHEMA_VERSION, 'status': 'pendente_revisao', 'items': []}
    items = []
    for entry in data['items']:
        if isinstance(entry, str):
            entry = {'text': entry}
        if not isinstance(entry, dict):
            continue
        text = clean_text(entry.get('text'))
        if not text:
            continue
        items.append({
            'id': entry.get('id'), 'text': text,
            'tipo': entry.get('tipo') if entry.get('tipo') in TIPOS else None,
            'nivel': entry.get('nivel') if entry.get('nivel') in NIVEIS else 'obrigatorio',
        })
    _assign_ids(items)
    return {'versao': SCHEMA_VERSION, 'status': requirements_status(items), 'items': items}


def rows_from_form(form):
    """Lê as linhas do formulário (campos repetidos e alinhados por posição)."""
    columns = [form.getlist(name) for name in ('req_id', 'req_text', 'req_tipo', 'req_nivel')]
    if len({len(column) for column in columns}) != 1:
        raise ValueError('Formulário de requisitos inválido. Recarregue a página e tente de novo.')
    return [{'id': identifier.strip(), 'text': text, 'tipo': tipo, 'nivel': nivel}
            for identifier, text, tipo, nivel in zip(*columns)]


def build_requirements(rows, known_ids=()):
    """Valida as linhas e monta a estrutura a gravar.

    Linhas sem texto são ignoradas. ``known_ids`` são os ids já gravados na vaga,
    para que um id removido não seja reutilizado por um requisito novo.
    """
    items, seen = [], set()
    for row in rows:
        text = clean_text(row.get('text'))
        if not text:
            continue
        if len(text) > MAX_TEXT:
            raise ValueError(f'Cada requisito deve ter até {MAX_TEXT} caracteres: "{text[:40]}…"')
        tipo = row.get('tipo')
        if tipo not in TIPOS:
            raise ValueError(f'Classifique como técnico ou comportamental o requisito: "{text[:60]}"')
        nivel = row.get('nivel') or 'obrigatorio'
        if nivel not in NIVEIS:
            raise ValueError('Nível de requisito inválido.')
        key = (text.casefold(), tipo)
        if key in seen:
            continue
        seen.add(key)
        items.append({'id': row.get('id'), 'text': text, 'tipo': tipo, 'nivel': nivel})
    if len(items) > MAX_ITEMS:
        raise ValueError(f'Use no máximo {MAX_ITEMS} requisitos por vaga.')
    _assign_ids(items, known_ids)
    return {'versao': SCHEMA_VERSION, 'status': requirements_status(items), 'items': items}


def serialize(requirements):
    return json.dumps(requirements, ensure_ascii=False)
