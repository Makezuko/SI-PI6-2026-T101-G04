"""Avaliação sintética: nenhum checkpoint ou currículo real."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from datasets import Dataset
from seqeval.metrics import accuracy_score, classification_report

from src.nlp.evaluate import (
    build_confusion_matrix, consolidate_predictions_by_document,
    entity_table, save_evaluation_tables, select_evaluation_split,
)
from src.nlp.labels import BIO_LABELS, LABEL2ID


class EvaluationTests(unittest.TestCase):
    def test_original_preserves_windows_and_metadata(self):
        dataset = Dataset.from_list([
            {"source_document_id": doc, "chunk_id": chunk, "is_augmented": augmented,
             "offset_mapping": [[1, 2]]}
            for doc, chunk, augmented in [("a", 0, False), ("b", 0, True), ("a", 1, False), ("c", 0, False)]
        ])
        selected = select_evaluation_split(dataset, "train", "original")
        self.assertEqual(list(selected["source_document_id"]), ["a", "a", "c"])
        self.assertEqual(list(selected["chunk_id"]), [0, 1, 0])
        self.assertEqual(selected.column_names, dataset.column_names)
        self.assertIs(select_evaluation_split(dataset, "train", "all"), dataset)
        missing = dataset.remove_columns("is_augmented")
        with self.assertRaisesRegex(ValueError, "is_augmented"):
            select_evaluation_split(missing, "train", "original")
        for split in ["validation", "test"]:
            self.assertIs(select_evaluation_split(missing, split, "original"), missing)

    def test_matrix_counts_order_normalization_accuracy(self):
        gold = [["O", "B-NAME", "I-NAME", "O"]]
        predicted = [["O", "B-NAME", "O", "B-NAME"]]
        matrix, normalized = build_confusion_matrix(gold, predicted)
        expected_tags = ["O"] + [prefix + entity for entity in [
            "COLLEGE_NAME", "COMPANIES_WORKED_AT", "DEGREE", "DESIGNATION",
            "EMAIL_ADDRESS", "GRADUATION_YEAR", "LOCATION", "NAME", "SKILLS",
            "YEARS_OF_EXPERIENCE"] for prefix in ["B-", "I-"]]
        self.assertEqual(BIO_LABELS, expected_tags)
        self.assertEqual(matrix.shape, (21, 21))
        expected = np.zeros((21, 21), dtype=int)
        expected[0, 0] = expected[0, 15] = expected[15, 15] = expected[16, 0] = 1
        np.testing.assert_array_equal(matrix, expected)
        self.assertEqual(matrix.sum(), 4)
        self.assertEqual(matrix.trace() / matrix.sum(), accuracy_score(gold, predicted))
        np.testing.assert_array_equal(normalized[1], np.zeros(21))
        self.assertTrue(np.isfinite(normalized).all())
        self.assertEqual(normalized[0].sum(), 1)
        report = classification_report(gold, predicted, output_dict=True, zero_division=0)
        rows = entity_table(report)
        self.assertEqual(len(rows), 10)
        self.assertNotIn("O", [row["entity"] for row in rows])
        self.assertEqual(rows[0], {"entity": "COLLEGE_NAME", "precision": 0., "recall": 0., "f1-score": 0., "support": 0})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_evaluation_tables(path, gold, predicted, report)
            data = json.loads((path / "confusion_matrix.json").read_text(encoding="utf-8"))
            self.assertEqual(data["labels"], expected_tags)
            self.assertEqual(data["matrix"], expected.tolist())
            with (path / "entity_metrics.csv").open(encoding="utf-8", newline="") as file:
                self.assertEqual(len(list(csv.DictReader(file))), 10)

    def test_overlap_averages_logits_and_excludes_invalid_tokens(self):
        name = LABEL2ID["B-NAME"]
        dataset = Dataset.from_list([
            {"source_document_id": "synthetic-0", "chunk_id": 0,
             "input_ids": [101, 7, 8, 102], "offset_mapping": [[0, 0], [1, 2], [3, 4], [0, 0]]},
            {"source_document_id": "synthetic-0", "chunk_id": 1,
             "input_ids": [101, 8, 9, 102], "offset_mapping": [[0, 0], [3, 4], [5, 6], [0, 0]]},
        ])
        logits = np.zeros((2, 5, 21))  # inclui padding do Trainer
        logits[0, 1, 0] = 5
        logits[0, 2, name] = 6
        logits[1, 1, 0] = 4  # média mantém NAME, mesmo com referência mascarada
        labels = np.array([[-100, 0, name, -100, -100], [-100, -100, -100, -100, -100]])
        class Tokenizer:
            def convert_ids_to_tokens(self, ids):
                return ["synthetic" for _ in ids]
        predicted, gold, details, stats = consolidate_predictions_by_document(dataset, logits, labels, Tokenizer())
        self.assertEqual(predicted, [["O", "B-NAME"]])
        self.assertEqual(predicted, gold)
        self.assertEqual(stats["evaluated_tokens"], 2)
        self.assertEqual(stats["duplicate_token_occurrences_removed"], 1)
        self.assertEqual(stats["tokens_without_gold_label"], 1)
        self.assertEqual(details[0]["tokens"][1]["occurrences"], 2)
        matrix, _ = build_confusion_matrix(gold, predicted)
        self.assertEqual(matrix.sum(), stats["evaluated_tokens"])
        self.assertEqual(matrix.trace() / matrix.sum(), accuracy_score(gold, predicted))


if __name__ == "__main__":
    unittest.main()
