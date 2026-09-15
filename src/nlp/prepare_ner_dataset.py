"""
Prepara os currículos para o treinamento de um modelo Transformer de NER.

Este script realiza:

1. Carregamento dos arquivos train, validation e test.
2. Validação das entidades e dos offsets.
3. Tokenização com o tokenizer do modelo pré-treinado.
4. Alinhamento entre tokens, subwords e entidades.
5. Conversão dos rótulos para o padrão BIO.
6. Divisão de currículos longos em janelas com sobreposição.
7. Verificação de que nenhuma entidade desapareceu na tokenização.
8. Salvamento no formato DatasetDict da biblioteca Hugging Face.

Modelo-base escolhido:
    distilbert-base-cased

Os arquivos de entrada devem ter sido produzidos por:

    python -m src.augmentation.augment

Execução:

    python -m src.nlp.prepare_ner_dataset
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict
from transformers import AutoTokenizer
from transformers.tokenization_utils_base import (
    PreTrainedTokenizerBase,
)

from src.nlp.labels import (
    BIO_LABELS,
    ENTITY_LABELS,
    ID2LABEL,
    LABEL2ID,
    normalize_entity_label,
)


# Modelo pré-treinado escolhido para iniciar o NER.
DEFAULT_MODEL_NAME = "distilbert-base-cased"

# O DistilBERT aceita no máximo 512 tokens por sequência.
DEFAULT_MAX_LENGTH = 512

# Quantidade de tokens repetidos entre duas janelas consecutivas.
#
# A sobreposição reduz o risco de uma entidade localizada exatamente na
# divisão entre duas janelas perder parte de seu contexto.
DEFAULT_STRIDE = 128


def load_json(path: Path) -> list[dict[str, Any]]:
    """
    Carrega um arquivo JSON com currículos e entidades.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            f"O arquivo {path} deve conter uma lista JSON."
        )

    return data


