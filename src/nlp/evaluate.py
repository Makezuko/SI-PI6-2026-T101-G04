"""
Avaliação detalhada de um modelo NER treinado.

Este script:

1. carrega o modelo salvo;
2. avalia validation ou test;
3. calcula precisão, recall, F1 e acurácia;
4. gera métricas por entidade;
5. registra exemplos de tokens classificados incorretamente.

Exemplo:

    python -m src.nlp.evaluate \
        --model-dir models/ner/augmented/best_model \
        --split test
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from datasets import Dataset, load_from_disk
from seqeval.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
)
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

from src.nlp.labels import ID2LABEL


MODEL_COLUMNS = {
    "input_ids",
    "attention_mask",
    "labels",
    "token_type_ids",
}


def save_json(
    data: Any,
    path: Path,
) -> None:
    """
    Salva resultados em JSON.
    """
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )


def remove_auxiliary_columns(
    dataset: Dataset,
) -> Dataset:
    """
    Mantém somente as colunas aceitas pelo modelo.
    """
    columns_to_remove = [
        column
        for column in dataset.column_names
        if column not in MODEL_COLUMNS
    ]

    if columns_to_remove:
        dataset = dataset.remove_columns(
            columns_to_remove
        )

    return dataset


def convert_to_bio_sequences(
    predictions: np.ndarray,
    label_ids: np.ndarray,
) -> tuple[
    list[list[str]],
    list[list[str]],
    np.ndarray,
]:
    """
    Converte IDs para sequências BIO e retorna também os IDs previstos.
    """
    predicted_ids = np.argmax(
        predictions,
        axis=-1,
    )

    prediction_sequences = []
    label_sequences = []

    for predicted_sequence, label_sequence in zip(
        predicted_ids,
        label_ids,
    ):
        current_predictions = []
        current_labels = []

        for predicted_id, label_id in zip(
            predicted_sequence,
            label_sequence,
        ):
            if label_id == -100:
                continue

            current_predictions.append(
                ID2LABEL[int(predicted_id)]
            )

            current_labels.append(
                ID2LABEL[int(label_id)]
            )

        prediction_sequences.append(
            current_predictions
        )

        label_sequences.append(
            current_labels
        )

    return (
        prediction_sequences,
        label_sequences,
        predicted_ids,
    )


def collect_error_examples(
    original_dataset: Dataset,
    predicted_ids: np.ndarray,
    label_ids: np.ndarray,
    tokenizer,
    maximum_examples: int,
) -> list[dict[str, Any]]:
    """
    Coleta janelas que possuem pelo menos uma classificação incorreta.

    Os exemplos ajudam na análise qualitativa do modelo.
    """
    errors = []

    for example_index, (
        predicted_sequence,
        label_sequence,
    ) in enumerate(
        zip(
            predicted_ids,
            label_ids,
        )
    ):
        example = original_dataset[
            example_index
        ]

        tokens = tokenizer.convert_ids_to_tokens(
            example["input_ids"]
        )

        token_errors = []

        for token, predicted_id, label_id in zip(
            tokens,
            predicted_sequence,
            label_sequence,
        ):
            if label_id == -100:
                continue

            if predicted_id == label_id:
                continue

            token_errors.append(
                {
                    "token": token,
                    "expected": ID2LABEL[
                        int(label_id)
                    ],
                    "predicted": ID2LABEL[
                        int(predicted_id)
                    ],
                }
            )

        if not token_errors:
            continue

        errors.append(
            {
                "dataset_index": example_index,
                "source_document_id": example.get(
                    "source_document_id"
                ),
                "chunk_id": example.get(
                    "chunk_id"
                ),
                "errors": token_errors[:50],
            }
        )

        if len(errors) >= maximum_examples:
            break

    return errors


def parse_args() -> argparse.Namespace:
    """
    Define os argumentos da avaliação.
    """
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--model-dir",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(
            "data/processed/huggingface_ner"
        ),
    )

    parser.add_argument(
        "--split",
        choices=[
            "validation",
            "test",
        ],
        default="test",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "reports/ner"
        ),
    )

    parser.add_argument(
        "--eval-batch-size",
        type=int,
        default=8,
    )

    parser.add_argument(
        "--maximum-error-examples",
        type=int,
        default=100,
    )

    return parser.parse_args()


def main() -> None:
    """
    Executa a avaliação detalhada.
    """
    args = parse_args()

    if not args.model_dir.exists():
        raise FileNotFoundError(
            f"Modelo não encontrado: "
            f"{args.model_dir}"
        )

    if not args.dataset_dir.exists():
        raise FileNotFoundError(
            f"Dataset não encontrado: "
            f"{args.dataset_dir}"
        )

    dataset = load_from_disk(
        str(args.dataset_dir)
    )

    original_split = dataset[
        args.split
    ]

    model_split = remove_auxiliary_columns(
        original_split
    )

    tokenizer = AutoTokenizer.from_pretrained(
        str(args.model_dir),
        use_fast=True,
    )

    model = (
        AutoModelForTokenClassification
        .from_pretrained(
            str(args.model_dir)
        )
    )

    data_collator = (
        DataCollatorForTokenClassification(
            tokenizer=tokenizer,
            padding=True,
            label_pad_token_id=-100,
            return_tensors="pt",
        )
    )

    temporary_output = (
        args.output_dir
        / "temporary_trainer"
    )

    training_arguments = TrainingArguments(
        output_dir=str(temporary_output),
        per_device_eval_batch_size=(
            args.eval_batch_size
        ),
        report_to="none",
        dataloader_num_workers=0,
        remove_unused_columns=True,
    )

    trainer = Trainer(
        model=model,
        args=training_arguments,
        data_collator=data_collator,
        processing_class=tokenizer,
    )

    prediction_output = trainer.predict(
        model_split
    )

    raw_predictions = (
        prediction_output.predictions
    )

    if isinstance(
        raw_predictions,
        tuple,
    ):
        raw_predictions = (
            raw_predictions[0]
        )

    (
        prediction_sequences,
        label_sequences,
        predicted_ids,
    ) = convert_to_bio_sequences(
        predictions=raw_predictions,
        label_ids=prediction_output.label_ids,
    )

    detailed_report = classification_report(
        label_sequences,
        prediction_sequences,
        output_dict=True,
        zero_division=0,
    )

    summary_metrics = {
        "model": str(args.model_dir),
        "split": args.split,
        "examples": len(original_split),
        "precision": precision_score(
            label_sequences,
            prediction_sequences,
            zero_division=0,
        ),
        "recall": recall_score(
            label_sequences,
            prediction_sequences,
            zero_division=0,
        ),
        "f1": f1_score(
            label_sequences,
            prediction_sequences,
            zero_division=0,
        ),
        "accuracy": accuracy_score(
            label_sequences,
            prediction_sequences,
        ),
        "test_loss": float(
            prediction_output.metrics.get(
                "test_loss",
                0.0,
            )
        ),
    }

    error_examples = collect_error_examples(
        original_dataset=original_split,
        predicted_ids=predicted_ids,
        label_ids=prediction_output.label_ids,
        tokenizer=tokenizer,
        maximum_examples=(
            args.maximum_error_examples
        ),
    )

    model_name = args.model_dir.parent.name

    result_directory = (
        args.output_dir
        / model_name
        / args.split
    )

    save_json(
        summary_metrics,
        result_directory
        / "metrics.json",
    )

    save_json(
        detailed_report,
        result_directory
        / "classification_report.json",
    )

    save_json(
        error_examples,
        result_directory
        / "error_examples.json",
    )

    print(
        "\nAvaliação concluída!"
    )

    print(
        json.dumps(
            summary_metrics,
            ensure_ascii=False,
            indent=2,
        )
    )

    print(
        f"\nRelatórios salvos em: "
        f"{result_directory}"
    )


if __name__ == "__main__":
    main()