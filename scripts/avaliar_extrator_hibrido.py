
"""
Avaliação ponta a ponta do extrator híbrido de currículos.

Pipeline:
1. Recupera as entidades NER.
2. Executa o extrator híbrido de skills e contextos.
3. Audita os índices das anotações manuais.
4. Gera embeddings dos requisitos e evidências.
5. Compara requisitos com evidências.
6. Avalia o ranking usando Hit@1, Hit@3 e MRR.

IMPORTANTE:
As anotações manuais precisam corresponder à versão atual
da extração. A avaliação só é executada com --confirm-annotations,
após a conferência do arquivo de auditoria.
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.nlp.skills_extractor import extract_skills
from src.nlp.embeddings import ResumeEmbedder, DEFAULT_MODEL
from src.matching.semantic import compare, evaluate_ranking


# ============================================================
# 1. LEITURA E ESCRITA DE ARQUIVOS
# ============================================================

def read_json(path: Path) -> Any:
    """Lê um arquivo JSON, inclusive quando possui BOM."""

    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    """Salva resultados em JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Salva resultados por requisito em CSV."""

    if not rows:
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# 2. CARREGAMENTO DOS DADOS
# ============================================================

def load_resume(resume_dir: Path):
    """Carrega texto, extração NER e configuração de embeddings."""

    text_path = resume_dir / "curriculo.txt"
    extraction_path = resume_dir / "extracao.json"
    embeddings_path = resume_dir / "embeddings.json"

    for path in (text_path, extraction_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Arquivo necessário não encontrado: {path}"
            )

    text = text_path.read_text(encoding="utf-8-sig")

    extraction = read_json(extraction_path)

    # O arquivo de embeddings anterior é usado somente
    # para recuperar o nome do modelo, não seus vetores.
    if embeddings_path.is_file():
        previous_embeddings = read_json(embeddings_path)
    else:
        previous_embeddings = {}

    ner_result = extraction.get("ner_result") or {}
    ner_entities = ner_result.get("entities", [])

    if not isinstance(ner_entities, list):
        raise ValueError(
            "ner_result.entities precisa ser uma lista."
        )

    resume_id = str(
        extraction.get("resume_id")
        or previous_embeddings.get("resume_id")
        or resume_dir.name
    )

    model_name = previous_embeddings.get(
        "model_name",
        DEFAULT_MODEL,
    )

    return text, ner_entities, resume_id, model_name


# ============================================================
# 3. CARREGAMENTO DAS ANOTAÇÕES
# ============================================================

def load_annotations(path: Path):
    """Carrega requisitos e suas evidências aceitas."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo de anotações não encontrado: {path}"
        )

    data = read_json(path)

    requirements = data.get("requirements")

    if not isinstance(requirements, list) or not requirements:
        raise ValueError(
            "O arquivo de anotações precisa conter requirements."
        )

    requirement_ids = set()

    for requirement in requirements:

        if not isinstance(requirement, dict):
            raise ValueError(
                "Cada requisito precisa ser um objeto JSON."
            )

        requirement_id = requirement.get("id")
        requirement_text = requirement.get("text")

        if not isinstance(requirement_id, str) or not requirement_id:
            raise ValueError(
                "Cada requisito precisa ter um ID textual."
            )

        if requirement_id in requirement_ids:
            raise ValueError(
                f"ID de requisito duplicado: {requirement_id}"
            )

        requirement_ids.add(requirement_id)

        if not isinstance(requirement_text, str) or not requirement_text.strip():
            raise ValueError(
                f"Requisito {requirement_id} sem texto válido."
            )

        # Campo ausente ou null significa não anotado.
        acceptable = requirement.get(
            "acceptable_input_indices"
        )

        if acceptable is not None:

            if not isinstance(acceptable, list):
                raise ValueError(
                    f"{requirement_id}: acceptable_input_indices "
                    "precisa ser uma lista ou null."
                )

            if any(
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                for index in acceptable
            ):
                raise ValueError(
                    f"{requirement_id}: índices inválidos."
                )

            if len(acceptable) != len(set(acceptable)):
                raise ValueError(
                    f"{requirement_id}: índices duplicados."
                )

    return requirements


