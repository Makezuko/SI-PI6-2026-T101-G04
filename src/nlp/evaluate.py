"""
Avaliação consolidada de um modelo NER.

O dataset foi dividido em janelas porque o DistilBERT aceita no máximo
512 tokens. Essas janelas podem compartilhar tokens por causa do stride.

Avaliar cada janela separadamente pode:

- contar uma entidade mais de uma vez;
- fragmentar entidades longas;
- alterar o support do relatório;
- prejudicar especialmente blocos longos como Skills.

Este script faz a inferência por janela, mas consolida as previsões por
currículo antes de calcular as métricas.

Processo:

1. carrega o modelo e o dataset;
2. executa a inferência nas janelas;
3. agrupa janelas pelo source_document_id;
4. identifica tokens repetidos por seus offsets globais;
5. calcula a média dos logits das ocorrências repetidas;
6. ordena os tokens pela posição original no currículo;
7. reconstrói uma sequência BIO por currículo;
8. calcula precisão, recall, F1 e acurácia;
9. gera relatório por entidade e exemplos de erro.

Exemplo:

    python -m src.nlp.evaluate \
        --model-dir models/ner/augmented/best_model \
        --split test
"""

from __future__ import annotations

import argparse
import csv
import warnings
import platform
from importlib.metadata import version, PackageNotFoundError
import json
from collections import defaultdict
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

from src.nlp.labels import ID2LABEL, BIO_LABELS, ENTITY_LABELS, normalize_entity_label


# Somente estas colunas podem ser enviadas diretamente ao modelo.
MODEL_COLUMNS = {
    "input_ids",
    "attention_mask",
    "labels",
    "token_type_ids",
}


