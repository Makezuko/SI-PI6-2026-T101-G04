"""
Data augmentation para o dataset Dataturks de currículos anotados para NER.

Estratégia utilizada:
1. Carregar o dataset já limpo por src/data/validate.py.
2. Separar currículos originais em treino, validação e teste.
3. Aplicar data augmentation SOMENTE ao conjunto de treino.
4. Substituir entidades por valores da mesma classe:
   - nome por nome;
   - empresa por empresa;
   - cargo por cargo;
   - bloco de skills por outro bloco de skills;
   - entre outras classes.
5. Reconstruir o texto e recalcular todos os offsets.
6. Validar os offsets antes de salvar.

Por que o augmentation é aplicado somente no treino?
-----------------------------------------------------
Se uma versão aumentada de um currículo aparecer no treino e o currículo
original aparecer no teste, teremos vazamento de dados. Nesse caso, o modelo
seria avaliado com um texto muito parecido com algo que já viu durante o
treinamento, produzindo métricas artificialmente altas.

Como executar, a partir da raiz do projeto:

python -m src.augmentation.augment \
    --input data/processed/dataturks_limpo.json \
    --output-dir data/processed/splits \
    --copies-per-resume 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# BANCO DE VALORES SINTÉTICOS
# ---------------------------------------------------------------------------
#
# Cada chave corresponde a um rótulo presente no dataset Dataturks.
#
# O rótulo é normalizado para letras minúsculas somente durante a consulta.
# O rótulo original da anotação é preservado no arquivo gerado.
#
# Nomes, e-mails e localizações são fictícios para não multiplicar dados
# potencialmente pessoais existentes no dataset original.
#
# O Dataturks normalmente anota a seção completa de Skills como uma entidade.
# Portanto, os exemplos de Skills abaixo também representam blocos completos.

SYNTHETIC_VALUES: dict[str, list[str]] = {
    "name": [
        "Alex Morgan",
        "Jordan Lee",
        "Taylor Brooks",
        "Casey Parker",
        "Morgan Reed",
        "Jamie Collins",
        "Cameron Hayes",
        "Avery Bennett",
    ],
    "email address": [
        "alex.morgan@example.com",
        "jordan.lee@example.com",
        "taylor.brooks@example.com",
        "casey.parker@example.com",
    ],
    "companies worked at": [
        "Northstar Technologies",
        "BluePeak Systems",
        "Vertex Labs",
        "Greenfield Analytics",
        "CloudBridge Solutions",
        "NovaWorks",
    ],
    "college name": [
        "North Valley University",
        "Central Institute of Technology",
        "Westbridge College",
        "Lakeside University",
    ],
    "location": [
        "Austin, TX",
        "Seattle, WA",
        "Boston, MA",
        "Denver, CO",
        "Chicago, IL",
        "Portland, OR",
    ],
    "designation": [
        "Software Engineer",
        "Frontend Developer",
        "Backend Developer",
        "Data Analyst",
        "Machine Learning Engineer",
        "Project Coordinator",
        "Full Stack Developer",
        "Systems Analyst",
    ],
    "degree": [
        "Bachelor of Science",
        "Bachelor of Engineering",
        "Master of Science",
        "Bachelor of Technology",
    ],
    "graduation year": [
        "2017",
        "2018",
        "2019",
        "2020",
        "2021",
        "2022",
    ],
    "years of experience": [
        "1 year",
        "2 years",
        "3 years",
        "4 years",
        "5 years",
        "6 years",
    ],
    "skills": [
        "JavaScript, TypeScript, React, Next.js, HTML, CSS",
        "Python, pandas, scikit-learn, NLP, Machine Learning",
        "Java, Spring Boot, REST APIs, SQL, Git",
        "FastAPI, PostgreSQL, Docker, AWS, CI/CD",
        "Power Apps, Power Automate, SharePoint, Data Analysis",
    ],
}


# Apenas esses rótulos poderão ser substituídos.
DEFAULT_AUGMENTABLE_LABELS = frozenset(SYNTHETIC_VALUES)


def normalize_label(label: str) -> str:
    """
    Normaliza o nome do rótulo para consultar o banco de valores.

    Exemplo:
        "Companies   Worked At" -> "companies worked at"

    Essa função não altera o label salvo no dataset.
    """
    return " ".join(label.strip().lower().split())


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """
    Carrega o arquivo JSON produzido pela etapa de validação.

    Formato esperado:

    [
        {
            "content": "texto completo do currículo",
            "entidades": [
                {
                    "start": 0,
                    "end": 10,
                    "label": "Name"
                }
            ]
        }
    ]

    O campo end é exclusivo:
        content[start:end]
    """
    with path.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    if not isinstance(dataset, list):
        raise ValueError(
            "O arquivo de entrada deve conter uma lista JSON de currículos."
        )

    return dataset


def save_json(data: Any, path: Path) -> None:
    """
    Salva um objeto em JSON usando UTF-8.

    A pasta de saída é criada automaticamente caso não exista.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def validate_resume(resume: dict[str, Any]) -> list[str]:
    """
    Valida a estrutura e os offsets de um currículo.

    A função verifica:

    - existência do texto;
    - existência da lista de entidades;
    - offsets inteiros;
    - start menor que end;
    - end dentro do tamanho do texto;
    - ausência de entidades vazias;
    - ausência de sobreposição entre entidades.

    Retorna uma lista de erros. Uma lista vazia significa que o currículo
    passou em todas as validações.
    """
    errors: list[str] = []

    content = resume.get("content")
    entities = resume.get("entidades")

    if not isinstance(content, str):
        return ["campo 'content' ausente ou não textual"]

    if not isinstance(entities, list):
        return ["campo 'entidades' ausente ou não é uma lista"]

    # Ordenar as entidades permite verificar sobreposições.
    sorted_entities = sorted(
        entities,
        key=lambda entity: entity.get("start", -1),
    )

    previous_end = 0

    for entity_index, entity in enumerate(sorted_entities):
        start = entity.get("start")
        end = entity.get("end")
        label = entity.get("label")

        if not isinstance(start, int) or not isinstance(end, int):
            errors.append(
                f"entidade {entity_index}: offsets não inteiros"
            )
            continue

        if not isinstance(label, str) or not label.strip():
            errors.append(
                f"entidade {entity_index}: label ausente ou inválido"
            )

        if start < 0 or end <= start or end > len(content):
            errors.append(
                f"entidade {entity_index}: intervalo inválido "
                f"[{start}, {end})"
            )
            continue

        if start < previous_end:
            errors.append(
                f"entidade {entity_index}: sobreposição detectada"
            )

        # O texto apontado pelo offset não pode ser vazio.
        entity_text = content[start:end]

        if not entity_text.strip():
            errors.append(
                f"entidade {entity_index}: trecho anotado vazio"
            )

        previous_end = max(previous_end, end)

    return errors