# ============================================================
# 4. EXECUÇÃO DO EXTRATOR HÍBRIDO
# ============================================================

def run_hybrid_extractor(text, ner_entities):
    """Executa a extração de skills e contextos."""

    hybrid = extract_skills(
        text=text,
        ner_entities=ner_entities,
    )

    semantic_inputs = hybrid.get("semantic_inputs", [])

    if not semantic_inputs:
        raise ValueError(
            "O extrator híbrido não produziu evidências semânticas."
        )

    for index, item in enumerate(semantic_inputs):

        if not isinstance(item, dict):
            raise ValueError(
                f"Entrada semântica inválida no índice {index}."
            )

        if not isinstance(item.get("text"), str):
            raise ValueError(
                f"Entrada sem texto válido no índice {index}."
            )

        if not item["text"].strip():
            raise ValueError(
                f"Entrada vazia no índice {index}."
            )

        if not isinstance(item.get("source"), str):
            raise ValueError(
                f"Entrada sem source válido no índice {index}."
            )

    return hybrid, semantic_inputs


# ============================================================
# 5. AUDITORIA DAS ANOTAÇÕES
# ============================================================

def build_annotation_audit(requirements, semantic_inputs):
    """
    Relaciona cada índice anotado com a evidência atual.

    Isso permite verificar se as anotações antigas ainda
    correspondem aos textos extraídos pela versão atual.
    """

    total_inputs = len(semantic_inputs)

    audit = []

    for requirement in requirements:

        indices = requirement.get(
            "acceptable_input_indices"
        )

        if indices is None:
            status = "não anotado"
            evidence_list = []

        elif not indices:
            status = "sem evidência anotada"
            evidence_list = []

        else:
            status = "positivo anotado"
            evidence_list = []

            for index in indices:

                if index >= total_inputs:
                    raise ValueError(
                        f"{requirement['id']}: índice anotado "
                        f"{index} não existe na extração atual. "
                        f"Total de entradas: {total_inputs}."
                    )

                item = semantic_inputs[index]

                evidence_list.append({
                    "input_index": index,
                    "text": item["text"],
                    "source": item["source"],
                    "metadata": {
                        key: value
                        for key, value in item.items()
                        if key not in ("text", "source")
                    },
                })

        audit.append({
            "requirement_id": requirement["id"],
            "requirement": requirement["text"],
            "annotation_status": status,
            "acceptable_input_indices": indices,
            "annotated_evidence": evidence_list,
        })

    return {
        "total_semantic_inputs": total_inputs,
        "total_requirements": len(requirements),
        "requirements": audit,
    }


# ============================================================
# 6. GERAÇÃO DE EMBEDDINGS E COMPARAÇÃO
# ============================================================

def run_semantic_matching(
    requirements,
    semantic_inputs,
    model_name,
):
    """Gera embeddings e compara requisitos com evidências."""

    embedder = ResumeEmbedder(
        model_name=model_name
    )

    requirement_inputs = [
        {
            "text": requirement["text"],
            "source": "requirement",
        }
        for requirement in requirements
    ]

    print("\nGerando embeddings dos requisitos...")

    requirement_embeddings = embedder.encode(
        requirement_inputs
    )

    print("\nGerando embeddings das evidências...")

    resume_embeddings = embedder.encode(
        semantic_inputs
    )

    if (
        requirement_embeddings["embedding_dimension"]
        != resume_embeddings["embedding_dimension"]
    ):
        raise ValueError(
            "As dimensões dos embeddings são incompatíveis."
        )

    print("\nCalculando similaridades semânticas...")

    results, _ = compare(
        requirements,
        requirement_embeddings["embeddings"],
        resume_embeddings,
    )

    return results, resume_embeddings


# ============================================================
# 7. AVALIAÇÃO DO RANKING
# ============================================================

def evaluate_results(results, requirements):
    """Calcula Hit@1, Hit@3 e MRR."""

    return evaluate_ranking(
        results,
        requirements,
    )


