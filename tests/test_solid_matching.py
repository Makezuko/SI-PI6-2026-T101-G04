"""Testes de OCP e LSP para as estratégias de aderência documental em src/matching/."""
import copy
import math
import unittest

from src.matching.adherence import calculate_adherence
from src.matching.aggregators import (
    AdherenceScoreStrategy,
    ProvisionalWeightedAdherence,
    StrictMandatoryAdherence,
    WeightedConfirmedAdherence,
)


def _decision(req_id: str, estado: str, text: str = "Evidência") -> dict:
    evidences = [{"text": text, "source": "skill"}] if estado == "atendido" else []
    return {
        "id": req_id,
        "estado": estado,
        "justificativa": f"Decisão registrada: {estado}.",
        "evidencias": evidences,
    }


class CustomCeilingAdherenceStrategy:
    """Estratégia definida fora de src/matching para comprovar OCP sem editar adherence.py."""

    @property
    def version(self) -> str:
        return "3.1-custom-ceiling"

    def compute(
        self, details: list[dict], scale: float
    ) -> tuple[float, float, list[float]]:
        score, maximum_score, contributions = WeightedConfirmedAdherence().compute(
            details, scale
        )
        if score > 80.0:
            factor = 80.0 / score
            contributions = [c * factor for c in contributions]
            score = math.fsum(contributions)
            maximum_score = max(score, min(maximum_score, 80.0))
        return score, maximum_score, contributions


class SolidMatchingTests(unittest.TestCase):
    def setUp(self):
        self.requirements = [
            {"id": "req-1", "text": "Python", "tipo": "tecnico", "nivel": "obrigatorio"},
            {"id": "req-2", "text": "SQL", "tipo": "tecnico", "nivel": "desejavel"},
        ]
        self.decisions_all_met = [
            _decision("req-1", "atendido", "Python 5 anos"),
            _decision("req-2", "atendido", "SQL avançado"),
        ]
        self.decisions_mandatory_missing = [
            _decision("req-1", "nao_identificado"),
            _decision("req-2", "atendido", "SQL avançado"),
        ]
        self.decisions_mixed_provisional = [
            _decision("req-1", "atendido", "Python 5 anos"),
            _decision("req-2", "revisao_necessaria"),
        ]

    def test_ocp_default_preserves_3_1_experimental_behavior(self):
        default_out = calculate_adherence(self.requirements, self.decisions_mixed_provisional)
        explicit_out = calculate_adherence(
            self.requirements,
            self.decisions_mixed_provisional,
            strategy=WeightedConfirmedAdherence(),
        )
        self.assertEqual(default_out["formula_version"], "3.1-experimental")
        self.assertAlmostEqual(default_out["score"], explicit_out["score"])
        self.assertAlmostEqual(default_out["maximum_score"], explicit_out["maximum_score"])

    def test_ocp_extends_adherence_without_modifying_adherence_module(self):
        strict = calculate_adherence(
            self.requirements,
            [
                _decision("req-1", "nao_identificado"),
                _decision("req-2", "atendido", "SQL"),
            ],
            weights={"obrigatorio": 1.0, "desejavel": 2.0},
            strategy=StrictMandatoryAdherence(max_score_when_missing=49.9),
        )
        provisional = calculate_adherence(
            self.requirements,
            self.decisions_mixed_provisional,
            strategy=ProvisionalWeightedAdherence(provisional_factor=0.5),
        )
        custom = calculate_adherence(
            self.requirements,
            self.decisions_all_met,
            strategy=CustomCeilingAdherenceStrategy(),
        )

        self.assertEqual(strict["formula_version"], "3.1-strict-mandatory")
        self.assertLessEqual(strict["score"], 49.9 + 1e-9)
        self.assertEqual(provisional["formula_version"], "3.1-provisional-weighted")
        self.assertAlmostEqual(provisional["score"], (200.0 / 3.0) + (100.0 / 3.0) * 0.5)
        self.assertEqual(custom["formula_version"], "3.1-custom-ceiling")
        self.assertAlmostEqual(custom["score"], 80.0)

    def test_rejects_invalid_strategy(self):
        with self.assertRaises(TypeError):
            calculate_adherence(self.requirements, self.decisions_all_met, strategy=object())

    def test_lsp_contract_for_all_adherence_strategies(self):
        """Mesmo conjunto de invariantes executado contra todas as implementações (LSP)."""
        strategies: list[AdherenceScoreStrategy] = [
            WeightedConfirmedAdherence(),
            StrictMandatoryAdherence(),
            ProvisionalWeightedAdherence(),
            CustomCeilingAdherenceStrategy(),
        ]
        scenarios = [
            self.decisions_all_met,
            self.decisions_mandatory_missing,
            self.decisions_mixed_provisional,
            [
                _decision("req-1", "nao_identificado"),
                _decision("req-2", "nao_identificado"),
            ],
        ]
        for strategy in strategies:
            self.assertIsInstance(strategy, AdherenceScoreStrategy)
            self.assertIsInstance(strategy.version, str)
            self.assertTrue(strategy.version.strip())
            for scenario in scenarios:
                req_copy = copy.deepcopy(self.requirements)
                dec_copy = copy.deepcopy(scenario)
                output = calculate_adherence(req_copy, dec_copy, strategy=strategy)
                self.assertEqual(output["status"], "calculado")
                self.assertGreaterEqual(output["score"], 0.0)
                self.assertLessEqual(output["score"], output["maximum_score"] + 1e-9)
                self.assertLessEqual(output["maximum_score"], 100.0 + 1e-9)
                contributions = [item["contribution_points"] for item in output["details"]]
                self.assertEqual(len(contributions), len(self.requirements))
                self.assertTrue(all(c >= 0.0 for c in contributions))
                self.assertAlmostEqual(math.fsum(contributions), output["score"], places=6)
                self.assertEqual(req_copy, self.requirements)
                self.assertEqual(dec_copy, scenario)


if __name__ == "__main__":
    unittest.main()
