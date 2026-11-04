"""Agregação pura de similaridades; não decide atendimento ou qualificação."""
import math
from numbers import Real


FORMULA_VERSION = "1.0"
NUMERIC_TOLERANCE = 1e-9
DEFAULT_WEIGHTS = {"obrigatorio": 1.0, "desejavel": 1.0}


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} deve ser um número finito, não booleano.")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} deve ser um número finito.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} deve ser um número finito.")
    return number


def _cosine(value, field):
    number = _number(value, field)
    if not -1 - NUMERIC_TOLERANCE <= number <= 1 + NUMERIC_TOLERANCE:
        raise ValueError(f"{field} deve estar entre -1 e 1.")
    return number


def _nonempty_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio.")
    return value


def _by_id(items, name):
    if not isinstance(items, list):
        raise ValueError(f"{name} deve ser uma lista.")
    indexed = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Cada item de {name} deve ser um objeto.")
        identifier = _nonempty_text(item.get("id"), f"ID em {name}")
        if identifier in indexed:
            raise ValueError(f"ID duplicado em {name}: {identifier}.")
        indexed[identifier] = item
    return indexed


def _validate_ranking(result):
    identifier = result["id"]
    ranking = result.get("ranking")
    if not isinstance(ranking, list):
        raise ValueError(f"{identifier}: ranking deve estar presente como lista.")
    previous = None
    for evidence in ranking:
        if not isinstance(evidence, dict):
            raise ValueError(f"{identifier}: evidência deve ser um objeto.")
        similarity = _cosine(evidence.get("similarity"), f"{identifier}: similarity")
        if previous is not None and similarity > previous + NUMERIC_TOLERANCE:
            raise ValueError(f"{identifier}: ranking deve estar em ordem decrescente.")
        previous = similarity
        for field in ("text", "source"):
            _nonempty_text(evidence.get(field), f"{identifier}: evidência.{field}")
        for field in ("input_index", "chunk_index"):
            index = evidence.get(field)
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError(f"{identifier}: {field} deve ser inteiro não negativo.")
    top = result.get("top_similarity")
    if ranking:
        top = _cosine(top, f"{identifier}: top_similarity")
        if abs(top - float(ranking[0]["similarity"])) > NUMERIC_TOLERANCE:
            raise ValueError(f"{identifier}: top_similarity incoerente com a primeira evidência.")
    elif top is not None:
        top = _cosine(top, f"{identifier}: top_similarity")
    return top, ranking


def _contributions(details):
    # Escala comum evita overflow com pesos finitos muito grandes.
    scale = max(item["weight"] for item in details)
    normalized = [item["weight"] / scale for item in details]
    denominator = math.fsum(normalized)
    contributions = [100 * weight * item["aggregation_value"] / denominator
            for item, weight in zip(details, normalized)]
    # Protege o limite superior de um eventual excesso de arredondamento.
    total = math.fsum(contributions)
    if total > 100:
        largest = max(range(len(contributions)), key=contributions.__getitem__)
        contributions[largest] -= total - 100
    return contributions


def calculate_similarity_index(requirements, results, weights=None):
    """Retorna índice 0–100 a partir de compare(), sem alterar as entradas.

    Fórmula v1.0: 100 * sum(w * max(0, cosseno)) / sum(w).
    Cossenos até 1e-9 além dos limites são normalizados. Limitar negativos
    a zero é uma regra inicial de agregação, não uma propriedade do modelo.
    Rankings vazios tornam a análise incompleta, sem nota geral parcial.
    """
    requirements_by_id = _by_id(requirements, "requirements")
    if not requirements_by_id:
        raise ValueError("requirements deve conter pelo menos um requisito.")
    results_by_id = _by_id(results, "results")
    missing = sorted(requirements_by_id.keys() - results_by_id.keys())
    extra = sorted(results_by_id.keys() - requirements_by_id.keys())
    if missing or extra:
        raise ValueError(f"IDs de resultados inconsistentes: ausentes={missing}; extras={extra}.")
    configured = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        if not isinstance(weights, dict) or any(key not in configured for key in weights):
            raise ValueError("weights deve ser um objeto com obrigatorio e/ou desejavel.")
        configured.update(weights)
    for level, value in configured.items():
        configured[level] = _number(value, f"Peso {level}")
        if configured[level] <= 0:
            raise ValueError(f"Peso {level} deve ser estritamente positivo.")

    warnings, details, incomplete = [], [], []
    for identifier, requirement in requirements_by_id.items():
        text = _nonempty_text(requirement.get("text"), f"{identifier}: text")
        level = requirement.get("nivel")
        if level is None:
            weight = 1.0
            warnings.append(f"{identifier}: requisito sem nível; utilizado peso 1.")
        elif not isinstance(level, str) or level not in configured:
            raise ValueError(f"{identifier}: nível desconhecido: {level!r}.")
        else:
            weight = configured[level]
        kind = requirement.get("tipo")
        if kind is not None and not isinstance(kind, str):
            raise ValueError(f"{identifier}: tipo deve ser texto ou null.")
        top, ranking = _validate_ranking(results_by_id[identifier])
        evidence = None
        if ranking:
            evidence = {key: ranking[0][key]
                        for key in ("text", "source", "input_index", "chunk_index")}
            normalized = min(1.0, max(-1.0, top))
            if normalized != top:
                warnings.append(f"{identifier}: pequeno excesso numérico do cosseno normalizado.")
            aggregation_value = max(0.0, normalized)
        else:
            incomplete.append(identifier)
            aggregation_value = None
        details.append({"id": identifier, "text": text, "tipo": kind, "nivel": level,
                        "weight": weight, "original_cosine": top,
                        "aggregation_value": aggregation_value,
                        "contribution_points": None, "best_evidence": evidence})

    score = None
    if not incomplete:
        contributions = _contributions(details)
        for item, contribution in zip(details, contributions):
            item["contribution_points"] = contribution
        score = math.fsum(contributions)
    else:
        warnings.append("Análise incompleta: ranking vazio em " + ", ".join(incomplete)
                        + ". Sem índice geral ou contribuições finais; não indica falta de competência.")
    groups = {}
    for level in DEFAULT_WEIGHTS:
        group = [item for item in details if item["nivel"] == level]
        groups[level] = (math.fsum(_contributions(group)) if group and all(
            item["aggregation_value"] is not None for item in group) else None)
    return {"status": "analise_incompleta" if incomplete else "calculado",
            "score": score, "score_name": "indice_compatibilidade_semantica",
            "formula_version": FORMULA_VERSION, "weights": configured,
            "warnings": warnings, "incomplete_requirement_ids": incomplete,
            "indices_by_level": groups, "details": details}
