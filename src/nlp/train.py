"""
Fine-tuning do DistilBERT para reconhecimento de entidades em currículos.

Este script executa dois experimentos:

1. baseline:
   utiliza somente os currículos originais;

2. augmented:
   utiliza currículos originais e sintéticos.

A validação é sempre realizada com currículos originais.

Execução dos dois experimentos:

    python -m src.nlp.train --experiment both

Somente baseline:

    python -m src.nlp.train --experiment baseline

Somente augmentation:

    python -m src.nlp.train --experiment augmented
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from datasets import Dataset, DatasetDict, load_from_disk
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
    EarlyStoppingCallback,
    EvalPrediction,
    Trainer,
    TrainingArguments,
    set_seed,
)

from src.nlp.labels import (
    BIO_LABELS,
    ID2LABEL,
    LABEL2ID,
)


DEFAULT_MODEL_NAME = "distilbert-base-cased"

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
    Salva configurações e resultados em JSON.
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


def convert_predictions_to_labels(
    predictions: np.ndarray,
    label_ids: np.ndarray,
) -> tuple[list[list[str]], list[list[str]]]:
    """
    Converte as previsões numéricas e os rótulos verdadeiros para BIO.

    Tokens com rótulo -100 são ignorados. Esses tokens correspondem a:

    - [CLS];
    - [SEP];
    - padding;
    - parte repetida entre janelas.
    """
    predicted_ids = np.argmax(
        predictions,
        axis=-1,
    )

    true_predictions = []
    true_labels = []

    for predicted_sequence, label_sequence in zip(
        predicted_ids,
        label_ids,
    ):
        sequence_predictions = []
        sequence_labels = []

        for predicted_id, label_id in zip(
            predicted_sequence,
            label_sequence,
        ):
            if label_id == -100:
                continue

            sequence_predictions.append(
                ID2LABEL[int(predicted_id)]
            )

            sequence_labels.append(
                ID2LABEL[int(label_id)]
            )

        true_predictions.append(
            sequence_predictions
        )

        true_labels.append(
            sequence_labels
        )

    return true_predictions, true_labels


def compute_metrics(
    evaluation_prediction: EvalPrediction,
) -> dict[str, float]:
    """
    Calcula as métricas de NER com a biblioteca seqeval.

    Métricas principais:

    precision:
        Entre as entidades previstas, quantas estavam corretas.

    recall:
        Entre as entidades existentes, quantas foram encontradas.

    F1:
        Média harmônica entre precisão e recall.

    accuracy:
        Percentual de tokens classificados corretamente.

    Para este projeto, F1, precisão e recall são mais importantes do que
    acurácia, pois a maior parte dos tokens pertence à classe O.
    """
    predictions = evaluation_prediction.predictions

    # Alguns modelos podem retornar uma tupla.
    if isinstance(predictions, tuple):
        predictions = predictions[0]

    true_predictions, true_labels = (
        convert_predictions_to_labels(
            predictions=predictions,
            label_ids=evaluation_prediction.label_ids,
        )
    )

    metrics = {
        "precision": precision_score(
            true_labels,
            true_predictions,
            zero_division=0,
        ),
        "recall": recall_score(
            true_labels,
            true_predictions,
            zero_division=0,
        ),
        "f1": f1_score(
            true_labels,
            true_predictions,
            zero_division=0,
        ),
        "accuracy": accuracy_score(
            true_labels,
            true_predictions,
        ),
    }

    # Também registra o F1 de cada entidade.
    report = classification_report(
        true_labels,
        true_predictions,
        output_dict=True,
        zero_division=0,
    )

    ignored_report_keys = {
        "micro avg",
        "macro avg",
        "weighted avg",
    }

    for entity_name, entity_metrics in report.items():
        if entity_name in ignored_report_keys:
            continue

        if not isinstance(entity_metrics, dict):
            continue

        normalized_name = (
            entity_name
            .upper()
            .replace(" ", "_")
        )

        metrics[
            f"f1_{normalized_name}"
        ] = float(
            entity_metrics.get(
                "f1-score",
                0.0,
            )
        )

    return metrics


def remove_auxiliary_columns(
    dataset: Dataset,
) -> Dataset:
    """
    Remove campos usados para auditoria, mas que não podem ser enviados
    diretamente ao DistilBERT.

    Permanecem apenas:

    - input_ids;
    - attention_mask;
    - labels;
    - token_type_ids, caso exista.
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


