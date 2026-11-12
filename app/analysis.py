"""Orquestração local da análise; modelos carregados uma vez por processo."""
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock

from app.requisitos import parse_requirements
from src.data.clean import anonymize_resume_text
from src.matching.score import calculate_similarity_index, FORMULA_VERSION, DEFAULT_WEIGHTS
from src.nlp.skills_extractor import extract_skills

MODEL_LOCK = RLock()
PIPELINE_VERSION = 'web-1'


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
        def anonymize(value):
            value = anonymize_resume_text(value, resume.get('name'))
            for entity in prediction['entities']:
                if entity['label'] in {'NAME', 'EMAIL_ADDRESS', 'LOCATION'} and entity['text']:
                    value = value.replace(entity['text'], '[DADO PESSOAL OCULTO]')
            return value
        text = anonymize(resume['raw_text'])
        # Predições conservam apenas SKILLS; offsets do texto original não são reutilizados.
        skills = [dict(entity, text=anonymize(entity['text']))
                  for entity in prediction['entities'] if entity['label'] == 'SKILLS']
        inputs = extract_skills(text=text, ner_entities=skills)['semantic_inputs']
        if not inputs:
            raise AnalysisError('Nenhuma evidência profissional extraída; análise permanece pendente.')
        safe_requirements = [dict(item, text=anonymize(item['text']))
                             for item in requirements]
        queries = embedder.encode([{'text': item['text'], 'source': 'requirement'} for item in safe_requirements])
        if len(queries['records']) != len(requirements):
            raise AnalysisError('Divida os requisitos longos em requisitos curtos antes da análise.')
        embedded = embedder.encode(inputs)
        from src.matching.semantic import compare
        results, _ = compare(safe_requirements, queries['embeddings'], embedded)
    result = calculate_similarity_index(safe_requirements, results)
    return {**versions(job, resume), **config, 'result': result}


def attach_analysis(client, job, candidates):
    from app.repositories import list_analyses
    rows = list_analyses(client, job['id']) if candidates else []
    for candidate in candidates:
        previous = [row for row in rows if str(row['curriculo_id']) == candidate['id']]
        current = versions(job, candidate)
        valid = [row for row in previous if all(row.get(key) == value for key, value in current.items())]
        record = valid[0] if valid else None
        candidate['analysis'] = record['result'] if record else None
        candidate['score'] = record['result']['score'] if record else None
        candidate['analysis_state'] = ('Concluída' if candidate['score'] is not None else
                                       'Desatualizada' if previous and not valid else 'Pendente')
    return sorted(candidates, key=lambda item: (item['score'] is None, -(item['score'] or 0)))


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
