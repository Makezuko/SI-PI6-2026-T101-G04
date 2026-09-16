"""
Inferência do modelo NER em currículos completos.

O DistilBERT aceita no máximo 512 tokens. Por isso, currículos longos são
divididos em janelas parcialmente sobrepostas.

As previsões repetidas nas regiões de sobreposição são consolidadas pela
média dos logits. Depois, os rótulos BIO são convertidos novamente em
entidades com:

- label;
- texto;
- start;
- end;
- confiança.

Exemplo:

    python -m src.nlp.inference \
        --model-dir models/ner/augmented/best_model \
        --input resume.txt \
        --output prediction.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
)


DEFAULT_MODEL_DIRECTORY = Path(
    "models/ner/augmented/best_model"
)

DEFAULT_MAX_LENGTH = 512
DEFAULT_STRIDE = 128


class ResumeNERPredictor:
    """
    Carrega o modelo treinado e extrai entidades de currículos.
    """

    def __init__(
        self,
        model_directory: Path | str = DEFAULT_MODEL_DIRECTORY,
        max_length: int = DEFAULT_MAX_LENGTH,
        stride: int = DEFAULT_STRIDE,
        device: str | None = None,
    ) -> None:
        self.model_directory = Path(
            model_directory
        )

        if not self.model_directory.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado: "
                f"{self.model_directory}"
            )

        self.max_length = max_length
        self.stride = stride

        if device is None:
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

        self.device = torch.device(
            device
        )

        self.tokenizer = (
            AutoTokenizer.from_pretrained(
                str(self.model_directory),
                use_fast=True,
            )
        )

        # O texto será dividido manualmente em janelas.
        self.tokenizer.model_max_length = (
            1_000_000
        )

        self.model = (
            AutoModelForTokenClassification
            .from_pretrained(
                str(self.model_directory)
            )
        )

        self.model.to(
            self.device
        )

        self.model.eval()

        self.id2label = {
            int(label_id): label
            for label_id, label
            in self.model.config.id2label.items()
        }

    def _create_windows(
        self,
        text: str,
    ) -> list[dict[str, Any]]:
        """
        Tokeniza o texto completo e cria janelas de até max_length.
        """
        encoding = self.tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
            padding=False,
        )

        all_input_ids = encoding[
            "input_ids"
        ]

        all_offsets = encoding[
            "offset_mapping"
        ]

        if not all_input_ids:
            return []

        cls_token_id = (
            self.tokenizer.cls_token_id
        )

        sep_token_id = (
            self.tokenizer.sep_token_id
        )

        if cls_token_id is None:
            raise ValueError(
                "Tokenizer sem token [CLS]."
            )

        if sep_token_id is None:
            raise ValueError(
                "Tokenizer sem token [SEP]."
            )

        special_tokens = 2

        content_window_size = (
            self.max_length
            - special_tokens
        )

        if self.stride >= content_window_size:
            raise ValueError(
                "stride deve ser menor que o tamanho "
                "da janela de conteúdo."
            )

        window_step = (
            content_window_size
            - self.stride
        )

        windows = []
        window_start = 0
        chunk_id = 0

        while window_start < len(
            all_input_ids
        ):
            window_end = min(
                window_start
                + content_window_size,
                len(all_input_ids),
            )

            content_ids = all_input_ids[
                window_start:window_end
            ]

            content_offsets = all_offsets[
                window_start:window_end
            ]

            input_ids = [
                cls_token_id,
                *content_ids,
                sep_token_id,
            ]

            offsets = [
                (0, 0),
                *content_offsets,
                (0, 0),
            ]

            attention_mask = [
                1
                for _ in input_ids
            ]

            windows.append(
                {
                    "chunk_id": chunk_id,
                    "input_ids": input_ids,
                    "attention_mask": (
                        attention_mask
                    ),
                    "offset_mapping": offsets,
                }
            )

            chunk_id += 1

            if window_end == len(
                all_input_ids
            ):
                break

            window_start += window_step

        return windows

    def _predict_tokens(
        self,
        text: str,
    ) -> list[dict[str, Any]]:
        """
        Executa o modelo e consolida tokens repetidos entre janelas.
        """
        windows = self._create_windows(
            text
        )

        if not windows:
            return []

        # Chave: (start, end)
        consolidated_tokens: dict[
            tuple[int, int],
            dict[str, Any],
        ] = {}

        with torch.no_grad():
            for window in windows:
                input_ids = torch.tensor(
                    [
                        window["input_ids"]
                    ],
                    dtype=torch.long,
                    device=self.device,
                )

                attention_mask = torch.tensor(
                    [
                        window[
                            "attention_mask"
                        ]
                    ],
                    dtype=torch.long,
                    device=self.device,
                )

                output = self.model(
                    input_ids=input_ids,
                    attention_mask=(
                        attention_mask
                    ),
                )

                logits = (
                    output.logits[0]
                    .detach()
                    .cpu()
                )

                for token_index, (
                    start,
                    end,
                ) in enumerate(
                    window["offset_mapping"]
                ):
                    start = int(start)
                    end = int(end)

                    # Ignora [CLS] e [SEP].
                    if start == end:
                        continue

                    token_key = (
                        start,
                        end,
                    )

                    token_logits = logits[
                        token_index
                    ]

                    if (
                        token_key
                        not in consolidated_tokens
                    ):
                        consolidated_tokens[
                            token_key
                        ] = {
                            "start": start,
                            "end": end,
                            "token_id": window[
                                "input_ids"
                            ][token_index],
                            "logits_sum": (
                                torch.zeros_like(
                                    token_logits
                                )
                            ),
                            "count": 0,
                            "chunk_ids": [],
                        }

                    record = consolidated_tokens[
                        token_key
                    ]

                    record["logits_sum"] += (
                        token_logits
                    )

                    record["count"] += 1

                    record[
                        "chunk_ids"
                    ].append(
                        window["chunk_id"]
                    )

        token_predictions = []

        for record in sorted(
            consolidated_tokens.values(),
            key=lambda item: (
                item["start"],
                item["end"],
            ),
        ):
            mean_logits = (
                record["logits_sum"]
                / record["count"]
            )

            probabilities = torch.softmax(
                mean_logits,
                dim=-1,
            )

            predicted_id = int(
                torch.argmax(
                    probabilities
                ).item()
            )

            confidence = float(
                probabilities[
                    predicted_id
                ].item()
            )

            label = self.id2label[
                predicted_id
            ]

            token = (
                self.tokenizer
                .convert_ids_to_tokens(
                    [
                        record["token_id"]
                    ]
                )[0]
            )

            token_predictions.append(
                {
                    "token": token,
                    "start": record[
                        "start"
                    ],
                    "end": record[
                        "end"
                    ],
                    "label": label,
                    "confidence": confidence,
                    "occurrences": record[
                        "count"
                    ],
                }
            )

        return token_predictions

    @staticmethod
    def _split_bio_label(
        label: str,
    ) -> tuple[str, str | None]:
        """
        Separa B-SKILLS em ("B", "SKILLS").
        """
        if label == "O":
            return "O", None

        if "-" not in label:
            return "O", None

        prefix, entity_type = (
            label.split(
                "-",
                maxsplit=1,
            )
        )

        if prefix not in {
            "B",
            "I",
        }:
            return "O", None

        return prefix, entity_type

    def _tokens_to_entities(
        self,
        text: str,
        token_predictions: list[
            dict[str, Any]
        ],
        minimum_confidence: float,
    ) -> list[dict[str, Any]]:
        """
        Converte previsões BIO em entidades de caracteres.
        """
        entities = []
        current_entity = None

        def close_current_entity() -> None:
            nonlocal current_entity

            if current_entity is None:
                return

            average_confidence = (
                sum(
                    current_entity[
                        "token_confidences"
                    ]
                )
                / len(
                    current_entity[
                        "token_confidences"
                    ]
                )
            )

            entity_text = text[
                current_entity["start"]:
                current_entity["end"]
            ]

            if (
                average_confidence
                >= minimum_confidence
                and entity_text.strip()
            ):
                entities.append(
                    {
                        "label": (
                            current_entity[
                                "label"
                            ]
                        ),
                        "text": (
                            entity_text.strip()
                        ),
                        "start": (
                            current_entity[
                                "start"
                            ]
                        ),
                        "end": (
                            current_entity[
                                "end"
                            ]
                        ),
                        "confidence": (
                            average_confidence
                        ),
                    }
                )

            current_entity = None

        for token in token_predictions:
            prefix, entity_type = (
                self._split_bio_label(
                    token["label"]
                )
            )

            if prefix == "O":
                close_current_entity()
                continue

            starts_new_entity = (
                prefix == "B"
                or current_entity is None
                or current_entity[
                    "label"
                ] != entity_type
            )

            if starts_new_entity:
                close_current_entity()

                current_entity = {
                    "label": entity_type,
                    "start": token["start"],
                    "end": token["end"],
                    "token_confidences": [
                        token["confidence"]
                    ],
                }

            else:
                current_entity["end"] = (
                    token["end"]
                )

                current_entity[
                    "token_confidences"
                ].append(
                    token["confidence"]
                )

        close_current_entity()

        return entities

    def predict(
        self,
        text: str,
        minimum_confidence: float = 0.0,
        include_tokens: bool = False,
    ) -> dict[str, Any]:
        """
        Extrai entidades de um currículo.
        """
        token_predictions = (
            self._predict_tokens(
                text
            )
        )

        entities = self._tokens_to_entities(
            text=text,
            token_predictions=(
                token_predictions
            ),
            minimum_confidence=(
                minimum_confidence
            ),
        )

        result = {
            "model": str(
                self.model_directory
            ),
            "device": str(
                self.device
            ),
            "text_length": len(text),
            "entity_count": len(
                entities
            ),
            "entities": entities,
        }

        if include_tokens:
            result[
                "token_predictions"
            ] = token_predictions

        return result


def parse_args() -> argparse.Namespace:
    """
    Argumentos da linha de comando.
    """
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--model-dir",
        type=Path,
        default=(
            DEFAULT_MODEL_DIRECTORY
        ),
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help=(
            "Arquivo TXT contendo o currículo."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "reports/inference.json"
        ),
    )

    parser.add_argument(
        "--minimum-confidence",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--include-tokens",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    """
    Executa a inferência pela linha de comando.
    """
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            f"Currículo não encontrado: "
            f"{args.input}"
        )

    text = args.input.read_text(
        encoding="utf-8"
    )

    predictor = ResumeNERPredictor(
        model_directory=args.model_dir
    )

    result = predictor.predict(
        text=text,
        minimum_confidence=(
            args.minimum_confidence
        ),
        include_tokens=(
            args.include_tokens
        ),
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Entidades encontradas: "
        f"{result['entity_count']}"
    )

    print(
        f"Resultado salvo em: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()