def prepare_experiment_dataset(
    dataset: DatasetDict,
    experiment_name: str,
) -> DatasetDict:
    """
    Seleciona os dados adequados para cada experimento.

    baseline:
        remove todos os chunks sintéticos.

    augmented:
        mantém originais e sintéticos.

    Validação e teste permanecem iguais nos dois experimentos.
    """
    train_dataset = dataset["train"]

    if experiment_name == "baseline":
        if "is_augmented" not in train_dataset.column_names:
            raise ValueError(
                "A coluna is_augmented não foi encontrada. "
                "Ela é necessária para criar o baseline."
            )

        train_dataset = train_dataset.filter(
            lambda example: not example[
                "is_augmented"
            ],
            desc="Selecionando exemplos originais",
        )

    elif experiment_name == "augmented":
        # Mantém todo o conjunto de treino.
        pass

    else:
        raise ValueError(
            f"Experimento desconhecido: {experiment_name}"
        )

    prepared_dataset = DatasetDict(
        {
            "train": remove_auxiliary_columns(
                train_dataset
            ),
            "validation": remove_auxiliary_columns(
                dataset["validation"]
            ),
            "test": remove_auxiliary_columns(
                dataset["test"]
            ),
        }
    )

    return prepared_dataset


def create_model(
    model_name: str,
):
    """
    Carrega o DistilBERT e cria uma nova camada de classificação.

    A camada final possui uma saída para cada rótulo BIO.
    """
    return AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(BIO_LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )


