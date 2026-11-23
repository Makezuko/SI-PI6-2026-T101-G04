"""Orquestração local da análise; modelos carregados uma vez por processo."""
from functools import lru_cache
from hashlib import sha256
import math
import json
import os
import sys
from pathlib import Path
from threading import RLock

from app.requisitos import parse_requirements
from src.matching.adherence import FORMULA_VERSION, DEFAULT_WEIGHTS, STATES
from src.matching.facade import PipelineExecutionError, TalentMatchPipelineFacade
from src.matching.llm_justification import generate_llm_justification, is_justification_available
from src.matching.telemetry import event

MODEL_LOCK = RLock()
PIPELINE_VERSION = 'web-8-contextual-window-mean'


class AnalysisError(ValueError):
    pass


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def configuration():
    from src.matching.contextual import settings
    return {
        'contextual': settings(),
        'ner_model': os.getenv('NER_MODEL_PATH', 'models/ner/augmented/best_model'),
        'embedding_model': os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-mpnet-base-v2'),
        'formula_version': FORMULA_VERSION, 'weights': DEFAULT_WEIGHTS,
        'pipeline_version': PIPELINE_VERSION,
    }


def process_configuration():
    config = configuration()
    contextual = config['contextual']
    return dict(pid=os.getpid(), python=sys.executable, enabled=contextual['enabled'],
                backend=contextual['backend'], model=contextual['model'],
                revision=contextual['revision'], pipeline=config['pipeline_version'])


