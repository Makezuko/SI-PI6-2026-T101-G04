"""Orquestração local da análise; modelos carregados uma vez por processo."""
from functools import lru_cache
from hashlib import sha256
import math
import json
import os
from pathlib import Path
from threading import RLock

from app.requisitos import parse_requirements
from src.data.clean import anonymize_resume_text
from src.data.privacy import anonymize_for_analysis, personal_spans, valid_entity, latest_role, sanitize_semantic_inputs, uploaded_name_entities
from src.matching.adherence import calculate_adherence, evaluate_requirements, FORMULA_VERSION, DEFAULT_WEIGHTS, STATES
from src.nlp.skills_extractor import extract_skills
from src.matching.documental_rules import unsafe

MODEL_LOCK = RLock()
PIPELINE_VERSION = 'web-4-documental-literal-sections'


class AnalysisError(ValueError):
    pass


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def configuration():
    return {
        'ner_model': os.getenv('NER_MODEL_PATH', 'models/ner/augmented/best_model'),
        'embedding_model': os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-mpnet-base-v2'),
        'formula_version': FORMULA_VERSION, 'weights': DEFAULT_WEIGHTS,
        'pipeline_version': PIPELINE_VERSION,
    }


def versions(job, resume):
    requirements = parse_requirements(job['requirements_data'])
    return {
        'requirements_hash': fingerprint(requirements['items']),
        'text_hash': fingerprint(resume['raw_text']),
        'config_hash': fingerprint(configuration()),
    }


def confirmed_requirements(job):
    data = parse_requirements(job['requirements_data'])
    if data['status'] != 'revisado':
        raise AnalysisError('A vaga precisa ter seus requisitos revisados antes da análise.')
    return data['items']


@lru_cache(maxsize=2)
def load_models(ner_path, embedding_model):
    try:
        if not Path(ner_path).is_dir():
            raise FileNotFoundError
        from src.nlp.inference import ResumeNERPredictor
        from src.nlp.embeddings import ResumeEmbedder
        predictor = ResumeNERPredictor(model_directory=ner_path)
        labels = {label.removeprefix('B-').removeprefix('I-') for label in predictor.id2label.values()}
        if not {'NAME', 'SKILLS'}.issubset(labels):
            raise ValueError('Rótulos incompatíveis.')
        return predictor, ResumeEmbedder(model_name=embedding_model)
    except Exception as exc:
        raise AnalysisError('Modelo NER ou embeddings indisponível/incompatível. Confira NER_MODEL_PATH e EMBEDDING_MODEL.') from exc


def analyze(job, resume):
    requirements = confirmed_requirements(job)
    config = configuration()
    with MODEL_LOCK:
        predictor, embedder = load_models(config['ner_model'], config['embedding_model'])
        prediction = predictor.predict(text=resume['raw_text'], minimum_confidence=0.0)
        raw = resume['raw_text']
        entities = prediction['entities'] + uploaded_name_entities(raw, resume.get('anonymized_text'))
        text = anonymize_for_analysis(raw, entities)
        spans = personal_spans(raw, entities)
        skills = [dict(label='SKILLS', text=anonymize_resume_text(entity['text']),
                       confidence=entity.get('confidence', 0))
                  for entity in entities if entity['label'] == 'SKILLS'
                  and valid_entity(raw, entity)
                  and not unsafe(raw[raw.rfind('\n', 0, entity['start']) + 1:
                                     raw.find('\n', entity['end']) if '\n' in raw[entity['end']:] else len(raw)])
                  and not any(a < entity['end'] and entity['start'] < b for a, b in spans)]
        inputs = extract_skills(text=text, ner_entities=skills)['semantic_inputs']
        inputs = sanitize_semantic_inputs(inputs)
        if not inputs:
            raise AnalysisError('Nenhuma evidência profissional extraída; análise permanece pendente.')
        safe_requirements = [dict(item) for item in requirements]
        queries = embedder.encode([{'text': item['text'], 'source': 'requirement'} for item in safe_requirements])
        if len(queries['records']) != len(requirements):
            raise AnalysisError('Divida os requisitos longos em requisitos curtos antes da análise.')
        embedded = embedder.encode(inputs)
        from src.matching.semantic import compare
        results, _ = compare(safe_requirements, queries['embeddings'], embedded)
    result = calculate_adherence(safe_requirements, evaluate_requirements(safe_requirements, results, inputs))
    result['extraction_diagnostic'] = {
        'requirements_received': [item['id'] for item in safe_requirements],
        'entries_by_source': {source: sum(entry['source'] == source for entry in inputs)
                              for source in sorted({entry['source'] for entry in inputs})},
        'entries_considered': len(inputs),
    }
    result['last_role'] = latest_role(raw, entities)
    return {**versions(job, resume), **config, 'result': result}


