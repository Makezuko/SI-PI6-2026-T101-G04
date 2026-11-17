"""Regra experimental: proporção ponderada de decisões documentais explícitas."""
from copy import deepcopy
import math

from src.matching.score import _by_id, _number, _nonempty_text, _validate_ranking

FORMULA_VERSION = '3.1-experimental'
DEFAULT_WEIGHTS = {'obrigatorio': 2.0, 'desejavel': 1.0}
STATES = {'atendido', 'nao_identificado', 'revisao_necessaria'}


def calculate_adherence(requirements, decisions, weights=None):
    """Cossenos não entram no cálculo. Ausência de decisão é erro, nunca zero."""
    requirements = _by_id(requirements, 'requirements')
    decisions = _by_id(decisions, 'decisions')
    if not requirements or requirements.keys() != decisions.keys():
        raise ValueError('Requisitos e decisões devem ter os mesmos IDs, não vazios.')
    configured = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        if not isinstance(weights, dict) or weights.keys() - configured.keys():
            raise ValueError('Pesos devem usar obrigatorio e/ou desejavel.')
        configured.update(weights)
    for level, weight in configured.items():
        configured[level] = _number(weight, f'Peso {level}')
        if configured[level] <= 0:
            raise ValueError('Pesos devem ser positivos.')
    details = []
    for identifier, requirement in requirements.items():
        level = requirement.get('nivel', 'obrigatorio')
        if level not in configured:
            raise ValueError('Nível desconhecido; revise a classificação do requisito.')
        decision = decisions[identifier]
        state = decision.get('estado')
        if state not in STATES:
            raise ValueError('Decisão ausente ou inválida; análise não calculada.')
        reason = _nonempty_text(decision.get('justificativa'), 'justificativa')
        evidence = deepcopy(decision.get('evidencias', []))
        if not isinstance(evidence, list) or (state == 'atendido' and not evidence):
            raise ValueError('Atendimento exige evidência documental.')
        for entry in evidence:
            if not isinstance(entry, dict):
                raise ValueError('Evidência deve ser um objeto com texto e origem.')
            _nonempty_text(entry.get('text'), 'evidencia.text')
            _nonempty_text(entry.get('source'), 'evidencia.source')
        origin = decision.get('origem', 'automatica')
        if origin not in {'automatica', 'humana'}:
            raise ValueError('Origem de decisão inválida.')
        details.append(dict(id=identifier, text=_nonempty_text(requirement.get('text'), 'text'),
                            nivel=level, tipo=requirement.get('tipo'), peso=configured[level],
                            estado=state, origem=origin, justificativa=reason, evidencias=evidence,
                            best_evidence=evidence[0] if evidence else None,
                            original_cosine=decision.get('top_similarity'),
                            compatible=state == 'atendido', method_version=FORMULA_VERSION,
                            diagnostic=deepcopy(decision.get('diagnostic', {}))))
    # Escala evita overflow para pesos finitos grandes.
    scale = max(configured.values())
    total = math.fsum(d['peso'] / scale for d in details)
    pending = math.fsum(d['peso'] / scale for d in details if d['estado'] == 'revisao_necessaria')
    confirmed = math.fsum(d['peso'] / scale for d in details if d['estado'] == 'atendido')
    for item in details:
        item['max_points'] = 100 * (item['peso'] / scale) / total
        item['contribution_points'] = item['max_points'] if item['compatible'] else 0.0
    counts = {state: sum(d['estado'] == state for d in details) for state in sorted(STATES)}
    alerts = [d['id'] for d in details if d['nivel'] == 'obrigatorio' and not d['compatible']]
    return dict(status='calculado', score=100 * confirmed / total,
                score_name='aderencia_documental', formula_version=FORMULA_VERSION,
                weights=configured, details=details, counts=counts, provisional=bool(pending),
                maximum_score=100 * (confirmed + pending) / total,
                undecided=counts['revisao_necessaria'] == len(details),
                pending_weight=math.fsum(d['peso'] for d in details if d['estado'] == 'revisao_necessaria'),
                mandatory_alert_ids=alerts, mandatory_status='atencao' if alerts else 'atendido',
                warnings=[], incomplete_requirement_ids=[])


def evaluate_requirements(requirements, results, entries=None):
    """Recuperação é entrada; similaridade não decide atendimento."""
    by_id = _by_id(results, 'results')
    if _by_id(requirements, 'requirements').keys() != by_id.keys():
        raise ValueError('Recuperação incompleta: IDs diferentes dos requisitos.')
    from src.matching.documental_rules import infer_condition, validate_condition, evaluate_condition
    decisions = []
    for requirement in requirements:
        result = by_id[requirement['id']]
        top, ranking = _validate_ranking(result)
        if not ranking and not entries:
            raise ValueError('Recuperação sem resultados; análise permanece pendente.')
        state = 'revisao_necessaria'
        reason = 'Evidência recuperada exige avaliação humana; similaridade não comprova atendimento.'
        condition = validate_condition(requirement.get('condition')) or infer_condition(requirement['text'])
        candidates = [dict(entry, input_index=index, chunk_index=0)
                      for index, entry in enumerate(entries or [])]
        candidates.extend(ranking)
        diagnostic = {'rule': 'human_review', 'total_entries': len(entries or []),
                      'semantic_candidates': len(ranking), 'retrieval_top_similarity': top}
        evidence = ranking
        if condition and requirement.get('tipo') != 'comportamental':
            passed, hits, reason, trace = evaluate_condition(condition, candidates)
            diagnostic.update(trace)
            if passed:
                state, evidence = 'atendido', hits
        elif condition is None:
            reason = 'Requisito sem regra inequívoca. Configure condições na edição da vaga ou solicite revisão humana.'
        decisions.append(dict(id=requirement['id'], estado=state, origem='automatica',
                              justificativa=reason, evidencias=deepcopy(evidence),
                              diagnostic=diagnostic,
                              top_similarity=evidence[0].get('similarity') if evidence else None))
    return decisions