def validate_dataset(
    dataset: Iterable[dict[str, Any]],
    dataset_name: str,
) -> None:
    """
    Valida todos os currículos de um conjunto.

    Caso algum problema seja encontrado, o pipeline é interrompido para
    impedir que dados com offsets incorretos sejam salvos.
    """
    all_errors: list[str] = []

    for resume_index, resume in enumerate(dataset):
        resume_errors = validate_resume(resume)

        for error in resume_errors:
            all_errors.append(
                f"{dataset_name}[{resume_index}]: {error}"
            )

    if all_errors:
        # Exibe no máximo os primeiros 20 erros para não poluir o terminal.
        error_preview = "\n".join(all_errors[:20])

        raise ValueError(
            f"Falha na validação de {dataset_name}: "
            f"{len(all_errors)} erro(s).\n"
            f"{error_preview}"
        )


def content_hash(content: str) -> str:
    """
    Gera um identificador do texto para verificar duplicidades.

    O hash permite comparar currículos sem precisar armazenar novamente
    seu texto completo.
    """
    normalized_content = " ".join(content.lower().split())

    return hashlib.sha256(
        normalized_content.encode("utf-8")
    ).hexdigest()


def split_originals(
    dataset: list[dict[str, Any]],
    train_ratio: float,
    validation_ratio: float,
    seed: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Divide os currículos originais em treino, validação e teste.

    O split acontece ANTES do augmentation.

    Com os valores padrão:

    - 70% para treino;
    - 15% para validação;
    - 15% para teste.

    A semente torna a separação reproduzível.
    """
    if train_ratio <= 0:
        raise ValueError("A proporção de treino deve ser maior que zero.")

    if validation_ratio < 0:
        raise ValueError(
            "A proporção de validação não pode ser negativa."
        )

    if train_ratio + validation_ratio >= 1:
        raise ValueError(
            "Treino + validação deve ser menor que 1 para sobrar teste."
        )

    indices = list(range(len(dataset)))

    # O Random local evita interferir em outras partes do programa.
    random.Random(seed).shuffle(indices)

    train_end = int(len(indices) * train_ratio)

    validation_end = train_end + int(
        len(indices) * validation_ratio
    )

    train = [
        dataset[index]
        for index in indices[:train_end]
    ]

    validation = [
        dataset[index]
        for index in indices[train_end:validation_end]
    ]

    test = [
        dataset[index]
        for index in indices[validation_end:]
    ]

    return train, validation, test


def build_value_bank(
    train_dataset: Iterable[dict[str, Any]],
) -> dict[str, list[str]]:
    """
    Cria um banco de valores para cada classe de entidade.

    O banco é construído usando SOMENTE o conjunto de treino.

    Para nome, e-mail e localização são utilizados apenas valores sintéticos,
    evitando multiplicar informações pessoais do dataset original.

    Para cargos, empresas, formação e skills, os valores encontrados no treino
    complementam os valores sintéticos definidos no início do arquivo.
    """
    value_bank: dict[str, set[str]] = {
        label: set(values)
        for label, values in SYNTHETIC_VALUES.items()
    }

    privacy_labels = {
        "name",
        "email address",
        "location",
    }

    for resume in train_dataset:
        content = resume["content"]

        for entity in resume["entidades"]:
            normalized_label = normalize_label(entity["label"])

            if normalized_label not in DEFAULT_AUGMENTABLE_LABELS:
                continue

            # Entidades potencialmente pessoais não são copiadas do dataset.
            if normalized_label in privacy_labels:
                continue

            entity_value = content[
                entity["start"]:entity["end"]
            ].strip()

            if entity_value:
                value_bank.setdefault(
                    normalized_label,
                    set(),
                ).add(entity_value)

    # Converte os conjuntos para listas ordenadas.
    # A ordenação ajuda na reprodução do experimento.
    return {
        label: sorted(values)
        for label, values in value_bank.items()
    }


def choose_replacement(
    original_value: str,
    candidates: list[str],
    rng: random.Random,
) -> str | None:
    """
    Escolhe um valor diferente do valor original.

    Se o banco não tiver nenhuma alternativa, retorna None.
    """
    alternatives = [
        candidate
        for candidate in candidates
        if candidate.casefold() != original_value.casefold()
    ]

    if not alternatives:
        return None

    return rng.choice(alternatives)


def augment_resume(
    resume: dict[str, Any],
    value_bank: dict[str, list[str]],
    rng: random.Random,
    replacement_probability: float = 0.35,
    max_replacements: int = 6,
) -> tuple[dict[str, Any], int]:
    """
    Produz uma versão aumentada de um currículo.

    A função reconstrói o texto da esquerda para a direita.

    Essa estratégia é mais segura do que usar str.replace(), pois:

    - altera somente o trecho que está anotado;
    - não modifica ocorrências iguais em outras partes do texto;
    - recalcula os offsets no momento em que o novo texto é construído;
    - suporta substituições maiores ou menores que o texto original.

    Retorna:

    - o currículo aumentado;
    - a quantidade de entidades substituídas.
    """
    content = resume["content"]

    entities = sorted(
        resume["entidades"],
        key=lambda entity: entity["start"],
    )

    text_pieces: list[str] = []
    new_entities: list[dict[str, Any]] = []

    # Cursor aponta para a posição já processada no texto original.
    cursor = 0

    # Quantidade de caracteres já adicionados ao texto novo.
    output_length = 0

    replacements = 0

    for entity in entities:
        # Copia o texto não anotado que aparece antes da entidade.
        prefix = content[cursor:entity["start"]]

        text_pieces.append(prefix)
        output_length += len(prefix)

        original_value = content[
            entity["start"]:entity["end"]
        ]

        new_value = original_value

        normalized_label = normalize_label(entity["label"])

        should_replace = (
            replacements < max_replacements
            and normalized_label in value_bank
            and rng.random() < replacement_probability
        )

        if should_replace:
            replacement = choose_replacement(
                original_value=original_value.strip(),
                candidates=value_bank[normalized_label],
                rng=rng,
            )

            if replacement is not None:
                # Preserva espaços que estejam dentro das bordas anotadas.
                left_space_length = (
                    len(original_value)
                    - len(original_value.lstrip())
                )

                left_space = original_value[:left_space_length]

                right_space_start = len(original_value.rstrip())
                right_space = original_value[right_space_start:]

                new_value = (
                    f"{left_space}{replacement}{right_space}"
                )

                replacements += 1

        # O início da nova entidade corresponde ao tamanho atual da saída.
        new_start = output_length

        text_pieces.append(new_value)
        output_length += len(new_value)

        # O fim continua sendo exclusivo.
        new_end = output_length

        new_entities.append(
            {
                "start": new_start,
                "end": new_end,
                "label": entity["label"],
            }
        )

        # Avança o cursor usando os offsets do texto original.
        cursor = entity["end"]

    # Copia o restante do currículo após a última entidade.
    text_pieces.append(content[cursor:])

    augmented_resume = {
        "content": "".join(text_pieces),
        "entidades": new_entities,
    }

    return augmented_resume, replacements


def augment_training_set(
    train_dataset: list[dict[str, Any]],
    copies_per_resume: int,
    seed: int,
    replacement_probability: float,
    max_replacements: int,
) -> tuple[list[dict[str, Any]], Counter]:
    """
    Aplica augmentation somente ao conjunto de treino.

    O resultado contém:

    - todos os currículos originais de treino;
    - as versões aumentadas que receberam pelo menos uma alteração.
    """
    if copies_per_resume < 0:
        raise ValueError(
            "copies_per_resume não pode ser negativo."
        )

    rng = random.Random(seed)

    value_bank = build_value_bank(train_dataset)

    # Mantemos os exemplos originais junto com os aumentados.
    augmented_train = list(train_dataset)

    statistics = Counter()

    for source_index, resume in enumerate(train_dataset):
        for copy_index in range(copies_per_resume):
            synthetic_resume, replacements = augment_resume(
                resume=resume,
                value_bank=value_bank,
                rng=rng,
                replacement_probability=replacement_probability,
                max_replacements=max_replacements,
            )

            # Uma cópia sem alterações não acrescenta informação.
            if (
                replacements == 0
                or synthetic_resume["content"] == resume["content"]
            ):
                statistics[
                    "copies_skipped_without_change"
                ] += 1

                continue

            # Metadados ajudam a rastrear como o exemplo foi criado.
            synthetic_resume["metadata"] = {
                "is_augmented": True,
                "source_train_index": source_index,
                "augmentation_copy": copy_index + 1,
                "replacements": replacements,
            }

            augmented_train.append(synthetic_resume)

            statistics["synthetic_resumes_created"] += 1
            statistics["entities_replaced"] += replacements

    statistics["original_train_resumes"] = len(train_dataset)
    statistics["final_train_resumes"] = len(augmented_train)

    return augmented_train, statistics


def assert_no_split_leakage(
    train_original: list[dict[str, Any]],
    validation: list[dict[str, Any]],
    test: list[dict[str, Any]],
) -> None:
    """
    Verifica se um mesmo currículo original aparece em mais de um split.
    """
    train_hashes = {
        content_hash(resume["content"])
        for resume in train_original
    }

    validation_hashes = {
        content_hash(resume["content"])
        for resume in validation
    }

    test_hashes = {
        content_hash(resume["content"])
        for resume in test
    }

    collisions = (
        (train_hashes & validation_hashes)
        | (train_hashes & test_hashes)
        | (validation_hashes & test_hashes)
    )

    if collisions:
        raise ValueError(
            f"Vazamento detectado: {len(collisions)} currículo(s) "
            "duplicado(s) entre os splits."
        )


def label_distribution(
    dataset: Iterable[dict[str, Any]],
) -> dict[str, int]:
    """
    Conta quantas entidades existem para cada rótulo.
    """
    counts: Counter = Counter()

    for resume in dataset:
        counts.update(
            entity["label"]
            for entity in resume["entidades"]
        )

    return dict(sorted(counts.items()))


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    """
    Executa o pipeline completo:

    1. carregamento;
    2. validação inicial;
    3. split dos currículos originais;
    4. verificação de vazamento;
    5. augmentation do treino;
    6. validação final;
    7. salvamento dos arquivos;
    8. criação do manifesto.
    """
    dataset = load_dataset(args.input)

    validate_dataset(
        dataset,
        dataset_name="dataset_original",
    )

    train_original, validation, test = split_originals(
        dataset=dataset,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )

    assert_no_split_leakage(
        train_original=train_original,
        validation=validation,
        test=test,
    )

    train_augmented, augmentation_statistics = (
        augment_training_set(
            train_dataset=train_original,
            copies_per_resume=args.copies_per_resume,
            seed=args.seed,
            replacement_probability=args.replacement_probability,
            max_replacements=args.max_replacements,
        )
    )

    # Validação final de todos os conjuntos.
    validate_dataset(
        train_augmented,
        dataset_name="train_augmented",
    )

    validate_dataset(
        validation,
        dataset_name="validation",
    )

    validate_dataset(
        test,
        dataset_name="test",
    )

    output_dir: Path = args.output_dir

    save_json(
        train_augmented,
        output_dir / "train.json",
    )

    save_json(
        validation,
        output_dir / "validation.json",
    )

    save_json(
        test,
        output_dir / "test.json",
    )

    # O manifesto registra as condições do experimento.
    manifest = {
        "seed": args.seed,
        "input_resumes": len(dataset),
        "split": {
            "train_original": len(train_original),
            "train_after_augmentation": len(train_augmented),
            "validation": len(validation),
            "test": len(test),
        },
        "configuration": {
            "train_ratio": args.train_ratio,
            "validation_ratio": args.validation_ratio,
            "test_ratio": round(
                1
                - args.train_ratio
                - args.validation_ratio,
                2,
            ),
            "copies_per_resume": args.copies_per_resume,
            "replacement_probability": (
                args.replacement_probability
            ),
            "max_replacements": args.max_replacements,
        },
        "augmentation": dict(augmentation_statistics),
        "label_distribution": {
            "train": label_distribution(train_augmented),
            "validation": label_distribution(validation),
            "test": label_distribution(test),
        },
        "validation": {
            "all_offsets_valid": True,
            "split_leakage_detected": False,
            "augmentation_applied_to": "train_only",
        },
    }

    save_json(
        manifest,
        output_dir / "manifest.json",
    )

    return manifest


def parse_args() -> argparse.Namespace:
    """
    Configura os argumentos aceitos pelo script.
    """
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "data/processed/dataturks_limpo.json"
        ),
        help="Arquivo JSON criado por src.data.validate.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/processed/splits"
        ),
        help="Pasta que receberá os arquivos finais.",
    )

    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.70,
    )

    parser.add_argument(
        "--validation-ratio",
        type=float,
        default=0.15,
    )

    parser.add_argument(
        "--copies-per-resume",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--replacement-probability",
        type=float,
        default=0.35,
    )

    parser.add_argument(
        "--max-replacements",
        type=int,
        default=6,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    return parser.parse_args()


if __name__ == "__main__":
    pipeline_result = run_pipeline(parse_args())

    print("\nData augmentation concluído com sucesso!\n")

    print(
        json.dumps(
            pipeline_result,
            ensure_ascii=False,
            indent=2,
        )
    )