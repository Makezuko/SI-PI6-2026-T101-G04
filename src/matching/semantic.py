"""
Comparação semântica e avaliação de evidências.

Não calcula a aderência final entre currículo e requisito.
Calcula similaridades de cosseno e avalia a posição das evidências
manualmente anotadas no ranking.
"""

import numpy as np


def cosine_matrix(requirement_vectors, resume_vectors):
    """
    Calcula a matriz de similaridade de cosseno.

    Cada linha representa um requisito.
    Cada coluna representa um chunk do currículo.
    """

    matrices = []

    for values in (requirement_vectors, resume_vectors):
        array = np.asarray(values, dtype=float)

        if array.ndim != 2 or not array.size:
            raise ValueError("Matriz de embeddings vazia ou com formato inválido.")

        if not np.isfinite(array).all():
            raise ValueError("Matriz de embeddings contém valores não finitos.")

        norms = np.linalg.norm(array, axis=1, keepdims=True)

        if (norms == 0).any():
            raise ValueError("Embedding com norma zero.")

        matrices.append(array / norms)

    if matrices[0].shape[1] != matrices[1].shape[1]:
        raise ValueError("Dimensões dos embeddings incompatíveis.")

    return np.clip(
        matrices[0] @ matrices[1].T,
        -1,
        1,
    )


def compare(requirements, requirement_vectors, resume):
    """
    Compara requisitos com as evidências do currículo.

    Os chunks são agrupados pelo input_index original.
    Assim, chunks sobrepostos da mesma entrada não aparecem
    como evidências independentes no ranking.

    Para cada entrada, é mantido o chunk com maior similaridade.
    """

    records = resume.get("records", [])
    embeddings = resume.get("embeddings", [])

    if not records or not embeddings:
        raise ValueError("O currículo não possui registros ou embeddings.")

    if len(records) != len(embeddings):
        raise ValueError("Registros e vetores do currículo não correspondem.")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Registro {index} possui formato inválido.")

        input_index = record.get("input_index")

        if not isinstance(input_index, int) or isinstance(input_index, bool) or input_index < 0:
            raise ValueError(f"Registro {index} possui input_index inválido.")

        if not isinstance(record.get("text"), str):
            raise ValueError(f"Registro {index} não possui texto válido.")

        if not isinstance(record.get("source"), str):
            raise ValueError(f"Registro {index} não possui source válido.")

    matrix = cosine_matrix(
        requirement_vectors,
        embeddings,
    )

    if len(requirements) != len(matrix):
        raise ValueError("Quantidade de requisitos e vetores incompatível.")

    result = []

    for requirement, scores in zip(requirements, matrix):
        if not isinstance(requirement, dict):
            raise ValueError("Requisito possui formato inválido.")

        if "id" not in requirement or "text" not in requirement:
            raise ValueError("Requisito deve possuir id e text.")

        grouped = {}

        skill_scores = []

        for index, score in enumerate(scores):
            record = records[index]
            input_index = record["input_index"]
            similarity = float(score)

            candidate = {
                "input_index": input_index,
                "similarity": similarity,
                "text": record["text"],
                "source": record["source"],
                "chunk_index": record.get("chunk_index", 0),
                "metadata": record.get("metadata", {}),
            }

            # Guarda o maior score de cada entrada original.
            if input_index not in grouped or similarity > grouped[input_index]["similarity"]:
                grouped[input_index] = candidate

            # Similaridade entre o requisito e chunks de skills.
            if record["source"] == "skill":
                skill_scores.append(similarity)

        ranked = sorted(
            grouped.values(),
            key=lambda item: (
                -item["similarity"],
                item["input_index"],
            ),
        )

        if not ranked:
            raise ValueError(f"Nenhuma evidência encontrada para o requisito {requirement['id']}.")

        result.append(
            {
                "id": requirement["id"],
                "requirement": requirement["text"],
                "top_similarity": ranked[0]["similarity"],
                "skills_only_similarity": (max(skill_scores) if skill_scores else None),
                "ranking": ranked,
            }
        )

    return result, matrix