# ============================================================
# 8. ORGANIZAÇÃO DOS RESULTADOS
# ============================================================

def build_requirement_report(
    results,
    requirements,
    evaluation,
):
    """Combina ranking e anotações em um relatório por requisito."""

    evaluation_by_id = {
        item["id"]: item
        for item in evaluation["per_requirement"]
    }

    annotation_by_id = {
        item["id"]: item
        for item in requirements
    }

    rows = []

    for result in results:

        requirement_id = result["id"]

        annotation = annotation_by_id[requirement_id]
        ranking_evaluation = evaluation_by_id[requirement_id]

        ranking = result["ranking"]
        top_evidence = ranking[0] if ranking else {}

        rows.append({
            "requirement_id": requirement_id,
            "requirement": result["requirement"],
            "category": annotation.get("category"),
            "acceptable_input_indices": annotation.get(
                "acceptable_input_indices"
            ),
            "first_relevant_rank": ranking_evaluation[
                "first_relevant_rank"
            ],
            "reciprocal_rank": ranking_evaluation[
                "reciprocal_rank"
            ],
            "top1_text": top_evidence.get("text"),
            "top1_source": top_evidence.get("source"),
            "top1_input_index": top_evidence.get("input_index"),
            "top1_similarity": result["top_similarity"],
            "skills_only_similarity": result[
                "skills_only_similarity"
            ],
            "annotation_status": ranking_evaluation[
                "annotation_status"
            ],
        })

    return rows


