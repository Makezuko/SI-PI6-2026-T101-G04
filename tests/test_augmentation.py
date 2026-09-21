"""
Testes das principais garantias do data augmentation.
"""

import random
import unittest

from src.augmentation.augment import (
    assert_no_split_leakage,
    augment_resume,
    split_originals,
    validate_resume,
)


class AugmentationTests(unittest.TestCase):

    def setUp(self):
        """
        Cria um currículo pequeno com offsets conhecidos.
        """
        self.resume = {
            "content": "Alex worked at Acme as Developer.",
            "entidades": [
                {
                    "start": 0,
                    "end": 4,
                    "label": "Name",
                },
                {
                    "start": 15,
                    "end": 19,
                    "label": "Companies worked at",
                },
                {
                    "start": 23,
                    "end": 32,
                    "label": "Designation",
                },
            ],
        }

    def test_offsets_after_larger_replacements(self):
        """
        Verifica se os offsets continuam corretos quando os novos textos
        são maiores do que os textos originais.
        """
        value_bank = {
            "name": [
                "Alexandra Johnson",
            ],
            "companies worked at": [
                "Northstar Technologies",
            ],
            "designation": [
                "Machine Learning Engineer",
            ],
        }

        augmented, replacements = augment_resume(
            resume=self.resume,
            value_bank=value_bank,
            rng=random.Random(42),
            replacement_probability=1.0,
            max_replacements=3,
        )

        self.assertEqual(replacements, 3)

        # Não deve existir nenhum erro de offset.
        self.assertEqual(
            validate_resume(augmented),
            [],
        )

        extracted_entities = [
            augmented["content"][
                entity["start"]:entity["end"]
            ]
            for entity in augmented["entidades"]
        ]

        self.assertEqual(
            extracted_entities,
            [
                "Alexandra Johnson",
                "Northstar Technologies",
                "Machine Learning Engineer",
            ],
        )

    def test_split_is_reproducible(self):
        """
        A mesma semente deve produzir exatamente o mesmo split.
        """
        dataset = [
            {
                "content": f"Resume {index}",
                "entidades": [],
            }
            for index in range(20)
        ]

        split_a = split_originals(
            dataset=dataset,
            train_ratio=0.70,
            validation_ratio=0.15,
            seed=42,
        )

        split_b = split_originals(
            dataset=dataset,
            train_ratio=0.70,
            validation_ratio=0.15,
            seed=42,
        )

        self.assertEqual(split_a, split_b)

    def test_no_leakage_between_splits(self):
        """
        Verifica que não existem currículos repetidos entre os splits.
        """
        dataset = [
            {
                "content": f"Resume {index}",
                "entidades": [],
            }
            for index in range(20)
        ]

        train, validation, test = split_originals(
            dataset=dataset,
            train_ratio=0.70,
            validation_ratio=0.15,
            seed=42,
        )

        # A função gera erro se encontrar vazamento.
        assert_no_split_leakage(
            train_original=train,
            validation=validation,
            test=test,
        )


if __name__ == "__main__":
    unittest.main()