def evaluate_ranking(results, requirements):
    """
    Avalia o ranking com base nas evidências positivas anotadas.

    Métricas:
    - Hit@1: proporção de requisitos com evidência relevante em 1º lugar.
    - Hit@3: proporção de requisitos com evidência relevante entre os 3 primeiros.
    - MRR: média dos recíprocos das posições da primeira evidência relevante.

    Estados das anotações:
    - Lista com índices: positivo anotado.
    - Lista vazia: sem evidência anotada.
    - None ou campo ausente: não anotado.

    Requisitos sem evidência anotada e não anotados não entram
    no cálculo das métricas de ranking.
    """

    if len(results) != len(requirements):
        raise ValueError("Resultados e requisitos não correspondem.")

    per_requirement = []

    for row, requirement in zip(results, requirements):
        if row.get("id") != requirement.get("id"):
            raise ValueError("A ordem dos resultados não corresponde à ordem dos requisitos.")

        gold = requirement.get("acceptable_input_indices")

        # Identifica o estado da anotação.
        if gold is None:
            status = "não anotado"

        elif not isinstance(gold, list):
            raise ValueError("Anotação deve ser uma lista de input_index.")

        elif not gold:
            status = "sem evidência anotada"

        else:
            status = "positivo anotado"

        # Valida os índices anotados.
        if status == "positivo anotado":
            for input_index in gold:
                if (
                    not isinstance(input_index, int)
                    or isinstance(input_index, bool)
                    or input_index < 0
                ):
                    raise ValueError(
                        f"Índice de evidência inválido no requisito "
                        f"{requirement['id']}: {input_index}"
                    )

            if len(gold) != len(set(gold)):
                raise ValueError(
                    f"Índices duplicados na anotação do requisito {requirement['id']}."
                )

        ranking = row.get("ranking", [])

        if not ranking:
            raise ValueError(f"Ranking vazio para o requisito {requirement['id']}.")

        # Procura a primeira evidência relevante no ranking.
        rank = None

        if status == "positivo anotado":
            rank = next(
                (
                    position
                    for position, evidence in enumerate(ranking, 1)
                    if evidence["input_index"] in gold
                ),
                None,
            )

        # Diferença entre as duas maiores similaridades.
        margin = ranking[0]["similarity"] - ranking[1]["similarity"] if len(ranking) > 1 else None

        # Reciprocal Rank.
        reciprocal_rank = None

        if status == "positivo anotado":
            reciprocal_rank = 1 / rank if rank is not None else 0.0

        per_requirement.append(
            {
                "id": row["id"],
                "annotation_status": status,
                "first_relevant_rank": rank,
                "reciprocal_rank": reciprocal_rank,
                "top1_top2_margin": margin,
            }
        )

    # Somente requisitos com evidências positivas entram nas métricas.
    positives = [
        item for item in per_requirement if item["annotation_status"] == "positivo anotado"
    ]

    ranks = [item["first_relevant_rank"] for item in positives]

    def mean(values):
        """
        Calcula a média ou retorna None quando não existem valores.
        """
        return float(np.mean(values)) if values else None

    # Métricas de ranking.
    hit_at_1 = mean([rank == 1 for rank in ranks])

    hit_at_3 = mean([rank is not None and rank <= 3 for rank in ranks])

    mrr = mean([1 / rank if rank is not None else 0 for rank in ranks])

    return {
        "total_requirements": len(results),
        "evaluated_positive_count": len(positives),
        "no_evidence_count": sum(
            item["annotation_status"] == "sem evidência anotada" for item in per_requirement
        ),
        "unannotated_count": sum(
            item["annotation_status"] == "não anotado" for item in per_requirement
        ),
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "mrr": mrr,
        "per_requirement": per_requirement,
    }


def aggregate_requirement_windows(requirements, encoded):
    """One L2-normalized mean vector per requirement, in original ID order.

    Every window contributes equally; overlap is retained. No requirement is
    duplicated in scoring. Evidence windows retain their original max pooling.
    """
    vectors = np.asarray(encoded["embeddings"], dtype=float)
    records = encoded["records"]
    if vectors.ndim != 2 or len(vectors) != len(records) or not np.isfinite(vectors).all():
        raise ValueError("Matriz de janelas invalida.")
    groups = [[] for _ in requirements]
    for record, vector in zip(records, vectors):
        index = record.get("input_index")
        if type(index) is not int or not 0 <= index < len(requirements):
            raise ValueError("Associacao de requisito invalida.")
        rid = record.get("metadata", {}).get("requirement_id")
        if rid is not None and rid != requirements[index]["id"]:
            raise ValueError("ID do requisito desalinhado.")
        groups[index].append(vector)
    result = []
    for group in groups:
        if not group:
            raise ValueError("Requisito sem janela valida.")
        mean = np.mean(group, axis=0)
        norm = np.linalg.norm(mean)
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError("Representacao de requisito invalida.")
        result.append((mean / norm).tolist())
    return result
