"""Testes determinísticos de agregação, sem modelos, downloads ou banco."""
import copy
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.calcular_aderencia import main
from src.matching.score import calculate_similarity_index


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "aderencia_exemplo.json"


class ScoreTests(unittest.TestCase):
    def setUp(self):
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.requirements = data["requirements"]
        self.results = data["results"]

    def calculate(self, weights=None):
        return calculate_similarity_index(self.requirements, self.results, weights)

    def set_similarity(self, value, index=0):
        self.results[index]["top_similarity"] = value
        self.results[index]["ranking"] = [
            {**self.results[index]["ranking"][0], "similarity": value}]

    def test_known_example_and_contributions(self):
        output = self.calculate()
        self.assertEqual(output["status"], "calculado")
        self.assertAlmostEqual(output["score"], 60)
        self.assertEqual(output["score_name"], "indice_compatibilidade_semantica")
        self.assertEqual(output["formula_version"], "1.0")
        self.assertEqual(output["score"], math.fsum(
            item["contribution_points"] for item in output["details"]))
        self.assertEqual(output["details"][0]["best_evidence"], {
            "text": self.results[0]["ranking"][0]["text"], "source": "project",
            "input_index": 0, "chunk_index": 0})
        json.dumps(output, allow_nan=False)

    def test_weights_and_levels(self):
        output = self.calculate({"obrigatorio": 2, "desejavel": 1})
        self.assertAlmostEqual(output["score"], 64)
        self.assertAlmostEqual(output["indices_by_level"]["obrigatorio"], 70)
        self.assertAlmostEqual(output["indices_by_level"]["desejavel"], 40)
        self.assertEqual([r["weight"] for r in output["details"]], [2, 2, 1])
        self.assertEqual(self.calculate({"desejavel": 3})["weights"]["obrigatorio"], 1)
        for requirement in self.requirements:
            requirement["tipo"] = "comportamental"
        changed = self.calculate({"obrigatorio": 2, "desejavel": 1})
        self.assertEqual(output["score"], changed["score"])
        self.assertEqual([d["weight"] for d in output["details"]],
                         [d["weight"] for d in changed["details"]])

    def test_reordered_results_match_by_id(self):
        expected = self.calculate()
        self.results.reverse()
        self.assertEqual(expected, self.calculate())

    def test_negative_cosine_preserved(self):
        self.set_similarity(-.8)
        output = self.calculate()
        detail = output["details"][0]
        self.assertEqual(detail["original_cosine"], -.8)
        self.assertEqual(detail["aggregation_value"], 0)
        self.assertEqual(detail["contribution_points"], 0)
        self.assertAlmostEqual(output["score"], 100 / 3)

    def test_missing_level_and_empty_groups(self):
        self.requirements[0].pop("nivel")
        self.requirements[1]["nivel"] = None
        output = self.calculate({"obrigatorio": 4, "desejavel": 1})
        self.assertAlmostEqual(output["score"], 60)
        self.assertEqual(len(output["warnings"]), 2)
        self.assertEqual(output["details"][0]["weight"], 1)
        self.assertIsNone(output["indices_by_level"]["obrigatorio"])

    def test_empty_ranking_incomplete_not_zero(self):
        self.results[0]["ranking"] = []
        self.results[0]["top_similarity"] = None
        output = self.calculate()
        self.assertEqual(output["status"], "analise_incompleta")
        self.assertIsNone(output["score"])
        self.assertEqual(output["incomplete_requirement_ids"], ["R1"])
        self.assertIsNone(output["indices_by_level"]["obrigatorio"])
        self.assertAlmostEqual(output["indices_by_level"]["desejavel"], 40)
        self.assertTrue(all(d["contribution_points"] is None for d in output["details"]))
        self.assertIsNone(output["details"][0]["best_evidence"])
        self.assertIsNone(output["details"][0]["aggregation_value"])

    def test_all_incomplete_even_with_numeric_top(self):
        for row in self.results:
            row["ranking"] = []
        output = self.calculate()
        self.assertIsNone(output["score"])
        self.assertEqual(output["incomplete_requirement_ids"], ["R1", "R2", "R3"])
        self.assertEqual(output["indices_by_level"], {"obrigatorio": None, "desejavel": None})
        self.assertTrue(all(d["aggregation_value"] is None for d in output["details"]))
        json.dumps(output, allow_nan=False)

    def test_duplicate_missing_and_extra_ids(self):
        for requirements, results in (
            (self.requirements * 2, self.results),
            (self.requirements, self.results * 2),
            (self.requirements, self.results[:-1]),
            (self.requirements, self.results + [{**self.results[0], "id": "EXTRA"}]),
        ):
            with self.subTest(requirements=requirements, results=results):
                with self.assertRaises(ValueError):
                    calculate_similarity_index(requirements, results)

    def test_invalid_requirements(self):
        for value in ([], None, {}, [None], [{}], [{"id": " ", "text": "Python"}],
                      [{"id": "R1", "text": " "}], [{"id": "R1", "text": 2}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_similarity_index(value, self.results)
        with self.assertRaises(ValueError):
            calculate_similarity_index(self.requirements, None)

    def test_bad_numeric_values_in_top_and_all_ranking_entries(self):
        for value in (float("nan"), float("inf"), -float("inf"), True, False,
                      1.01, -1.01, "0.8", None):
            with self.subTest(value=value):
                self.setUp()
                self.results[0]["top_similarity"] = value
                with self.assertRaises(ValueError):
                    self.calculate()
                self.setUp()
                self.results[0]["ranking"][1]["similarity"] = value
                with self.assertRaises(ValueError):
                    self.calculate()

    def test_numeric_tolerance_and_boundaries(self):
        for value, expected in ((1 + 5e-10, 1), (-1 - 5e-10, 0)):
            self.set_similarity(value)
            output = self.calculate()
            self.assertEqual(output["details"][0]["original_cosine"], value)
            self.assertEqual(output["details"][0]["aggregation_value"], expected)
        self.set_similarity(.8)
        self.results[0]["ranking"][0]["similarity"] += 5e-10
        self.calculate()
        for value in (0, 1, -1):
            for index in range(3):
                self.set_similarity(value, index)
            self.assertEqual(self.calculate()["score"], 100 * max(0, value))

    def test_bad_weights_and_level(self):
        for weights in ([], True, {"unknown": 1}, {"obrigatorio": 0},
                        {"obrigatorio": -1}, {"desejavel": True},
                        {"desejavel": float("nan")}, {"desejavel": float("inf")},
                        {"obrigatorio": "2"}):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                self.calculate(weights)
        for level in ("", "Obrigatório", "senior", [], True):
            self.requirements[0]["nivel"] = level
            with self.subTest(level=level), self.assertRaises(ValueError):
                self.calculate()

    def test_large_finite_weights(self):
        self.assertAlmostEqual(self.calculate({"obrigatorio": 1e308,
                                               "desejavel": 1e308})["score"], 60)

    def test_ranking_required_order_and_coherence(self):
        for mutation in (lambda row: row.pop("ranking"),
                         lambda row: row.update(ranking=None),
                         lambda row: row["ranking"].reverse(),
                         lambda row: row.update(top_similarity=.9),
                         lambda row: row["ranking"][0].pop("source"),
                         lambda row: row["ranking"][0].update(input_index=True)):
            self.setUp()
            mutation(self.results[0])
            with self.assertRaises(ValueError):
                self.calculate()

    def test_validation_continues_after_empty_ranking(self):
        self.results[0].update(ranking=[], top_similarity=None)
        self.results[1]["top_similarity"] = float("nan")
        with self.assertRaises(ValueError):
            self.calculate()

    def test_annotations_have_no_influence(self):
        expected = self.calculate()
        for item in self.requirements + self.results:
            item.update(acceptable_input_indices=[999], annotation_reason="Ignore",
                        category="no_evidence", hit_at_1=0, mrr=0)
        self.assertEqual(expected, self.calculate())

    def test_no_mutation_or_shared_output_evidence(self):
        weights = {"obrigatorio": 3}
        before = copy.deepcopy((self.requirements, self.results, weights))
        output = self.calculate(weights)
        self.assertEqual(before, (self.requirements, self.results, weights))
        output["details"][0]["best_evidence"]["text"] = "Changed"
        output["weights"]["obrigatorio"] = 10
        self.assertEqual(before, (self.requirements, self.results, weights))

    def test_actual_compare_contract(self):
        from src.matching.semantic import compare
        requirements = [{"id": "R", "text": "Python"}]
        resume = {"records": [{"text": "Python", "source": "skill",
                               "input_index": 0, "chunk_index": 0}], "embeddings": [[1, 0]]}
        rows, _ = compare(requirements, [[1, 0]], resume)
        self.assertEqual(calculate_similarity_index(requirements, rows)["score"], 100)


class CliTests(unittest.TestCase):
    def test_example_and_weights_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "result.json"
            weights = Path(directory) / "weights.json"
            weights.write_text('{"obrigatorio": 2, "desejavel": 1}', encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                main(["--input", str(EXAMPLE), "--output", str(output)])
            self.assertIn("60.00/100", stdout.getvalue())
            self.assertAlmostEqual(json.loads(output.read_text(encoding="utf-8"))["score"], 60)
            with redirect_stdout(io.StringIO()):
                main(["--input", str(EXAMPLE), "--output", str(output), "--weights", str(weights)])
            self.assertAlmostEqual(json.loads(output.read_text(encoding="utf-8"))["score"], 64)

    def test_invalid_files_and_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            path, output = Path(directory) / "input.json", Path(directory) / "output.json"
            for content in ("invalid", "[]", "{}", '{"requirements": [], "results": []}'):
                path.write_text(content, encoding="utf-8")
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                    main(["--input", str(path), "--output", str(output)])
                self.assertEqual(caught.exception.code, 1)
                self.assertIn("Não foi possível", stderr.getvalue())
                self.assertFalse(output.exists())
            data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            data["results"][0].update(ranking=[], top_similarity=None)
            path.write_text(json.dumps(data), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                main(["--input", str(path), "--output", str(output)])
            self.assertIn("Análise incompleta", stdout.getvalue())
            self.assertNotIn("/100", stdout.getvalue())
            self.assertIsNone(json.loads(output.read_text(encoding="utf-8"))["score"])


if __name__ == "__main__":
    unittest.main()