def versions(job, resume, config=None):
    requirements = parse_requirements(job['requirements_data'])
    return {
        'requirements_hash': fingerprint([{k: v for k, v in item.items() if k != 'condition'} for item in requirements['items']]),
        'text_hash': fingerprint(resume['raw_text']),
        'config_hash': fingerprint(configuration() if config is None else config),
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
    facade = TalentMatchPipelineFacade(
        models_loader=load_models,
        contextual_loader=load_contextual_model,
        justification_generator=generate_llm_justification,
        lock=MODEL_LOCK,
    )
    try:
        result = facade.analyze_resume(
            job=job,
            resume=resume,
            requirements=requirements,
            config=config,
        )
    except PipelineExecutionError as exc:
        raise AnalysisError(str(exc)) from None
    return {**versions(job, resume, config), **{k: v for k, v in config.items() if k != 'contextual'}, 'result': result}


@lru_cache(maxsize=2)
def load_contextual_model(path, revision, backend=None, runtime=None, runtime_revision=None):
    from src.matching.contextual import create_adapter, ContextualTechnicalError
    try:
        if not revision:
            raise ContextualTechnicalError('CONTEXTUAL_CONFIG_INVALID')
        return create_adapter(path)
    except Exception:
        raise ContextualTechnicalError('MODEL_LOAD_ERROR') from None


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


def result_matches_mode(result, config):
    if not is_current_documental_result(result):
        return False
    ctx = config['contextual']
    actual = result.get('contextual_configuration')
    if not ctx['enabled']:
        return False
    from src.matching.contextual import FORMULA_VERSION as CONTEXTUAL_FORMULA, validate
    if actual != ctx or result.get('contextual_formula_version') != CONTEXTUAL_FORMULA:
        return False
    try:
        for item in result['details']:
            trace = item['diagnostic']
            verdict = validate(trace['contextual'], trace['retrieved_evidence'])
            state = {'sustentado': 'atendido', 'nao_sustentado_pelas_evidencias': 'nao_identificado'}.get(verdict['estado'], 'revisao_necessaria')
            if item['estado'] != state:
                return False
    except (KeyError, ValueError, TypeError):
        return False
    return True


def attach_analysis(client, job, candidates):
    from app.repositories import list_analyses
    rows = list_analyses(client, job['id']) if candidates else []
    config = configuration()
    for candidate in candidates:
        previous = [row for row in rows if str(row['curriculo_id']) == candidate['id']]
        current = versions(job, candidate)
        valid = [row for row in previous
                 if all(row.get(key) == value for key, value in current.items())
                 and result_matches_mode(row.get('result'), config)]
        record = max(valid, key=lambda row: (row.get('analisado_em') or '', int(row.get('id') or 0))) if valid else None
        candidate['analysis_id'] = record.get('id') if record else None
        candidate['analysis'] = record['result'] if record else None
        result = record['result'] if record else {}
        candidate['llm_justification'] = result.get('llm_justification') if record else None
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


def dashboard_scores(client, jobs):
    """Calcula pontuações atuais para o painel com apenas 2 queries no banco."""
    if not jobs:
        return []
    from app.repositories import list_analyses_for_dashboard, list_resumes_for_dashboard
    resumes = list_resumes_for_dashboard(client)
    analyses = list_analyses_for_dashboard(client)
    config = configuration()
    config_hash = fingerprint(config)
    jobs_by_id = {str(job['id']): job for job in jobs}
    req_hashes = {
        str(job['id']): fingerprint([{k: v for k, v in item.items() if k != 'condition'} for item in parse_requirements(job['requirements_data'])['items']])
        for job in jobs
    }
    analyses_by_pair = {}
    for row in analyses:
        key = (str(row.get('vaga_id')), str(row.get('curriculo_id')))
        analyses_by_pair.setdefault(key, []).append(row)

    scores = []
    for resume in resumes:
        job_id = resume['job_id']
        job = jobs_by_id.get(job_id)
        if job is None:
            continue
        current = {
            'requirements_hash': req_hashes[job_id],
            'text_hash': fingerprint(resume['raw_text']),
            'config_hash': config_hash,
        }
        previous = analyses_by_pair.get((job_id, resume['id']), [])
        valid = [row for row in previous
                 if all(row.get(k) == v for k, v in current.items())
                 and result_matches_mode(row.get('result'), config)]
        if not valid:
            continue
        record = max(valid, key=lambda row: (row.get('analisado_em') or '', int(row.get('id') or 0)))
        result = record.get('result') or {}
        if not result.get('undecided') and result.get('score') is not None:
            scores.append(result['score'])
    return scores


def process_resume(client, job, resume):
    from app.repositories import save_analysis, get_resume
    event('ANALYSIS_EFFECTIVE_CONFIG', **process_configuration())
    payload = analyze(job, resume)
    # Evita publicar como atual uma análise cujo texto/requisitos mudaram durante o cálculo.
    from app.repositories import get_job
    latest_job = get_job(client, job['id'])
    latest_resume = get_resume(client, job['id'], resume['id'])
    if (not latest_job or not latest_resume
            or any(payload.get(key) != value for key, value in versions(latest_job, latest_resume).items())):
        raise AnalysisError('Vaga ou currículo mudou durante a análise. Reenvie para recalcular.')
    event('ANALYSIS_SAVE_START')
    try:
        record = save_analysis(client, job['id'], resume['id'], payload)
    except Exception:
        event('ANALYSIS_SAVE_ERROR', error_code='PERSISTENCE_ERROR')
        raise
    event('ANALYSIS_SAVED', analysis_id=record.get('id'), persisted_run_id=payload['result']['execution_id'])
    # A decisão manual em curriculos.status nunca é alterada por processamento.
    return payload['result']


def ensure_candidate_justification(client, job, candidate, transport=None):
    """Tenta gerar a justificativa via Gemini quando indisponível ao acessar o currículo."""
    current = candidate.get('llm_justification')
    if is_justification_available(current):
        return current
    justification = generate_llm_justification(
        job,
        anonymized_text=candidate.get('anonymized_text'),
        candidate=candidate,
        analysis_result=candidate.get('analysis'),
        transport=transport,
    )
    candidate['llm_justification'] = justification
    if candidate.get('analysis') is not None and is_justification_available(justification):
        candidate['analysis']['llm_justification'] = justification
        try:
            from app.repositories import save_analysis
            config = configuration()
            payload = {
                **versions(job, candidate, config),
                **{k: v for k, v in config.items() if k != 'contextual'},
                'result': candidate['analysis'],
            }
            save_analysis(client, job['id'], candidate['id'], payload)
        except Exception:
            pass
    return justification
