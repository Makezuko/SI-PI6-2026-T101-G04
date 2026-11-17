"""Agregação pura de similaridades; não decide atendimento ou qualificação."""
import math
from numbers import Real


FORMULA_VERSION = "2.1"
NUMERIC_TOLERANCE = 1e-9
SIMILARITY_THRESHOLD = 0.50
DEFAULT_WEIGHTS = {"obrigatorio": 90.0, "desejavel": 10.0}


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


def calculate_similarity_index(requirements, results, weights=None):
    """Calcula pontos por requisito usando similaridades de compare()."""
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
            level = "obrigatorio"
            warnings.append(f"{identifier}: requisito sem nível; considerado obrigatório.")
        elif not isinstance(level, str) or level not in configured:
            raise ValueError(f"{identifier}: nível desconhecido: {level!r}.")
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
            compatible = normalized >= SIMILARITY_THRESHOLD
            aggregation_value = normalized if compatible else 0.0
        else:
            incomplete.append(identifier)
            compatible = None
            aggregation_value = None
        details.append({"id": identifier, "text": text, "tipo": kind, "nivel": level,
                        "compatible": compatible, "max_points": None, "original_cosine": top,
                        "aggregation_value": aggregation_value,
                        "contribution_points": None, "best_evidence": evidence})

    groups = {
        level: [item for item in details if item["nivel"] == level]
        for level in DEFAULT_WEIGHTS
    }
    active_levels = [level for level, items in groups.items() if items]
    if len(active_levels) == 1:
        allocations = {active_levels[0]: 100.0}
    else:
        scale = max(configured.values())
        normalized_weights = {level: value / scale for level, value in configured.items()}
        denominator = math.fsum(normalized_weights.values())
        allocations = {
            level: 100.0 * normalized_weights[level] / denominator
            for level in configured
        }

    for level, items in groups.items():
        if items:
            points_per_item = allocations[level] / len(items)
            for item in items:
                item["max_points"] = points_per_item

    score = None
    if not incomplete:
        for item in details:
            item["contribution_points"] = item["max_points"] * item["aggregation_value"]
        total = math.fsum(item["contribution_points"] for item in details)
        if total > 100:
            largest = max(details, key=lambda item: item["contribution_points"])
            largest["contribution_points"] -= total - 100
        score = math.fsum(item["contribution_points"] for item in details)
    else:
        warnings.append("Análise incompleta: ranking vazio em " + ", ".join(incomplete)
                        + ". Sem índice geral ou contribuições finais; não indica falta de competência.")
    indices_by_level = {}
    for level, items in groups.items():
        indices_by_level[level] = (math.fsum(item["contribution_points"] for item in items)
                                   if items and all(item["contribution_points"] is not None
                                                    for item in items) else None)
    mandatory_items = groups["obrigatorio"]
    mandatory_status = (
        "incompativel" if any(item["compatible"] is False for item in mandatory_items)
        else "incompleto" if any(item["compatible"] is None for item in mandatory_items)
        else "atendido"
    )
    return {"status": "analise_incompleta" if incomplete else "calculado",
            "score": score, "score_name": "indice_compatibilidade_semantica",
            "formula_version": FORMULA_VERSION, "weights": configured,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "mandatory_status": mandatory_status,
            "warnings": warnings, "incomplete_requirement_ids": incomplete,
            "indices_by_level": indices_by_level, "details": details}