def save_json(
    data: Any,
    path: Path,
) -> None:
    """
    Salva informações de configuração e estatísticas em JSON.
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
        )


def validate_document(
    document: dict[str, Any],
    document_index: int,
    split_name: str,
) -> None:
    """
    Valida um currículo antes da tokenização.

    Esta validação confirma:

    - existência do campo content;
    - existência da lista entidades;
    - presença de start, end e label;
    - offsets dentro do texto;
    - uso apenas dos rótulos conhecidos;
    - ausência de entidades sobrepostas.
    """
    content = document.get("content")
    entities = document.get("entidades")

    document_reference = (
        f"{split_name}[{document_index}]"
    )

    if not isinstance(content, str):
        raise ValueError(
            f"{document_reference}: content inválido."
        )

    if not isinstance(entities, list):
        raise ValueError(
            f"{document_reference}: entidades deve ser uma lista."
        )

    sorted_entities = sorted(
        entities,
        key=lambda entity: (
            entity.get("start", -1),
            entity.get("end", -1),
        ),
    )

    previous_end = 0

    for entity_index, entity in enumerate(
        sorted_entities
    ):
        start = entity.get("start")
        end = entity.get("end")
        label = entity.get("label")

        entity_reference = (
            f"{document_reference}.entidades"
            f"[{entity_index}]"
        )

        if not isinstance(start, int):
            raise ValueError(
                f"{entity_reference}: start inválido."
            )

        if not isinstance(end, int):
            raise ValueError(
                f"{entity_reference}: end inválido."
            )

        if start < 0 or end <= start:
            raise ValueError(
                f"{entity_reference}: intervalo inválido "
                f"[{start}, {end})."
            )

        if end > len(content):
            raise ValueError(
                f"{entity_reference}: end ultrapassa "
                "o tamanho do texto."
            )

        if label not in ENTITY_LABELS:
            raise ValueError(
                f"{entity_reference}: rótulo desconhecido "
                f"'{label}'."
            )

        if start < previous_end:
            raise ValueError(
                f"{entity_reference}: sobreposição detectada."
            )

        if not content[start:end].strip():
            raise ValueError(
                f"{entity_reference}: entidade vazia."
            )

        previous_end = end


def token_overlaps_entity(
    token_start: int,
    token_end: int,
    entity_start: int,
    entity_end: int,
) -> bool:
    """
    Verifica se um token e uma entidade compartilham caracteres.

    Tanto os offsets dos tokens quanto os das entidades usam fim exclusivo.
    """
    return (
        token_start < entity_end
        and token_end > entity_start
    )


def align_tokens_with_entities(
    offsets: list[tuple[int, int]],
    entities: list[dict[str, Any]],
) -> tuple[list[int], set[int]]:
    """
    Alinha cada token com as entidades anotadas no currículo.

    Parâmetros
    ----------
    offsets:
        Lista de posições de caracteres produzida pelo tokenizer.

        Exemplo:
            [(0, 0), (0, 4), (5, 11), (0, 0)]

        Os offsets (0, 0) normalmente representam tokens especiais,
        como [CLS] e [SEP].

    entities:
        Entidades originais do currículo.

    Retorno
    -------
    token_labels:
        Lista de IDs BIO alinhada com os tokens.

    found_entity_indices:
        Índices das entidades encontradas nessa janela.

    Regras
    ------
    - tokens especiais recebem -100;
    - tokens fora das entidades recebem O;
    - primeiro token de uma entidade recebe B;
    - tokens seguintes da mesma entidade recebem I.

    O valor -100 é ignorado pela função de perda do Transformers.
    """
    sorted_entities = sorted(
        entities,
        key=lambda entity: (
            entity["start"],
            entity["end"],
        ),
    )

    token_labels: list[int] = []
    found_entity_indices: set[int] = set()

    # Guarda qual era a entidade do token anterior.
    # Se a entidade mudar, o token atual recebe B.
    previous_entity_index = None

    for token_start, token_end in offsets:
        # Tokens especiais não representam caracteres do texto.
        if token_start == token_end:
            token_labels.append(-100)
            previous_entity_index = None
            continue

        current_entity_index = None

        # Como as entidades já estão ordenadas e não se sobrepõem,
        # no máximo uma entidade pode corresponder ao token.
        for entity_index, entity in enumerate(
            sorted_entities
        ):
            if token_overlaps_entity(
                token_start=token_start,
                token_end=token_end,
                entity_start=entity["start"],
                entity_end=entity["end"],
            ):
                current_entity_index = entity_index
                break

            # Se a entidade começa depois do token, não é necessário
            # verificar as entidades seguintes.
            if entity["start"] >= token_end:
                break

        # Token fora de qualquer entidade.
        if current_entity_index is None:
            token_labels.append(
                LABEL2ID["O"]
            )

            previous_entity_index = None
            continue

        entity = sorted_entities[
            current_entity_index
        ]

        normalized_label = normalize_entity_label(
            entity["label"]
        )

        # Se essa entidade é diferente da entidade do token anterior,
        # este é o começo da entidade dentro da janela.
        if (
            current_entity_index
            != previous_entity_index
        ):
            bio_label = (
                f"B-{normalized_label}"
            )

        else:
            bio_label = (
                f"I-{normalized_label}"
            )

        token_labels.append(
            LABEL2ID[bio_label]
        )

        found_entity_indices.add(
            current_entity_index
        )

        previous_entity_index = (
            current_entity_index
        )

    return token_labels, found_entity_indices


def prepare_document_chunks(
    document: dict[str, Any],
    document_index: int,
    split_name: str,
    tokenizer: PreTrainedTokenizerBase,
    max_length: int,
    stride: int,
) -> list[dict[str, Any]]:
    """
    Tokeniza um currículo completo e divide manualmente seus tokens em janelas.

    A divisão manual evita depender do comportamento de
    return_overflowing_tokens, que pode variar entre versões da biblioteca
    Transformers.

    Processo:
    1. Tokeniza o texto inteiro sem truncamento e sem tokens especiais.
    2. Mantém os offsets globais de cada token no currículo.
    3. Divide os tokens em janelas.
    4. Adiciona [CLS] e [SEP] em cada janela.
    5. Repete uma parte da janela anterior usando o stride.
    6. Alinha cada token com os rótulos BIO.
    7. Confirma que todas as entidades apareceram em alguma janela.
    """
    content = document["content"]

    entities = sorted(
        document["entidades"],
        key=lambda entity: (
            entity["start"],
            entity["end"],
        ),
    )

    # ---------------------------------------------------------------
    # TOKENIZAÇÃO COMPLETA
    # ---------------------------------------------------------------
    #
    # Não usamos truncation nem return_overflowing_tokens.
    # Dessa forma, recebemos todos os tokens e offsets globais do currículo.
    full_encoding = tokenizer(
        content,
        add_special_tokens=False,
        return_offsets_mapping=True,
        truncation=False,
        padding=False,
    )

    all_input_ids = full_encoding["input_ids"]
    all_offsets = full_encoding["offset_mapping"]

    if len(all_input_ids) != len(all_offsets):
        raise ValueError(
            f"{split_name}[{document_index}]: "
            "input_ids e offset_mapping possuem tamanhos diferentes."
        )

    if not all_input_ids:
        raise ValueError(
            f"{split_name}[{document_index}]: "
            "o tokenizer não produziu nenhum token."
        )

    # O DistilBERT adiciona dois tokens especiais:
    #
    # [CLS] no começo;
    # [SEP] no final.
    #
    # Essa quantidade é obtida do próprio tokenizer para que a função
    # continue funcionando caso o modelo seja trocado.
    number_of_special_tokens = (
        tokenizer.num_special_tokens_to_add(
            pair=False
        )
    )

    # Quantidade de tokens reais do currículo que cabem em cada janela.
    content_window_size = (
        max_length
        - number_of_special_tokens
    )

    if content_window_size <= 0:
        raise ValueError(
            "max_length é menor do que a quantidade "
            "de tokens especiais exigida pelo tokenizer."
        )

    if stride >= content_window_size:
        raise ValueError(
            "stride deve ser menor que a quantidade de "
            "tokens de conteúdo disponíveis em cada janela."
        )

    # Exemplo:
    #
    # content_window_size = 510
    # stride = 128
    #
    # A primeira janela usa os tokens 0 até 509.
    # A segunda começa em 382, repetindo 128 tokens.
    window_step = (
        content_window_size
        - stride
    )

    document_chunks = []

    entities_found_in_document: set[int] = set()

    window_start = 0
    chunk_index = 0

    while window_start < len(all_input_ids):
        window_end = min(
            window_start + content_window_size,
            len(all_input_ids),
        )

        window_input_ids = all_input_ids[
            window_start:window_end
        ]

        window_offsets_without_special = all_offsets[
            window_start:window_end
        ]

                # -----------------------------------------------------------
        # ADIÇÃO MANUAL DOS TOKENS ESPECIAIS
        # -----------------------------------------------------------
        #
        # O DistilBERT utiliza:
        # - [CLS] no início;
        # - [SEP] no final.
        #
        # A adição é feita manualmente porque algumas versões do tokenizer
        # rápido não permitem criar special_tokens_mask usando
        # prepare_for_model().

        cls_token_id = tokenizer.cls_token_id
        sep_token_id = tokenizer.sep_token_id

        if cls_token_id is None:
            raise ValueError(
                "O tokenizer não possui cls_token_id."
            )

        if sep_token_id is None:
            raise ValueError(
                "O tokenizer não possui sep_token_id."
            )

        prepared_input_ids = [
            cls_token_id,
            *window_input_ids,
            sep_token_id,
        ]

        prepared_attention_mask = [
            1
            for _ in prepared_input_ids
        ]

        # Tokens especiais não correspondem a caracteres do currículo.
        # Por isso recebem o offset (0, 0).
        window_offsets_with_special = [
            (0, 0),
            *window_offsets_without_special,
            (0, 0),
        ]

        prepared_window = {
            "input_ids": prepared_input_ids,
            "attention_mask": prepared_attention_mask,
        }

        if (
            len(prepared_input_ids)
            != len(window_offsets_with_special)
        ):
            raise ValueError(
                f"{split_name}[{document_index}], "
                f"janela {chunk_index}: quantidade de tokens "
                "diferente da quantidade de offsets."
            )

        # -----------------------------------------------------------
        # ALINHAMENTO BIO
        # -----------------------------------------------------------

        labels, found_entity_indices = (
            align_tokens_with_entities(
                offsets=window_offsets_with_special,
                entities=entities,
            )
        )

        entities_found_in_document.update(
            found_entity_indices
        )

        if (
            len(labels)
            != len(prepared_window["input_ids"])
        ):
            raise ValueError(
                f"{split_name}[{document_index}], "
                f"janela {chunk_index}: quantidade de labels "
                "diferente da quantidade de tokens."
            )

        chunk = {
            "input_ids": prepared_window[
                "input_ids"
            ],
            "attention_mask": prepared_window[
                "attention_mask"
            ],
            "labels": labels,
            "offset_mapping": [
                [start, end]
                for start, end
                in window_offsets_with_special
            ],
            "source_document_id": (
                f"{split_name}-{document_index}"
            ),
            "chunk_id": chunk_index,
            "is_augmented": bool(
                document.get(
                    "metadata",
                    {},
                ).get(
                    "is_augmented",
                    False,
                )
            ),
        }

        document_chunks.append(chunk)

        chunk_index += 1

        # A última janela chegou ao final do currículo.
        if window_end == len(all_input_ids):
            break

        window_start += window_step

    # Agora que sabemos o total, registramos a quantidade de janelas
    # em todos os chunks do currículo.
    number_of_chunks = len(document_chunks)

    for chunk in document_chunks:
        chunk["number_of_chunks"] = (
            number_of_chunks
        )

    # ---------------------------------------------------------------
    # VERIFICAÇÃO DE COBERTURA DAS ENTIDADES
    # ---------------------------------------------------------------

    expected_entity_indices = set(
        range(len(entities))
    )

    missing_entities = (
        expected_entity_indices
        - entities_found_in_document
    )

    if missing_entities:
        missing_details = []

        for entity_index in sorted(
            missing_entities
        ):
            entity = entities[entity_index]

            missing_details.append(
                {
                    "index": entity_index,
                    "label": entity["label"],
                    "start": entity["start"],
                    "end": entity["end"],
                    "text": content[
                        entity["start"]:
                        entity["end"]
                    ][:100],
                }
            )

        raise ValueError(
            f"{split_name}[{document_index}]: "
            "algumas entidades não foram encontradas "
            f"na tokenização: {missing_details}"
        )

    return document_chunks


def prepare_split(
    documents: list[dict[str, Any]],
    split_name: str,
    tokenizer: PreTrainedTokenizerBase,
    max_length: int,
    stride: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Prepara todos os currículos de um split.

    Retorna:
    - janelas tokenizadas;
    - estatísticas do split.
    """
    all_chunks: list[dict[str, Any]] = []

    entity_distribution: Counter = Counter()

    augmented_documents = 0
    documents_with_multiple_chunks = 0

    for document_index, document in enumerate(
        documents
    ):
        validate_document(
            document=document,
            document_index=document_index,
            split_name=split_name,
        )

        for entity in document["entidades"]:
            entity_distribution.update(
                [entity["label"]]
            )

        if document.get(
            "metadata",
            {},
        ).get(
            "is_augmented",
            False,
        ):
            augmented_documents += 1

        chunks = prepare_document_chunks(
            document=document,
            document_index=document_index,
            split_name=split_name,
            tokenizer=tokenizer,
            max_length=max_length,
            stride=stride,
        )

        if len(chunks) > 1:
            documents_with_multiple_chunks += 1

        all_chunks.extend(chunks)

        # Mostra o andamento sem imprimir uma linha para cada currículo.
        if (
            (document_index + 1) % 50 == 0
            or document_index + 1 == len(documents)
        ):
            print(
                f"{split_name}: "
                f"{document_index + 1}/"
                f"{len(documents)} currículos preparados"
            )

    statistics = {
        "documents": len(documents),
        "augmented_documents": augmented_documents,
        "chunks": len(all_chunks),
        "documents_with_multiple_chunks": (
            documents_with_multiple_chunks
        ),
        "entity_distribution": dict(
            sorted(entity_distribution.items())
        ),
    }

    return all_chunks, statistics


