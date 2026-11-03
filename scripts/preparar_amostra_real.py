"""
Prepara uma amostra real para desenvolver a comparação semântica.

Usa os modelos existentes, sem treinamento.
Não calcula similaridade nem métricas de ranking nesta etapa.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path


def save_json(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_sample(path, sample_size, seed):
    """Seleciona currículos completos, sem usar suas entidades anotadas."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, list):
        raise ValueError("O arquivo deve conter uma lista de currículos.")

    if not 1 <= sample_size <= len(data):
        raise ValueError(
            f"O tamanho da amostra deve ficar entre 1 e {len(data)}."
        )

    # Não descartamos exemplos silenciosamente.
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Registro {index} não é um objeto.")

        text = item.get("content")

        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Currículo {index} sem content válido.")

    rng = random.Random(seed)
    selected_indices = sorted(
        rng.sample(range(len(data)), sample_size)
    )

    sample = []

    for index in selected_indices:
        text = data[index]["content"]

        # Identificador baseado no conteúdo, para rastrear o currículo.
        text_hash = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

        sample.append({
            "resume_id": f"cv_{index:03d}_{text_hash[:8]}",
            "source_index": index,
            "text_sha256": text_hash,
            "text": text,
        })

    return sample, len(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/splits/validation.json"),
    )

    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/ner/augmented/best_model"),
    )

    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/amostra_real_validation"),
    )

    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {args.input}"
        )

    if not args.model_dir.is_dir():
        raise FileNotFoundError(
            f"Modelo NER não encontrado: {args.model_dir}. "
            "Informe a pasta correta usando --model-dir."
        )

    sample, total = load_sample(
        args.input,
        args.sample_size,
        args.seed,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "purpose": "Desenvolvimento da comparação semântica",
        "source_file": str(args.input),
        "source_file_sha256": hashlib.sha256(
            args.input.read_bytes()
        ).hexdigest(),
        "split": "validation",
        "seed": args.seed,
        "total_resumes": total,
        "sample_size": len(sample),
        "ner_model_directory": str(args.model_dir),
        "annotation_note": (
            "As entidades anotadas do dataset não foram usadas "
            "como entrada do NER ou do extrator."
        ),
        "selected_resumes": [
            {
                key: value
                for key, value in item.items()
                if key != "text"
            }
            for item in sample
        ],
        "results": [],
    }

    manifest_path = args.output_dir / "manifest.json"
    save_json(manifest, manifest_path)

    # Importações locais permitem inspecionar a seleção sem carregar modelos.
    from src.nlp.inference import ResumeNERPredictor
    from src.nlp.skills_extractor import extract_skills
    from src.nlp.embeddings import ResumeEmbedder

    print(f"Currículos disponíveis: {total}")
    print(f"Selecionados: {len(sample)} | Semente: {args.seed}")

    print("\nCarregando o NER...")
    predictor = ResumeNERPredictor(
        model_directory=args.model_dir
    )

    print("Carregando o Sentence Transformer...")
    embedder = ResumeEmbedder()

    manifest["embedding_model"] = embedder.model_name
    save_json(manifest, manifest_path)

    failures = 0

    for position, item in enumerate(sample, start=1):
        resume_id = item["resume_id"]
        text = item["text"]
        folder = args.output_dir / resume_id
        folder.mkdir(parents=True, exist_ok=True)

        print(
            f"\n[{position}/{len(sample)}] "
            f"Processando {resume_id}"
        )

        (folder / "curriculo.txt").write_text(
            text,
            encoding="utf-8",
        )

        try:
            ner_result = predictor.predict(
                text=text,
                minimum_confidence=0.0,
            )

            extraction = extract_skills(
                text=text,
                ner_entities=ner_result["entities"],
            )

            if "semantic_inputs" not in extraction:
                raise ValueError(
                    "O extrator está sem semantic_inputs. "
                    "Confira se salvou a versão atualizada."
                )

            save_json(
                {
                    "resume_id": resume_id,
                    "source_index": item["source_index"],
                    "ner_result": ner_result,
                    "hybrid_skills": extraction,
                },
                folder / "extracao.json",
            )

            semantic_inputs = extraction["semantic_inputs"]

            if not any(
                isinstance(entry.get("text"), str)
                and entry["text"].strip()
                for entry in semantic_inputs
            ):
                manifest["results"].append({
                    "resume_id": resume_id,
                    "status": "sem_textos_para_embedding",
                    "message": (
                        "Revise a extração: nenhuma skill ou "
                        "seção de contexto foi encontrada."
                    ),
                })

                print("Sem entradas para embeddings. Revisão necessária.")

            else:
                embeddings = embedder.encode(semantic_inputs)

                embeddings["resume_id"] = resume_id
                embeddings["source_index"] = item["source_index"]
                embeddings["text_sha256"] = item["text_sha256"]

                save_json(
                    embeddings,
                    folder / "embeddings.json",
                )

                result = {
                    "resume_id": resume_id,
                    "status": "ok",
                    "skills_count": len(extraction["skills"]),
                    "context_blocks_count": len(
                        extraction.get("context_blocks", [])
                    ),
                    "semantic_inputs_count": len(semantic_inputs),
                    "embedding_count": len(
                        embeddings["embeddings"]
                    ),
                    "embedding_dimension": (
                        embeddings["embedding_dimension"]
                    ),
                }

                manifest["results"].append(result)

                print(
                    f"Skills: {result['skills_count']} | "
                    f"Contextos: {result['context_blocks_count']} | "
                    f"Vetores: {result['embedding_count']}"
                )

        except Exception as error:
            failures += 1

            manifest["results"].append({
                "resume_id": resume_id,
                "status": "erro",
                "error_type": type(error).__name__,
                "message": str(error),
            })

            print(f"Erro em {resume_id}: {error}")

        # Salva o progresso depois de cada currículo.
        save_json(manifest, manifest_path)

    successful = sum(
        result["status"] == "ok"
        for result in manifest["results"]
    )

    empty = sum(
        result["status"] == "sem_textos_para_embedding"
        for result in manifest["results"]
    )

    print("\nResumo")
    print(f"Com embeddings: {successful}")
    print(f"Sem entradas extraídas: {empty}")
    print(f"Com erro: {failures}")
    print(f"Manifesto: {manifest_path}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()