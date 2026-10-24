import json
import shutil
import argparse
from pathlib import Path
from typing import Any

from src.nlp.embeddings import DEFAULT_MODEL, ResumeEmbedder
from src.nlp.skills_extractor import extract_skills


def read_json(path: Path) -> dict[str, Any]:
    """Lê um arquivo JSON."""
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Salva um dicionário em JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reprocessa um currículo usando o extrator atualizado."
    )

    parser.add_argument(
        "--resume-dir",
        type=Path,
        required=True,
        help="Pasta do currículo original.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/amostra_real_validation_v3"),
        help="Pasta onde os novos resultados serão salvos.",
    )

    args = parser.parse_args()

    # Arquivos da versão anterior.
    text_path = args.resume_dir / "curriculo.txt"
    extraction_path = args.resume_dir / "extracao.json"
    embeddings_path = args.resume_dir / "embeddings.json"

    for path in (text_path, extraction_path, embeddings_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )

    text = text_path.read_text(encoding="utf-8")
    old_extraction = read_json(extraction_path)
    old_embeddings = read_json(embeddings_path)

    # Reutiliza as entidades do NER já salvas.
    ner_result = old_extraction.get("ner_result") or {}
    ner_entities = ner_result.get("entities", [])

    if not isinstance(ner_entities, list):
        raise ValueError(
            "ner_result.entities precisa ser uma lista."
        )

    # Executa a versão atualizada do extrator.
    hybrid = extract_skills(
        text=text,
        ner_entities=ner_entities,
    )

    semantic_inputs = hybrid["semantic_inputs"]

    if not semantic_inputs:
        raise ValueError(
            "O extrator não gerou entradas semânticas."
        )

    # Mantém o mesmo modelo e a configuração do ResumeEmbedder.
    model_name = old_embeddings.get(
        "model_name",
        DEFAULT_MODEL,
    )

    embedder = ResumeEmbedder(model_name=model_name)

    new_embeddings = embedder.encode(semantic_inputs)

    # Preserva os identificadores do currículo original.
    for key in ("resume_id", "source_index", "text_sha256"):
        if key in old_embeddings:
            new_embeddings[key] = old_embeddings[key]

    resume_id = str(
        old_embeddings.get("resume_id")
        or old_extraction.get("resume_id")
        or args.resume_dir.name
    )

    target_dir = args.output_dir / resume_id
    target_dir.mkdir(parents=True, exist_ok=True)

    # Salva a extração atualizada.
    new_extraction = {
        "resume_id": resume_id,
        "source_index": old_extraction.get(
            "source_index",
            old_embeddings.get("source_index"),
        ),
        "ner_result": ner_result,
        "hybrid_skills": hybrid,
    }

    write_json(
        target_dir / "extracao.json",
        new_extraction,
    )

    write_json(
        target_dir / "embeddings.json",
        new_embeddings,
    )

    shutil.copy2(
        text_path,
        target_dir / "curriculo.txt",
    )

    print("\nReprocessamento concluído!")
    print(f"Currículo: {resume_id}")
    print(f"Modelo: {model_name}")
    print(f"Habilidades únicas: {hybrid['statistics']['unique_skills']}")
    print(f"Blocos de contexto: {len(hybrid['context_blocks'])}")
    print(f"Entradas semânticas: {len(semantic_inputs)}")
    print(f"Embeddings gerados: {len(new_embeddings['embeddings'])}")
    print(f"Resultados salvos em: {target_dir}")


if __name__ == "__main__":
    main()