def validate_tokenized_chunks(
    chunks: list[dict[str, Any]],
    split_name: str,
    max_length: int,
) -> None:
    """
    Verifica se todas as janelas tokenizadas possuem estrutura consistente.
    """
    valid_label_ids = set(
        ID2LABEL.keys()
    )

    valid_label_ids.add(-100)

    for chunk_index, chunk in enumerate(
        chunks
    ):
        input_ids = chunk["input_ids"]
        attention_mask = chunk["attention_mask"]
        labels = chunk["labels"]
        offsets = chunk["offset_mapping"]

        lengths = {
            len(input_ids),
            len(attention_mask),
            len(labels),
            len(offsets),
        }

        if len(lengths) != 1:
            raise ValueError(
                f"{split_name}, chunk {chunk_index}: "
                "input_ids, attention_mask, labels e offsets "
                "possuem tamanhos diferentes."
            )

        if len(input_ids) > max_length:
            raise ValueError(
                f"{split_name}, chunk {chunk_index}: "
                f"janela maior que {max_length} tokens."
            )

        invalid_ids = (
            set(labels)
            - valid_label_ids
        )

        if invalid_ids:
            raise ValueError(
                f"{split_name}, chunk {chunk_index}: "
                f"IDs de rótulo inválidos: {invalid_ids}"
            )


