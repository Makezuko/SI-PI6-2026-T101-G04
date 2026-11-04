"""Calcula o índice agregado a partir do JSON do analisador semântico."""
import argparse
import json
from pathlib import Path

from src.matching.score import calculate_similarity_index


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--weights", type=Path, help="Arquivo JSON com pesos por nível.")
    args = parser.parse_args(argv)
    try:
        data = _read_json(args.input)
        if not isinstance(data, dict) or "requirements" not in data or "results" not in data:
            raise ValueError("O JSON precisa conter requirements e results.")
        weights = _read_json(args.weights) if args.weights else None
        if args.weights and not isinstance(weights, dict):
            raise ValueError("O arquivo de pesos precisa conter um objeto JSON.")
        result = calculate_similarity_index(data["requirements"], data["results"], weights)
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Não foi possível calcular o índice: {exc}\n")
    if result["status"] == "calculado":
        print(f"Índice de compatibilidade semântica: {result['score']:.2f}/100")
    else:
        print("Análise incompleta; índice não calculado. Requisitos: "
              + ", ".join(result["incomplete_requirement_ids"]))
    print(f"Resultado salvo em: {args.output}")


if __name__ == "__main__":
    main()