def is_current_documental_result(result):
    """Hashes não bastam: valide também o contrato JSON usado pelos templates.

    Um servidor antigo pode continuar gravando o formato semântico enquanto os
    templates já foram atualizados no disco. Não converta essas notas em aderência.
    """
    if not isinstance(result, dict):
        return False
    if (result.get('formula_version') != FORMULA_VERSION
            or result.get('score_name') != 'aderencia_documental'
            or result.get('status') != 'calculado'):
        return False
    counts, weights, details = (result.get(key) for key in ('counts', 'weights', 'details'))
    if not isinstance(counts, dict) or any(
            type(counts.get(state)) is not int or counts[state] < 0 for state in STATES):
        return False
    if not isinstance(weights, dict) or weights != DEFAULT_WEIGHTS:
        return False
    if not isinstance(details, list) or not details:
        return False
    required_fields = {'id', 'text', 'nivel', 'peso', 'estado', 'justificativa',
                       'compatible', 'contribution_points', 'max_points',
                       'best_evidence', 'original_cosine'}
    if any(not isinstance(item, dict) or not required_fields.issubset(item)
           or item['estado'] not in STATES for item in details):
        return False
    if counts != {state: sum(item['estado'] == state for item in details) for state in STATES}:
        return False
    for key in ('score', 'maximum_score', 'pending_weight'):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
    return (0 <= result['score'] <= result['maximum_score'] <= 100
            and result['pending_weight'] >= 0
            and type(result.get('provisional')) is bool
            and type(result.get('undecided')) is bool
            and result['undecided'] == (counts['revisao_necessaria'] == len(details))
            and isinstance(result.get('mandatory_alert_ids'), list))


def attach_analysis(client, job, candidates):
    from app.repositories import list_analyses
    rows = list_analyses(client, job['id']) if candidates else []
    for candidate in candidates:
        previous = [row for row in rows if str(row['curriculo_id']) == candidate['id']]
        current = versions(job, candidate)
        valid = [row for row in previous
                 if all(row.get(key) == value for key, value in current.items())
                 and is_current_documental_result(row.get('result'))]
        record = valid[0] if valid else None
        candidate['analysis'] = record['result'] if record else None
        result = record['result'] if record else {}
        candidate['last_role'] = result.get('last_role', 'Não identificado')
        candidate['score'] = result.get('score')
        candidate['ranking_score'] = candidate['score']
        if result.get('undecided'):
            candidate['score'] = None
        candidate['mandatory_status'] = result.get('mandatory_status')
        if not record:
            candidate['analysis_state'] = 'Desatualizada' if previous else 'Pendente'
        elif result.get('status') == 'analise_incompleta':
            candidate['analysis_state'] = 'Incompleta'
        elif result.get('undecided'):
            candidate['analysis_state'] = 'Avaliação pendente'
        elif result.get('provisional'):
            candidate['analysis_state'] = 'Provisória — revisão necessária'
        else:
            candidate['analysis_state'] = 'Concluída'

    def ranking_order(candidate):
        score = candidate.get('score')
        pending = (candidate.get('analysis') or {}).get('pending_weight', 0)
        return score is None, -(score or 0), pending, int(candidate['id'])

    return sorted(candidates, key=ranking_order)


def process_resume(client, job, resume):
    from app.repositories import save_analysis, get_resume
    payload = analyze(job, resume)
    # Evita publicar como atual uma análise cujo texto/requisitos mudaram durante o cálculo.
    from app.repositories import get_job
    latest_job = get_job(client, job['id'])
    latest_resume = get_resume(client, job['id'], resume['id'])
    if not latest_job or not latest_resume or versions(latest_job, latest_resume) != versions(job, resume):
        raise AnalysisError('Vaga ou currículo mudou durante a análise. Reenvie para recalcular.')
    save_analysis(client, job['id'], resume['id'], payload)
    # A decisão manual em curriculos.status nunca é alterada por processamento.
    return payload['result']