def parse_args() -> argparse.Namespace:
    """
    Define os argumentos de linha de comando.
    """
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(
            "data/processed/splits"
        ),
        help=(
            "Pasta que contém train.json, "
            "validation.json e test.json."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "data/processed/huggingface_ner"
        ),
        help=(
            "Pasta que receberá o DatasetDict "
            "no formato Hugging Face."
        ),
    )

    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="Modelo/tokenizer pré-treinado.",
    )

    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help="Quantidade máxima de tokens por janela.",
    )

    parser.add_argument(
        "--stride",
        type=int,
        default=DEFAULT_STRIDE,
        help="Sobreposição entre janelas consecutivas.",
    )

    return parser.parse_args()


def run_pipeline(
    args: argparse.Namespace,
) -> DatasetDict:
    """
    Executa toda a preparação do dataset.
    """
    if args.max_length <= 2:
        raise ValueError(
            "max_length precisa ser maior que 2."
        )

    if args.stride < 0:
        raise ValueError(
            "stride não pode ser negativo."
        )

    if args.stride >= args.max_length:
        raise ValueError(
            "stride deve ser menor que max_length."
        )

    print(
        f"Carregando tokenizer: {args.model_name}"
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name,
        use_fast=True,
    )
    
    tokenizer.model_max_length = 1_000_000

    # Somente tokenizers rápidos oferecem offset_mapping.
    if not tokenizer.is_fast:
        raise ValueError(
            "O tokenizer escolhido não é um Fast Tokenizer "
            "e não fornece offset_mapping."
        )

    input_files = {
        "train": args.input_dir / "train.json",
        "validation": (
            args.input_dir / "validation.json"
        ),
        "test": args.input_dir / "test.json",
    }

    prepared_splits = {}
    all_statistics = {}

    for split_name, input_path in input_files.items():
        print(
            f"\nPreparando split: {split_name}"
        )

        documents = load_json(
            input_path
        )

        chunks, statistics = prepare_split(
            documents=documents,
            split_name=split_name,
            tokenizer=tokenizer,
            max_length=args.max_length,
            stride=args.stride,
        )

        validate_tokenized_chunks(
            chunks=chunks,
            split_name=split_name,
            max_length=args.max_length,
        )

        prepared_splits[split_name] = (
            Dataset.from_list(chunks)
        )

        all_statistics[split_name] = (
            statistics
        )

    dataset = DatasetDict(
        prepared_splits
    )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Salva o DatasetDict no formato nativo da Hugging Face.
    dataset.save_to_disk(
        str(args.output_dir)
    )

    metadata = {
        "model_name": args.model_name,
        "max_length": args.max_length,
        "stride": args.stride,
        "entity_labels": ENTITY_LABELS,
        "bio_labels": BIO_LABELS,
        "label2id": LABEL2ID,

        # Chaves JSON precisam ser texto.
        "id2label": {
            str(index): label
            for index, label in ID2LABEL.items()
        },

        "statistics": all_statistics,

        "validation": {
            "all_entities_found": True,
            "all_chunk_lengths_valid": True,
            "all_label_ids_valid": True,
        },
    }

    save_json(
        metadata,
        args.output_dir
        / "preparation_metadata.json",
    )

    print(
        "\nPreparação concluída com sucesso!"
    )

    print(
        f"Dataset salvo em: {args.output_dir}"
    )

    print(
        "\nEstatísticas:"
    )

    print(
        json.dumps(
            all_statistics,
            ensure_ascii=False,
            indent=2,
        )
    )

    return dataset


if __name__ == "__main__":
    run_pipeline(
        parse_args()
    )