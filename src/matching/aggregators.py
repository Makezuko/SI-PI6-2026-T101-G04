"""Estratégias de pontuação para aderência documental (OCP/LSP)."""
from __future__ import annotations

import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class AdherenceScoreStrategy(Protocol):
    """Contrato para estratégias intercambiáveis de cálculo de aderência documental.

    Pré-condições:
    - ``details`` é uma lista não vazia de dicionários contendo ``peso`` (> 0),
      ``max_points`` (> 0), ``estado``, ``compatible`` e ``nivel``.
    - ``scale`` é um número finito estritamente positivo.

    Pós-condições:
    - Retorna ``(score, maximum_score, contributions)``.
    - ``0.0 <= score <= maximum_score <= 100.0 + 1e-9``.
    - ``len(contributions) == len(details)`` e cada contribuição é ``>= 0.0``.
    - ``math.fsum(contributions) == pytest/math.isclose(score)``.
    - Não muta ``details`` nem seus itens.
    """

    @property
    def version(self) -> str:
        """Identificador da versão da fórmula de aderência."""
        ...

    def compute(
        self, details: list[dict], scale: float
    ) -> tuple[float, float, list[float]]:
        """Calcula ``(score, maximum_score, contributions)`` para os requisitos avaliados."""
        ...


def _base_totals(details: list[dict], scale: float) -> tuple[float, float, float]:
    total = math.fsum(item["peso"] / scale for item in details)
    pending = math.fsum(
        item["peso"] / scale for item in details if item["estado"] == "revisao_necessaria"
    )
    confirmed = math.fsum(
        item["peso"] / scale for item in details if item["estado"] == "atendido"
    )
    return total, pending, confirmed


class WeightedConfirmedAdherence:
    """Estratégia padrão (v3.1-experimental): pontua apenas requisitos atendidos."""

    @property
    def version(self) -> str:
        return "3.1-experimental"

    def compute(
        self, details: list[dict], scale: float
    ) -> tuple[float, float, list[float]]:
        total, pending, confirmed = _base_totals(details, scale)
        contributions = [
            float(item["max_points"]) if item["compatible"] else 0.0 for item in details
        ]
        score = 100.0 * confirmed / total
        maximum_score = 100.0 * (confirmed + pending) / total
        return score, maximum_score, contributions


class StrictMandatoryAdherence:
    """Limita a nota quando um requisito obrigatório tem estado 'nao_identificado'."""

    def __init__(self, max_score_when_missing: float = 49.9) -> None:
        if not 0.0 <= max_score_when_missing <= 100.0:
            raise ValueError("max_score_when_missing deve estar entre 0.0 e 100.0.")
        self.max_score_when_missing = float(max_score_when_missing)

    @property
    def version(self) -> str:
        return "3.1-strict-mandatory"

    def compute(
        self, details: list[dict], scale: float
    ) -> tuple[float, float, list[float]]:
        total, pending, confirmed = _base_totals(details, scale)
        contributions = [
            float(item["max_points"]) if item["compatible"] else 0.0 for item in details
        ]
        score = 100.0 * confirmed / total
        maximum_score = 100.0 * (confirmed + pending) / total
        mandatory_missing = any(
            item["nivel"] == "obrigatorio" and item["estado"] == "nao_identificado"
            for item in details
        )
        if mandatory_missing and score > self.max_score_when_missing:
            factor = (
                self.max_score_when_missing / score
                if score > 0.0 and self.max_score_when_missing > 0.0
                else 0.0
            )
            contributions = [value * factor for value in contributions]
            score = math.fsum(contributions)
            maximum_score = max(score, min(maximum_score, self.max_score_when_missing))
        return score, maximum_score, contributions


class ProvisionalWeightedAdherence:
    """Atribui peso parcial configurável a itens em 'revisao_necessaria'."""

    def __init__(self, provisional_factor: float = 0.5) -> None:
        if not 0.0 <= provisional_factor <= 1.0:
            raise ValueError("provisional_factor deve estar entre 0.0 e 1.0.")
        self.provisional_factor = float(provisional_factor)

    @property
    def version(self) -> str:
        return "3.1-provisional-weighted"

    def compute(
        self, details: list[dict], scale: float
    ) -> tuple[float, float, list[float]]:
        total, pending, confirmed = _base_totals(details, scale)
        contributions = []
        for item in details:
            if item["estado"] == "atendido":
                contributions.append(float(item["max_points"]))
            elif item["estado"] == "revisao_necessaria":
                contributions.append(float(item["max_points"]) * self.provisional_factor)
            else:
                contributions.append(0.0)
        score = math.fsum(contributions)
        maximum_score = 100.0 * (confirmed + pending) / total
        return score, maximum_score, contributions