def run_experiment(
    experiment_name: str,
    dataset: DatasetDict,
    tokenizer,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """
    Executa um experimento completo de fine-tuning.
    """
    print(
        "\n"
        + "=" * 70
    )

    print(
        f"INICIANDO EXPERIMENTO: "
        f"{experiment_name.upper()}"
    )

    print(
        "=" * 70
    )

    experiment_dataset = (
        prepare_experiment_dataset(
            dataset=dataset,
            experiment_name=experiment_name,
        )
    )

    output_directory = (
        args.output_dir
        / experiment_name
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Chunks de treino: "
        f"{len(experiment_dataset['train'])}"
    )

    print(
        f"Chunks de validação: "
        f"{len(experiment_dataset['validation'])}"
    )

    print(
        f"Chunks de teste: "
        f"{len(experiment_dataset['test'])}"
    )

    model = create_model(
        args.model_name
    )

    data_collator = (
        DataCollatorForTokenClassification(
            tokenizer=tokenizer,
            padding=True,
            label_pad_token_id=-100,
            return_tensors="pt",
        )
    )

    has_cuda = torch.cuda.is_available()

    if has_cuda:
        print(
            "Dispositivo detectado: GPU CUDA"
        )
    else:
        print(
            "Dispositivo detectado: CPU"
        )

        print(
            "O treinamento em CPU pode demorar "
            "consideravelmente."
        )

    training_arguments = TrainingArguments(
        output_dir=str(output_directory),

        # Quantidade de vezes que o modelo verá o conjunto de treino.
        num_train_epochs=args.epochs,

        # Taxa de aprendizado pequena para não destruir rapidamente
        # os conhecimentos adquiridos no pré-treinamento.
        learning_rate=args.learning_rate,

        # Batch pequeno para reduzir o consumo de memória.
        per_device_train_batch_size=(
            args.train_batch_size
        ),

        per_device_eval_batch_size=(
            args.eval_batch_size
        ),

        # Acumula gradientes de vários batches antes da atualização.
        gradient_accumulation_steps=(
            args.gradient_accumulation_steps
        ),

        weight_decay=args.weight_decay,

        warmup_ratio=args.warmup_ratio,

        # Avalia e salva ao final de cada época.
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="steps",
        logging_steps=args.logging_steps,

        # Ao terminar, recupera a época com maior F1.
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,

        save_total_limit=2,

        # Reprodutibilidade.
        seed=args.seed,
        data_seed=args.seed,

        # Não enviar métricas para serviços externos.
        report_to="none",

        # Compatibilidade com Windows.
        dataloader_num_workers=0,

        # Mixed precision somente quando houver CUDA.
        fp16=has_cuda,

        remove_unused_columns=True,
    )

    trainer = Trainer(
        model=model,
        args=training_arguments,
        train_dataset=experiment_dataset[
            "train"
        ],
        eval_dataset=experiment_dataset[
            "validation"
        ],
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        processing_class=tokenizer,
        callbacks=[
            EarlyStoppingCallback(
                early_stopping_patience=2
            )
        ],
    )

    train_result = trainer.train()

    trainer.save_model(
        str(output_directory / "best_model")
    )

    tokenizer.save_pretrained(
        str(output_directory / "best_model")
    )

    train_metrics = {
        key: float(value)
        if isinstance(
            value,
            (int, float, np.number),
        )
        else value
        for key, value
        in train_result.metrics.items()
    }

    validation_metrics = trainer.evaluate(
        eval_dataset=experiment_dataset[
            "validation"
        ],
        metric_key_prefix="validation",
    )

    test_metrics = trainer.evaluate(
        eval_dataset=experiment_dataset[
            "test"
        ],
        metric_key_prefix="test",
    )

    results = {
        "experiment": experiment_name,
        "model_name": args.model_name,
        "device": (
            "cuda"
            if has_cuda
            else "cpu"
        ),
        "dataset_sizes": {
            "train_chunks": len(
                experiment_dataset["train"]
            ),
            "validation_chunks": len(
                experiment_dataset["validation"]
            ),
            "test_chunks": len(
                experiment_dataset["test"]
            ),
        },
        "hyperparameters": {
            "epochs": args.epochs,
            "learning_rate": (
                args.learning_rate
            ),
            "train_batch_size": (
                args.train_batch_size
            ),
            "eval_batch_size": (
                args.eval_batch_size
            ),
            "gradient_accumulation_steps": (
                args.gradient_accumulation_steps
            ),
            "weight_decay": args.weight_decay,
            "warmup_ratio": args.warmup_ratio,
            "seed": args.seed,
        },
        "train_metrics": train_metrics,
        "validation_metrics": {
            key: float(value)
            if isinstance(
                value,
                (int, float, np.number),
            )
            else value
            for key, value
            in validation_metrics.items()
        },
        "test_metrics": {
            key: float(value)
            if isinstance(
                value,
                (int, float, np.number),
            )
            else value
            for key, value
            in test_metrics.items()
        },
    }

    save_json(
        results,
        output_directory / "results.json",
    )

    print(
        f"\nExperimento {experiment_name} "
        "concluído."
    )

    print(
        f"Modelo salvo em: "
        f"{output_directory / 'best_model'}"
    )

    return results


def create_comparison(
    experiment_results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Cria uma comparação resumida entre baseline e augmentation.
    """
    comparison = []

    for result in experiment_results:
        test_metrics = result[
            "test_metrics"
        ]

        comparison.append(
            {
                "experiment": result[
                    "experiment"
                ],
                "train_chunks": result[
                    "dataset_sizes"
                ]["train_chunks"],
                "test_precision": test_metrics.get(
                    "test_precision"
                ),
                "test_recall": test_metrics.get(
                    "test_recall"
                ),
                "test_f1": test_metrics.get(
                    "test_f1"
                ),
                "test_accuracy": test_metrics.get(
                    "test_accuracy"
                ),
                "test_f1_SKILLS": test_metrics.get(
                    "test_f1_SKILLS"
                ),
                "test_f1_DESIGNATION": test_metrics.get(
                    "test_f1_DESIGNATION"
                ),
                "test_f1_COMPANIES_WORKED_AT": (
                    test_metrics.get(
                        "test_f1_COMPANIES_WORKED_AT"
                    )
                ),
                "test_f1_YEARS_OF_EXPERIENCE": (
                    test_metrics.get(
                        "test_f1_YEARS_OF_EXPERIENCE"
                    )
                ),
            }
        )

    save_json(
        comparison,
        output_path,
    )

    print(
        "\nComparação dos experimentos:"
    )

    print(
        json.dumps(
            comparison,
            ensure_ascii=False,
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    """
    Define os argumentos do treinamento.
    """
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path(
            "data/processed/huggingface_ner"
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "models/ner"
        ),
    )

    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
    )

    parser.add_argument(
        "--experiment",
        choices=[
            "baseline",
            "augmented",
            "both",
        ],
        default="both",
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-5,
    )

    parser.add_argument(
        "--train-batch-size",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--eval-batch-size",
        type=int,
        default=8,
    )

    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--weight-decay",
        type=float,
        default=0.01,
    )

    parser.add_argument(
        "--warmup-ratio",
        type=float,
        default=0.1,
    )

    parser.add_argument(
        "--logging-steps",
        type=int,
        default=25,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    return parser.parse_args()


def main() -> None:
    """
    Carrega os dados e executa os experimentos solicitados.
    """
    args = parse_args()

    set_seed(
        args.seed
    )

    if not args.dataset_dir.exists():
        raise FileNotFoundError(
            f"Dataset não encontrado: "
            f"{args.dataset_dir}. Execute primeiro "
            "python -m src.nlp.prepare_ner_dataset"
        )

    dataset = load_from_disk(
        str(args.dataset_dir)
    )

    required_splits = {
        "train",
        "validation",
        "test",
    }

    missing_splits = (
        required_splits
        - set(dataset.keys())
    )

    if missing_splits:
        raise ValueError(
            f"Splits ausentes: "
            f"{sorted(missing_splits)}"
        )

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name,
        use_fast=True,
    )

    experiments = (
        ["baseline", "augmented"]
        if args.experiment == "both"
        else [args.experiment]
    )

    all_results = []

    for experiment_name in experiments:
        result = run_experiment(
            experiment_name=experiment_name,
            dataset=dataset,
            tokenizer=tokenizer,
            args=args,
        )

        all_results.append(result)

        # Libera memória antes do próximo experimento.
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    create_comparison(
        experiment_results=all_results,
        output_path=(
            args.output_dir
            / "comparison.json"
        ),
    )


if __name__ == "__main__":
    main()