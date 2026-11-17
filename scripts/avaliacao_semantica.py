"""Contratos da avaliação ampliada; sem dependência da aplicação ou de .env."""
import ast
import hashlib
import json
import random
import subprocess
from pathlib import Path

from src.matching.semantic import evaluate_ranking

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / 'data/processed/splits/validation.json'
EXCLUDED = ['cv_001_23ef2a5f', 'cv_007_ccf4e61f', 'cv_014_962e2cda',
            'cv_015_0ebf0185', 'cv_017_956f5a8e']
CATEGORIES = ['literal', 'literal', 'paráfrase', 'paráfrase',
              'relacionada, não confirmada', 'sem evidência']
SOURCE_FILES = ['app/analysis.py', 'src/data/privacy.py', 'src/data/clean.py',
                'src/nlp/skills_extractor.py', 'src/nlp/inference.py',
                'src/nlp/embeddings.py', 'src/matching/semantic.py']
REVIEW_FIELDS = ['extraction_failure', 'ranking_failure', 'related_confusion',
                 'annotation_ambiguity', 'language_difficulty']


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8'))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def pipeline_version():
    # Importar app.analysis inicializaria Flask e leria .env. Lemos só a constante.
    tree = ast.parse((ROOT / 'app/analysis.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'PIPELINE_VERSION' for t in node.targets))


def code_hashes():
    return {name: digest((ROOT / name).read_bytes()) for name in SOURCE_FILES}


def private_output(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / 'reports'):
        raise ValueError('Dados pessoais e relatórios devem ficar em reports/.')
    return path


def select_sample(data, seed=42, size=10):
    """Identidade igual a preparar_amostra_real.load_sample; sem IDs nativos."""
    if not isinstance(data, list):
        raise ValueError('Validation deve ser uma lista.')
    for old_id in EXCLUDED:
        index = int(old_id.split('_')[1])
        if index >= len(data) or not isinstance(data[index].get('content'), str):
            raise ValueError('Não foi possível conferir o ID excluído: ' + old_id)
        actual = f'cv_{index:03d}_{digest(data[index]["content"].encode())[:8]}'
        if actual != old_id:
            raise ValueError('Validation não corresponde à amostra antiga: ' + old_id)
    excluded_indices = {int(value.split('_')[1]) for value in EXCLUDED}
    indices = sorted(random.Random(seed).sample(
        [i for i in range(len(data)) if i not in excluded_indices], size))
    selected = []
    for i in indices:
        text = data[i].get('content')
        if not isinstance(text, str):
            raise ValueError(f'Registro selecionado {i} sem content textual; não substituído.')
        sha = digest(text.encode())
        selected.append(dict(resume_id=f'cv_{i:03d}_{sha[:8]}', source_index=i,
                             text_sha256=sha, text=text))
    if len({item['text_sha256'] for item in selected}) != size:
        raise ValueError('Textos duplicados na amostra; não substituídos silenciosamente.')
    return selected


def integrated_inputs(raw, entities):
    """Adaptador fiel ao bloco pré-embedding de app.analysis.analyze web-2.

    Não importa o pacote Flask e não modifica os módulos avaliados. O hash do
    serviço integrado é congelado junto com o dos módulos efetivamente usados.
    """
    from src.data.clean import anonymize_resume_text
    from src.data.privacy import anonymize_for_analysis, personal_spans, valid_entity
    from src.nlp.skills_extractor import extract_skills
    text = anonymize_for_analysis(raw, entities)
    spans = personal_spans(raw, entities)
    skills = [dict(label='SKILLS', text=anonymize_resume_text(entity['text']),
                   confidence=entity.get('confidence', 0))
              for entity in entities if entity['label'] == 'SKILLS'
              and valid_entity(raw, entity)
              and not any(a < entity['end'] and entity['start'] < b for a, b in spans)]
    return extract_skills(text=text, ner_entities=skills)


def annotation_template(item, inputs_hash):
    return dict(resume_id=item['resume_id'], inputs_sha256=inputs_hash,
                human_review=dict(completed=False, reviewer='', notes='', distribution_limitations=''),
                requirements=[dict(id=f'R{i+1}', text='', category=category,
                                   acceptable_input_indices=None, evidence_in_original=None,
                                   extraction_failure=False, expected_evidence='', notes='',
                                   human_analysis={name: '' for name in REVIEW_FIELDS})
                              for i, category in enumerate(CATEGORIES)])


def validate_annotation(annotation, inputs, expected_hash):
    if fingerprint(inputs) != expected_hash or annotation.get('inputs_sha256') != expected_hash:
        raise ValueError('Hash das entradas incompatível; refaça a anotação.')
    if [item.get('input_index') for item in inputs] != list(range(len(inputs))):
        raise ValueError('Índices das entradas incompatíveis.')
    review = annotation.get('human_review', {})
    if review.get('completed') is not True or not str(review.get('reviewer', '')).strip():
        raise ValueError('Revisão humana pendente.')
    requirements = annotation.get('requirements', [])
    if len(requirements) != 6 or len({r['id'] for r in requirements}) != 6:
        raise ValueError('São necessários seis requisitos com IDs únicos.')
    known = set(range(len(inputs)))
    for r in requirements:
        gold = r.get('acceptable_input_indices')
        if not isinstance(r.get('text'), str) or not r['text'].strip() or gold is None:
            raise ValueError('Requisito vazio ou não anotado.')
        if (not isinstance(gold, list) or any(type(i) is not int for i in gold)
                or len(gold) != len(set(gold)) or not set(gold) <= known):
            raise ValueError('Índice anotado inválido.')
        if r.get('category') not in set(CATEGORIES):
            raise ValueError('Categoria humana inválida.')
        original = r.get('evidence_in_original')
        failure = r.get('extraction_failure')
        if type(original) is not bool or type(failure) is not bool:
            raise ValueError('Confirme a consulta ao currículo original e a falha de extração.')
        if (bool(gold) and (not original or failure)) or (not gold and original != failure):
            raise ValueError('Gold, evidência original e falha de extração inconsistentes.')
        if original and not str(r.get('expected_evidence', '')).strip():
            raise ValueError('Descreva a evidência esperada no original.')
        if failure and not str(r.get('notes', '')).strip():
            raise ValueError('Documente a falha de extração.')
    actual_categories = sorted(r['category'] for r in requirements)
    if actual_categories != sorted(CATEGORIES) and not review.get('distribution_limitations', '').strip():
        raise ValueError('Documente a limitação da distribuição planejada.')
    return requirements


def metrics_for(rows, ranking_only=False):
    """Reutiliza evaluate_ranking; perdas da extração são positivos sem acerto.

    Um sentinela -1 só na cópia destinada à métrica marca esses positivos,
    sem entrar no gold persistido, no modelo ou em compare.
    """
    selected = [row for row in rows if not (ranking_only and row['requirement']['extraction_failure'])]
    requirements = []
    for row in selected:
        r = dict(row['requirement'])
        if r['extraction_failure']:
            r['acceptable_input_indices'] = [-1]
        requirements.append(r)
    result = evaluate_ranking([row['result'] for row in selected], requirements)
    result['extraction_lost_positive_count'] = sum(row['requirement']['extraction_failure'] for row in selected)
    result['excluded_extraction_failures'] = len(rows) - len(selected)
    result['denominator'] = result['evaluated_positive_count']
    return result


def consolidate(rows, resume_ids):
    return dict(resume_count=len(resume_ids), requirement_count=len(rows),
                overall=metrics_for(rows), ranking_only=metrics_for(rows, True),
                by_resume={rid: metrics_for([r for r in rows if r['resume_id'] == rid]) for rid in resume_ids},
                by_category={cat: metrics_for([r for r in rows if r['requirement']['category'] == cat])
                             for cat in sorted({r['requirement']['category'] for r in rows})})