def convert_numpy_types(
    value: Any,
) -> Any:
    """
    Converte tipos NumPy para tipos nativos do Python.

    Isso evita que valores como support sejam gravados como texto no JSON.
    """
    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, dict):
        return {
            key: convert_numpy_types(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            convert_numpy_types(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            convert_numpy_types(item)
            for item in value
        ]

    return value


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

    safe_data = convert_numpy_types(
        data
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            safe_data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def remove_auxiliary_columns(
    dataset: Dataset,
) -> Dataset:
    """
    Remove os campos de auditoria antes de enviar os dados ao modelo.

    O dataset original não é alterado. Ele continuará disponível para
    a consolidação por documento.
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


def validate_required_columns(
    dataset: Dataset,
) -> None:
    """
    Confirma que o dataset possui os campos necessários para reconstruir
    os currículos.
    """
    required_columns = {
        "input_ids",
        "labels",
        "offset_mapping",
        "source_document_id",
        "chunk_id",
    }

    missing_columns = (
        required_columns
        - set(dataset.column_names)
    )

    if missing_columns:
        raise ValueError(
            "O dataset não possui as colunas necessárias "
            "para a avaliação consolidada: "
            f"{sorted(missing_columns)}. "
            "Execute novamente "
            "python -m src.nlp.prepare_ner_dataset."
        )


def consolidate_predictions_by_document(
    original_dataset: Dataset,
    raw_predictions: np.ndarray,
    label_ids: np.ndarray,
    tokenizer,
) -> tuple[
    list[list[str]],
    list[list[str]],
    list[dict[str, Any]],
    dict[str, int],
]:
    """
    Consolida as previsões das janelas em sequências por currículo.

    Cada token é identificado por:

        (source_document_id, start, end)

    Se o mesmo token aparecer em duas janelas sobrepostas, seus logits são
    somados e posteriormente divididos pela quantidade de ocorrências.

    O rótulo verdadeiro é obtido da ocorrência que não está mascarada com
    -100. Tokens especiais possuem offset (0, 0) e são ignorados.

    Retorna:

    - previsões BIO por documento;
    - rótulos BIO verdadeiros por documento;
    - detalhes de tokens para análise de erros;
    - estatísticas da consolidação.
    """
    # Estrutura:
    #
    # documents[document_id][(start, end)] = informações do token
    documents: dict[
        str,
        dict[tuple[int, int], dict[str, Any]],
    ] = defaultdict(dict)

    duplicate_token_occurrences = 0
    ignored_special_tokens = 0
    conflicting_gold_labels = 0

    for example_index in range(
        len(original_dataset)
    ):
        example = original_dataset[
            example_index
        ]

        document_id = str(
            example["source_document_id"]
        )

        chunk_id = int(
            example["chunk_id"]
        )

        input_ids = example[
            "input_ids"
        ]

        offsets = example[
            "offset_mapping"
        ]

        current_labels = label_ids[
            example_index
        ]

        current_logits = raw_predictions[
            example_index
        ]

        # Trainer pode completar os arrays com padding. Usamos apenas
        # a quantidade real de tokens presente no exemplo original.
        sequence_length = min(
            len(input_ids),
            len(offsets),
            len(current_labels),
            len(current_logits),
        )

        for token_index in range(
            sequence_length
        ):
            start = int(
                offsets[token_index][0]
            )

            end = int(
                offsets[token_index][1]
            )

            # [CLS], [SEP] e outros tokens especiais.
            if start == end:
                ignored_special_tokens += 1
                continue

            token_key = (
                start,
                end,
            )

            token_id = int(
                input_ids[token_index]
            )

            gold_label_id = int(
                current_labels[token_index]
            )

            token_logits = np.asarray(
                current_logits[token_index],
                dtype=np.float64,
            )

            document_tokens = documents[
                document_id
            ]

            if token_key not in document_tokens:
                document_tokens[token_key] = {
                    "start": start,
                    "end": end,
                    "token_id": token_id,
                    "logits_sum": np.zeros_like(
                        token_logits,
                        dtype=np.float64,
                    ),
                    "logits_count": 0,
                    "gold_label_id": None,
                    "chunk_ids": [],
                }

            else:
                duplicate_token_occurrences += 1

            token_record = document_tokens[
                token_key
            ]

            token_record["logits_sum"] += (
                token_logits
            )

            token_record[
                "logits_count"
            ] += 1

            token_record[
                "chunk_ids"
            ].append(
                chunk_id
            )

            # -100 significa que o token não deve participar da perda
            # ou da avaliação nessa ocorrência.
            if gold_label_id != -100:
                existing_gold = token_record[
                    "gold_label_id"
                ]

                if existing_gold is None:
                    token_record[
                        "gold_label_id"
                    ] = gold_label_id

                elif existing_gold != gold_label_id:
                    conflicting_gold_labels += 1

                    raise ValueError(
                        "Rótulos verdadeiros diferentes para "
                        f"{document_id}, token {token_key}: "
                        f"{existing_gold} e {gold_label_id}."
                    )

    prediction_sequences: list[
        list[str]
    ] = []

    label_sequences: list[
        list[str]
    ] = []

    document_details: list[
        dict[str, Any]
    ] = []

    missing_gold_tokens = 0
    evaluated_tokens = 0

    # Ordenação estável dos documentos pelo número presente no ID.
    def document_sort_key(
        document_id: str,
    ) -> tuple[str, int]:
        prefix, separator, suffix = (
            document_id.rpartition("-")
        )

        if separator and suffix.isdigit():
            return prefix, int(suffix)

        return document_id, 0

    for document_id in sorted(
        documents,
        key=document_sort_key,
    ):
        document_tokens = documents[
            document_id
        ]

        sorted_token_records = sorted(
            document_tokens.values(),
            key=lambda record: (
                record["start"],
                record["end"],
            ),
        )

        document_predictions = []
        document_labels = []
        token_details = []

        for token_record in sorted_token_records:
            gold_label_id = token_record[
                "gold_label_id"
            ]

            # Em condições normais, todo token aparecerá sem máscara em
            # pelo menos uma janela. Caso contrário, não há rótulo seguro
            # para utilizá-lo na avaliação.
            if gold_label_id is None:
                missing_gold_tokens += 1
                continue

            mean_logits = (
                token_record["logits_sum"]
                / token_record["logits_count"]
            )

            predicted_label_id = int(
                np.argmax(mean_logits)
            )

            predicted_label = ID2LABEL[
                predicted_label_id
            ]

            expected_label = ID2LABEL[
                int(gold_label_id)
            ]

            token_text = (
                tokenizer.convert_ids_to_tokens(
                    [
                        token_record[
                            "token_id"
                        ]
                    ]
                )[0]
            )

            document_predictions.append(
                predicted_label
            )

            document_labels.append(
                expected_label
            )

            token_details.append(
                {
                    "token": token_text,
                    "start": token_record[
                        "start"
                    ],
                    "end": token_record[
                        "end"
                    ],
                    "expected": expected_label,
                    "predicted": predicted_label,
                    "correct": (
                        predicted_label
                        == expected_label
                    ),
                    "occurrences": token_record[
                        "logits_count"
                    ],
                    "chunk_ids": sorted(
                        set(
                            token_record[
                                "chunk_ids"
                            ]
                        )
                    ),
                }
            )

            evaluated_tokens += 1

        prediction_sequences.append(
            document_predictions
        )

        label_sequences.append(
            document_labels
        )

        document_details.append(
            {
                "source_document_id": (
                    document_id
                ),
                "tokens": token_details,
            }
        )

    consolidation_statistics = {
        "windows": len(
            original_dataset
        ),
        "documents": len(
            documents
        ),
        "evaluated_tokens": (
            evaluated_tokens
        ),
        "duplicate_token_occurrences_removed": (
            duplicate_token_occurrences
        ),
        "ignored_special_tokens": (
            ignored_special_tokens
        ),
        "tokens_without_gold_label": (
            missing_gold_tokens
        ),
        "conflicting_gold_labels": (
            conflicting_gold_labels
        ),
    }

    return (
        prediction_sequences,
        label_sequences,
        document_details,
        consolidation_statistics,
    )


def collect_document_error_examples(
    document_details: list[
        dict[str, Any]
    ],
    maximum_examples: int,
    maximum_errors_per_document: int,
) -> list[dict[str, Any]]:
    """
    Coleta erros depois da consolidação das janelas.

    Agora cada exemplo representa um currículo, e não uma janela isolada.
    """
    error_examples = []

    for document in document_details:
        token_errors = [
            {
                "token": token[
                    "token"
                ],
                "start": token[
                    "start"
                ],
                "end": token[
                    "end"
                ],
                "expected": token[
                    "expected"
                ],
                "predicted": token[
                    "predicted"
                ],
                "occurrences": token[
                    "occurrences"
                ],
                "chunk_ids": token[
                    "chunk_ids"
                ],
            }
            for token in document[
                "tokens"
            ]
            if not token["correct"]
        ]

        if not token_errors:
            continue

        error_examples.append(
            {
                "source_document_id": (
                    document[
                        "source_document_id"
                    ]
                ),
                "number_of_errors": len(
                    token_errors
                ),
                "errors": token_errors[
                    :maximum_errors_per_document
                ],
            }
        )

        if (
            len(error_examples)
            >= maximum_examples
        ):
            break

    return error_examples


def count_entity_support(
    report: dict[str, Any],
) -> dict[str, int]:
    """
    Extrai o support de cada entidade para facilitar a comparação com o
    dataset original.
    """
    ignored_keys = {
        "micro avg",
        "macro avg",
        "weighted avg",
    }

    support = {}

    for entity_name, metrics in report.items():
        if entity_name in ignored_keys:
            continue

        if not isinstance(
            metrics,
            dict,
        ):
            continue

        support[entity_name] = int(
            metrics.get(
                "support",
                0,
            )
        )

    return support


def select_evaluation_split(dataset, split, train_subset):
    """Seleciona janelas originais sem remover metadados."""
    if split == "train" and train_subset == "original":
        if "is_augmented" not in dataset.column_names:
            raise ValueError("train original exige a coluna is_augmented; nao e seguro inferir sinteticos.")
        return dataset.filter(lambda row: row["is_augmented"] is False)
    return dataset


def build_confusion_matrix(label_sequences, prediction_sequences):
    """Linhas verdadeiras, colunas previstas; unidade: token consolidado."""
    matrix = np.zeros((len(BIO_LABELS), len(BIO_LABELS)), dtype=np.int64)
    indices = {tag: i for i, tag in enumerate(BIO_LABELS)}
    if len(label_sequences) != len(prediction_sequences):
        raise ValueError("Quantidade de documentos incompativel.")
    for gold, predicted in zip(label_sequences, prediction_sequences):
        if len(gold) != len(predicted):
            raise ValueError("Quantidade de tokens incompativel.")
        for expected, actual in zip(gold, predicted):
            matrix[indices[expected], indices[actual]] += 1
    support = matrix.sum(axis=1, keepdims=True)
    normalized = np.divide(matrix, support, out=np.zeros_like(matrix, dtype=float), where=support != 0)
    return matrix, normalized


def entity_table(report):
    return [{"entity": normalize_entity_label(entity), **report.get(
        normalize_entity_label(entity),
        {"precision": 0.0, "recall": 0.0, "f1-score": 0.0, "support": 0})}
        for entity in ENTITY_LABELS]


def save_evaluation_tables(directory, labels, predictions, report):
    directory.mkdir(parents=True, exist_ok=True)
    rows = entity_table(report)
    save_json(rows, directory / "entity_metrics.json")
    with (directory / "entity_metrics.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["entity", "precision", "recall", "f1-score", "support"])
        writer.writeheader()
        writer.writerows(rows)
    matrix, normalized = build_confusion_matrix(labels, predictions)
    for name, values in [("confusion_matrix", matrix), ("confusion_matrix_normalized", normalized)]:
        save_json({"labels": BIO_LABELS, "rows": "true", "columns": "predicted",
                   "evaluation_unit": "consolidated_token", "matrix": values}, directory / f"{name}.json")
        with (directory / f"{name}.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["true/predicted", *BIO_LABELS])
            writer.writerows([tag, *row] for tag, row in zip(BIO_LABELS, values.tolist()))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        warnings.warn("PNG nao gerado: instale matplotlib (python -m pip install matplotlib).")
        return
    for name, values in [("confusion_matrix", matrix), ("confusion_matrix_normalized", normalized)]:
        fig, ax = plt.subplots(figsize=(17, 15))
        im = ax.imshow(values, cmap="Blues", vmin=0)
        ax.set_xticks(range(len(BIO_LABELS)), BIO_LABELS, rotation=90)
        ax.set_yticks(range(len(BIO_LABELS)), BIO_LABELS)
        ax.set_xlabel("Tag prevista")
        ax.set_ylabel("Tag verdadeira")
        ax.set_title("Tokens consolidados por documento: " + name)
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        fig.savefig(directory / f"{name}.png", dpi=160)
        plt.close(fig)


def library_versions():
    versions = {"python": platform.python_version()}
    for package in ["numpy", "datasets", "transformers", "torch", "accelerate", "seqeval", "matplotlib"]:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


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
            "train",
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

    parser.add_argument(
        "--maximum-errors-per-document",
        type=int,
        default=100,
    )

    parser.add_argument("--train-subset", choices=["original", "all"], default="original")
    parser.add_argument("--overwrite", action="store_true", help="Sobrescrever relatorios existentes com aviso.")
    return parser.parse_args()


def main() -> None:
    """
    Executa a avaliação consolidada por currículo.
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

    if args.split not in dataset:
        raise ValueError(
            f"Split não encontrado: "
            f"{args.split}"
        )

    original_split = select_evaluation_split(dataset[args.split], args.split, args.train_subset)
    if not len(original_split):
        raise ValueError("Nenhuma janela disponivel para a avaliacao solicitada.")
    subset = args.train_subset if args.split == "train" else None
    folder = f"train_{subset}" if args.split == "train" else args.split
    result_directory = args.output_dir / args.model_dir.parent.name / folder
    if result_directory.exists() and any(result_directory.iterdir()):
        if not args.overwrite:
            raise FileExistsError(f"Relatorios existentes em {result_directory}. Use outro --output-dir ou --overwrite.")
        warnings.warn(f"Sobrescrevendo relatorios em {result_directory}.")

    validate_required_columns(
        original_split
    )

    # Cópia sem os metadados, utilizada apenas na inferência.
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
        output_dir=str(
            temporary_output
        ),
        per_device_eval_batch_size=(
            args.eval_batch_size
        ),
        report_to="none",
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        remove_unused_columns=True,
    )

    trainer = Trainer(
        model=model,
        args=training_arguments,
        data_collator=data_collator,
        processing_class=tokenizer,
    )

    # A inferência ainda ocorre por janela porque o modelo aceita no
    # máximo 512 tokens.
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
        document_details,
        consolidation_statistics,
    ) = consolidate_predictions_by_document(
        original_dataset=original_split,
        raw_predictions=raw_predictions,
        label_ids=(
            prediction_output.label_ids
        ),
        tokenizer=tokenizer,
    )

    detailed_report = classification_report(
        label_sequences,
        prediction_sequences,
        output_dict=True,
        zero_division=0,
    )

    for row in entity_table(detailed_report):
        detailed_report[row["entity"]] = {key: value for key, value in row.items() if key != "entity"}
    window_loss = prediction_output.metrics.get("test_loss")
    if window_loss is None or not np.isfinite(window_loss):
        window_loss = None
        warnings.warn("Perda por janela indisponivel; registrada como null.")
    else:
        window_loss = float(window_loss)

    entity_support = count_entity_support(
        detailed_report
    )

    summary_metrics = {
        "model": str(
            args.model_dir
        ),
        "split": args.split,
        "evaluation_scope": (
            "document_consolidated"
        ),
        "documents": (
            consolidation_statistics[
                "documents"
            ]
        ),
        "windows": (
            consolidation_statistics[
                "windows"
            ]
        ),
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

        # A loss continua sendo calculada por janela pelo Trainer.
        "window_loss": window_loss,
        "window_test_loss": window_loss,
        "loss_scope": "window",
        "dataset": str(args.dataset_dir.resolve()),
        "model_path": str(args.model_dir.resolve()),
        "train_subset": subset,
        "subset": subset if subset else "all",
        "evaluated_tokens": consolidation_statistics["evaluated_tokens"],
        "library_versions": library_versions(),
        "seqeval_mode": "default (non-strict), zero_division=0; no BIO repair",
        "checkpoint_evaluation_only": True,
        "training_performed": False,
        "macro_avg": detailed_report["macro avg"],
        "weighted_avg": detailed_report["weighted avg"],

        "entity_support": (
            entity_support
        ),

        "consolidation": (
            consolidation_statistics
        ),
    }

    error_examples = (
        collect_document_error_examples(
            document_details=(
                document_details
            ),
            maximum_examples=(
                args.maximum_error_examples
            ),
            maximum_errors_per_document=(
                args.maximum_errors_per_document
            ),
        )
    )

    save_evaluation_tables(result_directory, label_sequences, prediction_sequences, detailed_report)

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

    save_json(
        consolidation_statistics,
        result_directory
        / "consolidation_statistics.json",
    )

    print(
        "\nAvaliação consolidada concluída!"
    )

    print(
        json.dumps(
            convert_numpy_types(
                summary_metrics
            ),
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