# ============================================================
# 9. EXECUÇÃO PRINCIPAL
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Avaliação ponta a ponta do extrator híbrido."
    )

    parser.add_argument(
        "--resume-dir",
        type=Path,
        required=True,
        help="Diretório com curriculo.txt e extracao.json.",
    )

    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path(
            "examples/requisitos_cv001_v4_anotacoes.json"
        ),
        help="Arquivo JSON com requisitos e evidências anotadas.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "reports/avaliacao_extrator_hibrido"
        ),
        help="Diretório para salvar os resultados.",
    )

    parser.add_argument(
        "--confirm-annotations",
        action="store_true",
        help=(
            "Confirma que as evidências do arquivo de auditoria "
            "foram verificadas manualmente."
        ),
    )

    args = parser.parse_args()

    print("=" * 65)
    print("AVALIAÇÃO DO EXTRATOR HÍBRIDO")
    print("=" * 65)

    # --------------------------------------------------------
    # 1. Carregar dados
    # --------------------------------------------------------

    print("\n[1/6] Carregando currículo e entidades NER...")

    text, ner_entities, resume_id, model_name = load_resume(
        args.resume_dir
    )

    requirements = load_annotations(
        args.annotations
    )

    print(f"Currículo: {resume_id}")
    print(f"Entidades NER: {len(ner_entities)}")
    print(f"Requisitos: {len(requirements)}")
    print(f"Modelo de embeddings: {model_name}")

    # --------------------------------------------------------
    # 2. Executar extrator híbrido
    # --------------------------------------------------------

    print("\n[2/6] Executando extrator híbrido...")

    hybrid, semantic_inputs = run_hybrid_extractor(
        text,
        ner_entities,
    )

    print(
        f"Entradas semânticas extraídas: "
        f"{len(semantic_inputs)}"
    )

    print(
        f"Skills únicas: "
        f"{hybrid.get('statistics', {}).get('unique_skills', 'N/D')}"
    )

    print(
        f"Blocos de contexto: "
        f"{len(hybrid.get('context_blocks', []))}"
    )

    # --------------------------------------------------------
    # 3. Auditar anotações
    # --------------------------------------------------------

    print("\n[3/6] Auditando índices das anotações...")

    audit = build_annotation_audit(
        requirements,
        semantic_inputs,
    )

    output_dir = args.output_dir / resume_id

    audit_path = output_dir / "auditoria_anotacoes.json"

    write_json(
        audit_path,
        audit,
    )

    print(f"Auditoria salva em: {audit_path}")

    if not args.confirm_annotations:

        print("\n" + "=" * 65)
        print("AVALIAÇÃO PAUSADA PARA CONFERÊNCIA DAS ANOTAÇÕES")
        print("=" * 65)

        print(
            "\nAbra o arquivo auditoria_anotacoes.json e confira "
            "se cada input_index anotado corresponde à evidência "
            "correta na extração atual."
        )

        print(
            "\nSe estiver tudo correto, execute novamente "
            "adicionando --confirm-annotations."
        )

        return

    print(
        "\nAnotações confirmadas pelo usuário."
    )

    # --------------------------------------------------------
    # 4. Gerar embeddings e matching
    # --------------------------------------------------------

    print("\n[4/6] Executando embeddings e matching...")

    results, resume_embeddings = run_semantic_matching(
        requirements,
        semantic_inputs,
        model_name,
    )

    print(
        f"Embeddings das evidências: "
        f"{len(resume_embeddings['embeddings'])}"
    )

    # --------------------------------------------------------
    # 5. Avaliar ranking
    # --------------------------------------------------------

    print("\n[5/6] Calculando métricas de avaliação...")

    evaluation = evaluate_results(
        results,
        requirements,
    )

    requirement_report = build_requirement_report(
        results,
        requirements,
        evaluation,
    )

    # --------------------------------------------------------
    # 6. Salvar resultados
    # --------------------------------------------------------

    print("\n[6/6] Salvando resultados...")

    summary = {
        "resume_id": resume_id,
        "evaluation_type": "hybrid_extractor_end_to_end",
        "embedding_model": model_name,
        "ner_entities_count": len(ner_entities),
        "semantic_inputs_count": len(semantic_inputs),
        "unique_skills": hybrid.get(
            "statistics", {}
        ).get("unique_skills"),
        "context_blocks_count": len(
            hybrid.get("context_blocks", [])
        ),
        "embedding_count": len(
            resume_embeddings["embeddings"]
        ),
        "embedding_dimension": resume_embeddings[
            "embedding_dimension"
        ],
        "ranking_metrics": {
            "total_requirements": evaluation[
                "total_requirements"
            ],
            "evaluated_positive_count": evaluation[
                "evaluated_positive_count"
            ],
            "no_evidence_count": evaluation[
                "no_evidence_count"
            ],
            "unannotated_count": evaluation[
                "unannotated_count"
            ],
            "hit_at_1": evaluation["hit_at_1"],
            "hit_at_3": evaluation["hit_at_3"],
            "mrr": evaluation["mrr"],
        },
        "per_requirement": requirement_report,
    }

    write_json(
        output_dir / "metricas.json",
        summary,
    )

    write_json(
        output_dir / "ranking_completo.json",
        {"results": results},
    )

    write_csv(
        output_dir / "metricas_por_requisito.csv",
        requirement_report,
    )

    # --------------------------------------------------------
    # Exibir resumo
    # --------------------------------------------------------

    metrics = summary["ranking_metrics"]

    print("\n" + "=" * 65)
    print("RESULTADO DA AVALIAÇÃO")
    print("=" * 65)

    print(f"Currículo: {resume_id}")

    print(
        f"Requisitos avaliados positivamente: "
        f"{metrics['evaluated_positive_count']}"
    )

    print(
        f"Requisitos sem evidência anotada: "
        f"{metrics['no_evidence_count']}"
    )

    print(
        f"Requisitos não anotados: "
        f"{metrics['unannotated_count']}"
    )

    def show_metric(name, value):

        if value is None:
            print(f"{name}: N/A")
        else:
            print(
                f"{name}: {value:.4f} "
                f"({value * 100:.2f}%)"
            )

    show_metric("Hit@1", metrics["hit_at_1"])
    show_metric("Hit@3", metrics["hit_at_3"])
    show_metric("MRR", metrics["mrr"])

    print("\nArquivos gerados:")

    print(output_dir / "auditoria_anotacoes.json")
    print(output_dir / "metricas.json")
    print(output_dir / "ranking_completo.json")
    print(output_dir / "metricas_por_requisito.csv")

    print("\nAvaliação concluída!")


if __name__ == "__main__":
    main()
