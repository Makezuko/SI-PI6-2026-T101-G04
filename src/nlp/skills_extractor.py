"""
Extrator híbrido de competências de currículos.

O extrator combina:

1. seções explícitas do currículo;
2. blocos Skills previstos pelo NER;
3. segmentação por vírgulas, marcadores e quebras de linha;
4. normalização e deduplicação.

A detecção por seção é prioritária porque o NER apresentou baixo F1 para
Skills e dificuldade para determinar o começo e o fim de blocos extensos.

O Sentence Transformer ainda não é utilizado aqui. Esta etapa apenas
produz uma lista limpa de competências individuais.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any


# Títulos que indicam o começo de uma seção de competências.
SKILL_SECTION_HEADINGS = {
    "skills",
    "technical skills",
    "technical skill",
    "technical competencies",
    "technical competency",
    "core competencies",
    "core competency",
    "key skills",
    "professional skills",
    "computer skills",
    "it skills",
    "technology skills",
    "technologies",
    "tools",
    "tools and technologies",
    "tools & technologies",
    "programming languages",
    "technical proficiencies",
    "areas of expertise",
    "expertise",
    "competencies",
    "software skills",
    "software proficiency",
    "technical summary",
    "skill set",
    "technical skill set",
}

# Algumas tecnologias válidas possuem somente uma ou duas letras.
# Elas precisam ser explicitamente permitidas para que o filtro não
# descarte, por exemplo, C, R ou Go junto com fragmentos inválidos.
VALID_SHORT_SKILLS = {
    "c",
    "r",
    "go",
    "c#",
    "c++",
    "f#",
    "js",
    "ts",
    "ai",
    "ml",
    "sql",
    "css",
    "php",
    "aws",
    "git",
}

# Títulos que normalmente encerram a seção de competências.
STOP_SECTION_HEADINGS = {
    "academic background",
    "academic qualifications",
    "achievements",
    "additional information",
    "awards",
    "career objective",
    "certifications",
    "certificates",
    "contact",
    "education",
    "educational qualification",
    "employment",
    "employment history",
    "experience",
    "interests",
    "internships",
    "languages",
    "objective",
    "personal details",
    "professional experience",
    "professional summary",
    "profile",
    "projects",
    "publications",
    "references",
    "summary",
    "training",
    "volunteer experience",
    "work experience",
    "work history",
}


# Prefixos usados dentro de seções de Skills.
CATEGORY_PREFIXES = {
    "backend",
    "cloud",
    "databases",
    "database",
    "development tools",
    "frameworks",
    "frontend",
    "languages",
    "libraries",
    "methodologies",
    "operating systems",
    "platforms",
    "programming",
    "programming languages",
    "software",
    "technologies",
    "tools",
    "web technologies",
}


# Expressões que normalmente indicam uma frase, e não uma skill individual.
NON_SKILL_PHRASES = {
    "responsible for",
    "worked with",
    "experience in",
    "experience with",
    "knowledge of",
    "participated in",
    "involved in",
    "ability to",
    "worked on",
    "duties included",
}


def repair_common_encoding(
    text: str,
) -> str:
    """
    Corrige alguns marcadores frequentemente corrompidos no dataset.
    """
    replacements = {
        "â€¢": "•",
        "â—": "●",
        "ï‚·": "•",
        "\uf0b7": "•",
        "\u00a0": " ",
    }

    repaired = text

    for old, new in replacements.items():
        repaired = repaired.replace(
            old,
            new,
        )

    return repaired


def is_valid_skill_candidate(skill: str) -> bool:
    """
    Verifica se um texto realmente parece representar uma competência.

    Esse filtro é necessário porque o modelo NER ainda possui baixo
    desempenho para SKILLS e pode produzir fragmentos como ".", "s"
    ou "LS". Esses fragmentos não devem chegar à etapa de comparação
    semântica com Sentence Transformers.

    Regras:
    1. rejeita textos vazios;
    2. rejeita pontuação isolada;
    3. aceita tecnologias curtas conhecidas, como C, R, Go e C#;
    4. rejeita outros textos com menos de três caracteres;
    5. exige pelo menos uma letra ou número.
    """
    if not isinstance(skill, str):
        return False

    normalized = skill.strip()
    normalized_lower = normalized.casefold()

    if not normalized:
        return False

    # Aceita explicitamente tecnologias curtas conhecidas.
    if normalized_lower in VALID_SHORT_SKILLS:
        return True

    # Rejeita ".", "-", "/", entre outros sinais isolados.
    if not any(character.isalnum() for character in normalized):
        return False

    # Fragmentos curtos que não estão na lista segura são descartados.
    if len(normalized) < 3:
        return False

    # Uma competência deve possuir ao menos uma letra.
    # Isso evita aceitar números soltos como "1" ou "2024".
    if not any(character.isalpha() for character in normalized):
        return False

    return True


def normalize_heading(
    text: str,
) -> str:
    """
    Normaliza um possível título de seção.
    """
    normalized = repair_common_encoding(
        text
    )

    normalized = normalized.strip()

    normalized = re.sub(
        r"^[•●▪◦\-\–\—\s]+",
        "",
        normalized,
    )

    normalized = re.sub(
        r"[:\-–—\s]+$",
        "",
        normalized,
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.casefold()


def split_heading_and_content(
    line: str,
) -> tuple[str, str]:
    """
    Separa linhas como:

        Technical Skills: Python, Java

    em:

        heading = Technical Skills
        content = Python, Java
    """
    repaired_line = repair_common_encoding(
        line
    ).strip()

    if ":" not in repaired_line:
        return repaired_line, ""

    heading, content = (
        repaired_line.split(
            ":",
            maxsplit=1,
        )
    )

    return (
        heading.strip(),
        content.strip(),
    )


def find_skill_sections(
    text: str,
) -> list[dict[str, Any]]:
    """
    Localiza seções explícitas de competências.

    A coleta começa quando uma linha corresponde a um título de Skills
    e termina quando outro título principal é encontrado.
    """
    repaired_text = repair_common_encoding(
        text
    )

    lines = repaired_text.splitlines()

    sections = []
    collecting = False
    current_heading = None
    current_lines = []
    section_start_line = None

    def close_section(
        end_line: int,
    ) -> None:
        nonlocal collecting
        nonlocal current_heading
        nonlocal current_lines
        nonlocal section_start_line

        if (
            collecting
            and current_lines
        ):
            block = "\n".join(
                current_lines
            ).strip()

            if block:
                sections.append(
                    {
                        "heading": (
                            current_heading
                        ),
                        "text": block,
                        "start_line": (
                            section_start_line
                        ),
                        "end_line": end_line,
                    }
                )

        collecting = False
        current_heading = None
        current_lines = []
        section_start_line = None

    for line_index, line in enumerate(
        lines
    ):
        stripped_line = line.strip()

        if not stripped_line:
            # Mantém uma quebra simples dentro da seção.
            if collecting:
                current_lines.append("")
            continue

        heading_part, inline_content = (
            split_heading_and_content(
                stripped_line
            )
        )

        normalized_heading = (
            normalize_heading(
                heading_part
            )
        )

        if (
            normalized_heading
            in SKILL_SECTION_HEADINGS
        ):
            close_section(
                line_index - 1
            )

            collecting = True
            current_heading = (
                heading_part.strip()
            )

            current_lines = []

            section_start_line = (
                line_index
            )

            if inline_content:
                current_lines.append(
                    inline_content
                )

            continue

        if (
            collecting
            and normalized_heading
            in STOP_SECTION_HEADINGS
        ):
            close_section(
                line_index - 1
            )

            continue

        if collecting:
            current_lines.append(
                stripped_line
            )

    close_section(
        len(lines) - 1
    )

    return sections


def remove_category_prefix(
    candidate: str,
) -> str:
    """
    Remove prefixos internos como:

        Databases: PostgreSQL

    retornando:

        PostgreSQL
    """
    if ":" not in candidate:
        return candidate

    prefix, content = candidate.split(
        ":",
        maxsplit=1,
    )

    if (
        normalize_heading(prefix)
        in CATEGORY_PREFIXES
    ):
        return content.strip()

    return candidate


def clean_skill_candidate(
    candidate: str,
) -> str | None:
    """
    Limpa e valida uma possível competência individual.
    """
    skill = repair_common_encoding(
        candidate
    )

    skill = skill.strip()

    skill = re.sub(
        r"^[•●▪◦\-\–\—\s]+",
        "",
        skill,
    )

    skill = re.sub(
        r"[,;:|\s]+$",
        "",
        skill,
    )

    skill = remove_category_prefix(
        skill
    )

    # Remove informações de tempo, mantendo somente a competência.
    #
    # Exemplo:
    # Python (3 years) -> Python
    skill = re.sub(
        r"\s*\(\s*"
        r"(?:less\s+than\s+)?"
        r"\d+(?:\.\d+)?\s*"
        r"(?:years?|months?)"
        r"\s*\)\s*$",
        "",
        skill,
        flags=re.IGNORECASE,
    )

    skill = re.sub(
        r"\s+",
        " ",
        skill,
    ).strip()

    if not skill:
        return None

    normalized = skill.casefold()

    if normalized in (
        SKILL_SECTION_HEADINGS
        | STOP_SECTION_HEADINGS
        | CATEGORY_PREFIXES
    ):
        return None

    # C, R e Go são exemplos válidos, portanto não usamos um limite
    # mínimo maior que um caractere.
    if len(skill) > 100:
        return None

    words = skill.split()

    # Blocos muito extensos geralmente são frases ou parágrafos.
    if len(words) > 10:
        return None

    for phrase in NON_SKILL_PHRASES:
        if phrase in normalized:
            return None

    if not re.search(
        r"[A-Za-z0-9+#.]",
        skill,
    ):
        return None

    return skill


def split_skill_block(
    block: str,
) -> list[str]:
    """
    Divide um bloco de competências em itens individuais.
    """
    repaired_block = (
        repair_common_encoding(
            block
        )
    )

    # Cada marcador é convertido para quebra de linha.
    repaired_block = re.sub(
        r"[•●▪◦]+",
        "\n",
        repaired_block,
    )

    # Separa usando delimitadores normalmente empregados em currículos.
    raw_candidates = re.split(
        r"[\n,;|]+",
        repaired_block,
    )

    skills = []

    for raw_candidate in raw_candidates:
        cleaned = clean_skill_candidate(
            raw_candidate
        )

        if cleaned is not None:
            skills.append(
                cleaned
            )

    return skills


def normalize_skill_key(
    skill: str,
) -> str:
    """
    Cria uma chave para deduplicação sem alterar o texto exibido.
    """
    normalized = skill.casefold()

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    normalized = normalized.strip()

    return normalized


def extract_ner_skill_blocks(
    ner_entities: list[
        dict[str, Any]
    ] | None,
) -> list[dict[str, Any]]:
    """
    Seleciona somente entidades SKILLS previstas pelo NER.
    """
    if not ner_entities:
        return []

    blocks = []

    for entity in ner_entities:
        label = str(
            entity.get(
                "label",
                "",
            )
        ).upper()

        if label != "SKILLS":
            continue

        text = str(
            entity.get(
                "text",
                "",
            )
        )

        if not text.strip():
            continue

        blocks.append(
            {
                "text": text,
                "confidence": float(
                    entity.get(
                        "confidence",
                        0.0,
                    )
                ),
                "start": entity.get(
                    "start"
                ),
                "end": entity.get(
                    "end"
                ),
            }
        )

    return blocks


def extract_skills(
    text: str,
    ner_entities: list[
        dict[str, Any]
    ] | None = None,
) -> dict[str, Any]:
    """
    Executa a extração híbrida de competências.

    As competências encontradas em mais de uma fonte são mantidas apenas
    uma vez, mas registram todas as suas origens.
    """
    sections = find_skill_sections(
        text
    )

    ner_blocks = extract_ner_skill_blocks(
        ner_entities
    )

    # OrderedDict preserva a ordem em que as skills aparecem.
    candidates: OrderedDict[
        str,
        dict[str, Any],
    ] = OrderedDict()

    def add_candidate(
        skill: str,
        source: str,
        evidence: str,
        confidence: float | None,
    ) -> None:
        """
        Valida, normaliza e adiciona uma competência ao resultado.

        O filtro é aplicado tanto às competências encontradas em seções
        explícitas quanto às previstas pelo NER. Isso impede que fragmentos
        como ".", "s" e "LS" cheguem ao resultado final.
        """

        # Ignora fragmentos que não parecem representar uma skill real.
        if not is_valid_skill_candidate(skill):
            return

        key = normalize_skill_key(
            skill
        )

        if not key:
            return

        if key not in candidates:
            candidates[key] = {
                "skill": skill,
                "normalized": key,
                "sources": [],
                "evidence": [],
                "ner_confidence": None,
            }

        record = candidates[key]

        if source not in record["sources"]:
            record["sources"].append(
                source
            )

        shortened_evidence = evidence[:300]

        if shortened_evidence not in record["evidence"]:
            record["evidence"].append(
                shortened_evidence
            )

        if confidence is not None:
            previous_confidence = record[
                "ner_confidence"
            ]

            if (
                previous_confidence is None
                or confidence > previous_confidence
            ):
                record[
                    "ner_confidence"
                ] = confidence

    # Primeiro adiciona as competências encontradas em seções explícitas.
    for section in sections:
        section_skills = split_skill_block(
            section["text"]
        )

        for skill in section_skills:
            add_candidate(
                skill=skill,
                source="section",
                evidence=section["text"],
                confidence=None,
            )

    # Depois adiciona as competências encontradas pelo modelo NER.
    # A função add_candidate elimina fragmentos inválidos e duplicidades.
    for block in ner_blocks:
        block_skills = split_skill_block(
            block["text"]
        )

        for skill in block_skills:
            add_candidate(
                skill=skill,
                source="ner",
                evidence=block["text"],
                confidence=block["confidence"],
            )

    # Converte o OrderedDict para uma lista pronta para serialização em JSON.
    skill_details = list(
        candidates.values()
    )

    return {
        "skills": [
            item["skill"]
            for item in skill_details
        ],
        "skill_details": (
            skill_details
        ),
        "sections_found": (
            sections
        ),
        "ner_skill_blocks": (
            ner_blocks
        ),
        "statistics": {
            "sections_found": len(
                sections
            ),
            "ner_blocks_found": len(
                ner_blocks
            ),
            "unique_skills": len(
                skill_details
            ),
            "skills_from_section": sum(
                1
                for item in skill_details
                if "section"
                in item["sources"]
            ),
            "skills_from_ner": sum(
                1
                for item in skill_details
                if "ner"
                in item["sources"]
            ),
            "skills_confirmed_by_both": sum(
                1
                for item in skill_details
                if {
                    "section",
                    "ner",
                }.issubset(
                    item["sources"]
                )
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    """
    Argumentos da linha de comando.
    """
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help=(
            "Arquivo TXT contendo o currículo."
        ),
    )

    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(
            "models/ner/augmented/best_model"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "reports/skills_extraction.json"
        ),
    )

    parser.add_argument(
        "--minimum-ner-confidence",
        type=float,
        default=0.0,
    )

    return parser.parse_args()


def main() -> None:
    """
    Executa NER e extração híbrida em um currículo.
    """
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            f"Currículo não encontrado: "
            f"{args.input}"
        )

    text = args.input.read_text(
        encoding="utf-8"
    )

    # Importação local evita carregar Torch quando apenas as funções
    # de segmentação são utilizadas nos testes.
    from src.nlp.inference import (
        ResumeNERPredictor,
    )

    predictor = ResumeNERPredictor(
        model_directory=args.model_dir
    )

    ner_result = predictor.predict(
        text=text,
        minimum_confidence=(
            args.minimum_ner_confidence
        ),
    )

    hybrid_result = extract_skills(
        text=text,
        ner_entities=ner_result[
            "entities"
        ],
    )

    complete_result = {
        "input_file": str(
            args.input
        ),
        "ner_entity_count": (
            ner_result[
                "entity_count"
            ]
        ),
        "ner_entities": (
            ner_result[
                "entities"
            ]
        ),
        "hybrid_skills": (
            hybrid_result
        ),
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            complete_result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Skills encontradas: "
        f"{len(hybrid_result['skills'])}"
    )

    for skill in hybrid_result[
        "skills"
    ]:
        print(
            f"- {skill}"
        )

    print(
        f"\nResultado salvo em: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
