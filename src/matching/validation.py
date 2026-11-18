"""Validação compartilhada de requisitos e resultados de recuperação."""
import math
from numbers import Real

NUMERIC_TOLERANCE = 1e-9


def number(value, field):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} deve ser um número finito, não booleano.")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} deve ser um número finito.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} deve ser um número finito.")
    return number


def cosine(value, field):
    value_number = number(value, field)
    if not -1 - NUMERIC_TOLERANCE <= value_number <= 1 + NUMERIC_TOLERANCE:
        raise ValueError(f"{field} deve estar entre -1 e 1.")
    return value_number


def nonempty_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} deve ser texto não vazio.")
    return value


def by_id(items, name):
    if not isinstance(items, list):
        raise ValueError(f"{name} deve ser uma lista.")
    indexed = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Cada item de {name} deve ser um objeto.")
        identifier = nonempty_text(item.get("id"), f"ID em {name}")
        if identifier in indexed:
            raise ValueError(f"ID duplicado em {name}: {identifier}.")
        indexed[identifier] = item
    return indexed


def validate_ranking(result):
    identifier = result["id"]
    ranking = result.get("ranking")
    if not isinstance(ranking, list):
        raise ValueError(f"{identifier}: ranking deve estar presente como lista.")
    previous = None
    for evidence in ranking:
        if not isinstance(evidence, dict):
            raise ValueError(f"{identifier}: evidência deve ser um objeto.")
        similarity = cosine(evidence.get("similarity"), f"{identifier}: similarity")
        if previous is not None and similarity > previous + NUMERIC_TOLERANCE:
            raise ValueError(f"{identifier}: ranking deve estar em ordem decrescente.")
        previous = similarity
        for field in ("text", "source"):
            nonempty_text(evidence.get(field), f"{identifier}: evidência.{field}")
        for field in ("input_index", "chunk_index"):
            index = evidence.get(field)
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError(f"{identifier}: {field} deve ser inteiro não negativo.")
    top = result.get("top_similarity")
    if ranking:
        top = cosine(top, f"{identifier}: top_similarity")
        if abs(top - float(ranking[0]["similarity"])) > NUMERIC_TOLERANCE:
            raise ValueError(f"{identifier}: top_similarity incoerente com a primeira evidência.")
    elif top is not None:
        top = cosine(top, f"{identifier}: top_similarity")
    return top, ranking


