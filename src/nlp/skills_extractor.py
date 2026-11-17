
"""
Extrator híbrido de competências de currículos.

Combina:
1. Seções explícitas de competências;
2. Entidades SKILLS previstas pelo NER;
3. Segmentação por vírgulas, marcadores e quebras de linha;
4. Reconhecimento de categorias;
5. Reconstrução de competências fragmentadas;
6. Normalização, filtragem e deduplicação.

A extração por seção é prioritária porque o NER ainda apresenta
dificuldade para reconhecer os limites de competências extensas.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any


# ============================================================
# 1. CONFIGURAÇÕES
# ============================================================

SKILL_SECTION_HEADINGS = {
    "habilidades técnicas", "habilidades tecnicas", "habilidades", "competências técnicas",
    "competencias tecnicas", "competências", "conhecimentos técnicos",
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
    "technical proficiency",
    "technical proficiency skills",
    "technical expertise",
}

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

STOP_SECTION_HEADINGS = {
    "academic background",
    "academic qualifications",
    "achievements",
    "additional information",
    "additional info",
    "additional inf",
    "links",
    "personal information",
    "visa information",
    "awards",
    "career objective",
    "certifications",
    "certificates",
    "contact",
    "declaration",
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

CATEGORY_PREFIXES = {
    "backend",
    "cloud",
    "ci tools",
    "continuous build",
    "artifact repository",
    "static code analysis",
    "editors and ides",
    "library and tool",
    "libraries and tools",
    "erp packages",
    "office productivity",
    "version control",
    "version control system",
    "web designing",
    "applications",
    "middleware",
    "servers",
    "containers",
    "databases",
    "database",
    "development tools",
    "devops",
    "devops pipeline",
    "devops pipelines",
    "frameworks",
    "frontend",
    "languages",
    "libraries",
    "methodologies",
    "operating systems",
    "platforms",
    "programming",
    "programming languages",
    "scm tools",
    "software",
    "technologies",
    "tools",
    "web technologies",
}

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
    "environment like",
    "environments like",
    "working with",
    "familiar with",
}

GENERIC_SKILL_PLACEHOLDERS = {
    "specialization",
    "specialisation",
    "specilization",
    "especialização",
    "especializacao",
    "machine",
    "ificial",
    "mysq",
    "my sq",
    "additional inf",
    "additional info",
    "links",
    "visa information",
    "personal information",
    "engineer",
    "software engineer",
    "software developer",
    "developer",
    "integration",
    "year",
    "years",
    "pack",
    "software",
    "environment",
    "environments",
}

# Combinações conhecidas que podem ter sido fragmentadas.
# A junção só acontece quando o resultado corresponde exatamente
# a uma expressão desta lista.
KNOWN_FRAGMENT_COMBINATIONS = {
    "artificial intelligence": "Artificial Intelligence",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "microsoft access": "Microsoft Access",
    "microsoft word": "Microsoft Word",
    "microsoft excel": "Microsoft Excel",
    "data structures": "Data Structures",
    "data structures and algorithms": "Data Structures and Algorithms",
    "data structures & algorithms": "Data Structures & Algorithms",
    "version control system": "Version Control System",
    "static code analysis": "Static Code Analysis",
    "continuous build": "Continuous Build",
    "artifact repository": "Artifact Repository",
    "office productivity": "Office Productivity",
    "library and tool": "Library and Tool",
    "editors and ides": "Editors and IDEs",
    "cloud computing": "Cloud Computing",
}

# Categorias técnicas inferidas a partir do nome da competência.
# Essa classificação é independente da categoria encontrada no currículo.
TECHNICAL_CATEGORY_RULES = {
    "Programming Languages": {
        "python", "java", "javascript", "typescript",
        "kotlin", "swift", "go", "golang", "c",
        "c++", "c#", "f#", "php", "ruby", "scala",
        "r", "perl", "rust", "objective-c",
        "pl/sql", "sql",
    },
    "Web Technologies": {
        "html", "css", "xml",
    },
    "Frameworks and Libraries": {
        "django", "flask", "fastapi", "spring",
        "spring mvc", "react", "angular", "angular js",
        "vue", "jquery", "bootstrap", "tensorflow",
        "pytorch", "scikit-learn", "keras",
        "opencv", "pandas", "numpy",
    },
    "Databases": {
        "mysql", "my sql", "postgresql", "postgres",
        "sqlite", "mongodb", "redis", "oracle",
        "sql server", "microsoft access",
        "elasticsearch", "elastic search",
    },
    "Cloud and DevOps": {
        "aws", "azure", "gcp", "google cloud",
        "docker", "kubernetes", "jenkins",
        "terraform", "ansible", "chef",
        "git", "github", "gitlab", "svn",
        "maven", "ant", "nexus",
    },
    "Operating Systems": {
        "linux", "unix", "windows",
        "windows server", "macos",
    },
    "Data Science and AI": {
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "natural language processing",
        "computer vision",
        "data science",
        "data analysis",
        "data engineering",
        "neural networks",
        "tensorflow",
        "pytorch",
    },
    "Development Tools": {
        "eclipse", "netbeans", "pycharm",
        "jupyter", "jupyter notebook",
        "visual studio", "visual studio code",
        "intellij idea", "notepad++",
        "putty", "winscp",
    },
}


# ============================================================
# 2. NORMALIZAÇÃO E FILTROS
# ============================================================

def repair_common_encoding(text: str) -> str:
    """Corrige marcadores frequentemente corrompidos no dataset."""

    replacements = {
        "â€¢": "•",
        "â—": "●",
        "ï‚·": "•",
        "\uf0b7": "•",
        "\u00a0": " ",
    }

    repaired = text

    for old, new in replacements.items():
        repaired = repaired.replace(old, new)

    return repaired


def normalize_skill_key(skill: str) -> str:
    """Cria uma chave para deduplicação."""

    normalized = skill.casefold()
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def normalize_heading(text: str) -> str:
    """Normaliza um possível título de seção."""

    normalized = repair_common_encoding(text)
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

    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.casefold()


def normalize_skill_display(skill: str) -> str:
    """
    Normaliza a forma exibida da competência.

    Preserva tecnologias como .NET, C++ e C#.
    """

    skill = repair_common_encoding(skill).strip()

    skill = re.sub(
        r"^[•●▪◦\-\–\—\s]+",
        "",
        skill,
    )

    # Remove pontuação final sem remover o ponto inicial de .NET.
    skill = re.sub(r"[,;:|\s.]+$", "", skill)

    skill = re.sub(r"\s+", " ", skill).strip()

    aliases = {
        "git-hub": "GitHub",
        "github": "GitHub",
        "my sql": "MySQL",
        "mysql": "MySQL",
        "postgre sql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "golang": "Go",
        "jupiter notebook": "Jupyter Notebook",
        "pycharm": "PyCharm",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "linux": "Linux",
        "windows": "Windows",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "html": "HTML",
        "css": "CSS",
        "xml": "XML",
        "sql": "SQL",
        "aws": "AWS",
        "apex": "APEX",
        "dns": "DNS",
        "git": "Git",
        "svn": "SVN",
        "php": "PHP",
        "pl/sql": "PL/SQL",
        "c++": "C++",
        "c#": "C#",
        ".net": ".NET",
        "microsoft access": "Microsoft Access",
        "microsoft word": "Microsoft Word",
        "microsoft excel": "Microsoft Excel",
        "artificial intelligence": "Artificial Intelligence",
        "machine learning": "Machine Learning",
        "deep learning": "Deep Learning",
        "data structures": "Data Structures",
        "data structures and algorithms": "Data Structures and Algorithms",
        "data structures & algorithms": "Data Structures & Algorithms",
    }

    key = normalize_skill_key(skill)

    if key in aliases:
        return aliases[key]

    return skill


def is_skill_noise(text: str) -> bool:
    """Identifica links, contatos e informações que não são competências."""

    normalized = re.sub(
        r"\s+",
        " ",
        text.strip().casefold(),
    )

    if normalized in GENERIC_SKILL_PLACEHOLDERS:
        return True

    if re.search(r"\[[^\[\]]*ocult[oa]s?\]", text, re.IGNORECASE):
        return True

    if re.search(
        r"(?:https?://|www\.)\S+",
        text,
        re.IGNORECASE,
    ):
        return True

    if re.search(
        r"\b(?:indeed\.com|linkedin\.com|github\.com)/\S+",
        text,
        re.IGNORECASE,
    ):
        return True

    if re.search(
        r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
        text,
        re.IGNORECASE,
    ):
        return True

    administrative_phrases = {
        "additional information",
        "additional info",
        "visa information",
        "work permit",
        "personal information",
    }

    if normalized in administrative_phrases:
        return True

    # Informações de visto e autorização de trabalho.
    if re.search(
        r"\bvisa\b|\bwork permit\b",
        normalized,
    ):
        return True

    # Exemplos: B1 B2 US VISA till 2025.
    if re.search(
        r"\b(?:b1|b2|h1b|l1)\b.*\b(?:visa|till|until|valid)\b",
        normalized,
    ):
        return True

    # Datas isoladas ou expressões como "till 2025".
    if re.fullmatch(
        r"(?:till|until|valid until)?\s*\d{4}",
        normalized,
    ):
        return True

    return False


def is_valid_skill_candidate(skill: str) -> bool:
    """
    Verifica se um texto parece representar uma competência.
    """

    if not isinstance(skill, str):
        return False

    normalized = normalize_skill_display(skill)
    normalized_lower = normalized.casefold()

    if not normalized:
        return False

    if is_skill_noise(normalized):
        return False

    if normalized_lower in VALID_SHORT_SKILLS:
        return True

    if normalized_lower in GENERIC_SKILL_PLACEHOLDERS:
        return False

    if not any(character.isalnum() for character in normalized):
        return False

    if len(normalized) < 3:
        return False

    if not any(character.isalpha() for character in normalized):
        return False

    return True


def infer_technical_category(skill: str) -> str | None:
    """
    Infere uma categoria técnica a partir da competência.

    Retorna None quando não há correspondência suficientemente clara.
    """

    normalized = normalize_skill_key(skill)

    for category, terms in TECHNICAL_CATEGORY_RULES.items():
        normalized_terms = {
            normalize_skill_key(term)
            for term in terms
        }

        if normalized in normalized_terms:
            return category

    return None


def split_heading_and_content(
    line: str,
) -> tuple[str, str]:
    """Separa linhas como 'Technical Skills: Python, Java'."""

    repaired_line = repair_common_encoding(line).strip()

    if ":" not in repaired_line:
        return repaired_line, ""

    heading, content = repaired_line.split(":", maxsplit=1)

    return heading.strip(), content.strip()


# ============================================================
# 3. IDENTIFICAÇÃO DE SEÇÕES
# ============================================================

def find_skill_sections(
    text: str,
) -> list[dict[str, Any]]:
    """Localiza seções explícitas de competências."""

    repaired_text = repair_common_encoding(text)
    lines = repaired_text.splitlines()

    sections = []

    collecting = False
    current_heading = None
    current_lines = []
    section_start_line = None

    def close_section(end_line: int) -> None:
        nonlocal collecting
        nonlocal current_heading
        nonlocal current_lines
        nonlocal section_start_line

        if collecting and current_lines:
            block = "\n".join(current_lines).strip()

            if block:
                sections.append({
                    "heading": current_heading,
                    "text": block,
                    "start_line": section_start_line,
                    "end_line": end_line,
                })

        collecting = False
        current_heading = None
        current_lines = []
        section_start_line = None

    for line_index, line in enumerate(lines):
        stripped_line = line.strip()

        if not stripped_line:
            if collecting:
                current_lines.append("")
            continue

        heading_part, inline_content = split_heading_and_content(
            stripped_line
        )

        normalized_heading = normalize_heading(heading_part)

        if (
            collecting
            and inline_content
            and normalized_heading in CATEGORY_PREFIXES
        ):
            current_lines.append(stripped_line)
            continue

        if normalized_heading in SKILL_SECTION_HEADINGS:
            close_section(line_index - 1)

            collecting = True
            current_heading = heading_part.strip()
            current_lines = []
            section_start_line = line_index

            if inline_content:
                current_lines.append(inline_content)

            continue

        if (
            collecting
            and normalized_heading in STOP_SECTION_HEADINGS
        ):
            close_section(line_index - 1)
            continue

        if collecting:
            current_lines.append(stripped_line)

    close_section(len(lines) - 1)

    return sections


# ============================================================
# 4. LIMPEZA E SEGMENTAÇÃO DE COMPETÊNCIAS
# ============================================================

def remove_category_prefix(candidate: str) -> str:
    """Remove prefixos de categoria, quando reconhecidos."""

    if ":" not in candidate:
        return candidate

    prefix, content = candidate.split(":", maxsplit=1)

    if normalize_heading(prefix) in CATEGORY_PREFIXES:
        return content.strip()

    return candidate


def clean_skill_candidate(
    candidate: str,
) -> str | None:
    """Limpa e valida uma possível competência individual."""

    skill = normalize_skill_display(candidate)

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

    skill = remove_category_prefix(skill)
    skill = normalize_skill_display(skill)

    if not skill:
        return None

    normalized = skill.casefold()

    if normalized in (
        SKILL_SECTION_HEADINGS
        | STOP_SECTION_HEADINGS
        | CATEGORY_PREFIXES
        | GENERIC_SKILL_PLACEHOLDERS
    ):
        return None

    if len(skill) > 100:
        return None

    if len(skill.split()) > 10:
        return None

    if is_skill_noise(skill):
        return None

    for phrase in NON_SKILL_PHRASES:
        if phrase in normalized:
            return None

    if not re.search(r"[A-Za-z0-9+#.]", skill):
        return None

    if not is_valid_skill_candidate(skill):
        return None

    return skill


def merge_known_fragments(
    candidates: list[str],
) -> list[str]:
    """
    Reconstrói competências conhecidas que foram separadas.

    Exemplo:
        Artificial, Intelligence -> Artificial Intelligence

    A junção só ocorre quando a combinação está na lista permitida.
    """

    merged = []
    index = 0

    while index < len(candidates):
        current = candidates[index].strip()
        found = False

        # Tenta combinar até quatro fragmentos consecutivos.
        for size in range(4, 1, -1):
            group = candidates[index:index + size]

            if len(group) != size:
                continue

            combined = " ".join(
                part.strip()
                for part in group
            )

            key = normalize_skill_key(combined)

            if key in KNOWN_FRAGMENT_COMBINATIONS:
                merged.append(KNOWN_FRAGMENT_COMBINATIONS[key])
                index += size
                found = True
                break

        if not found:
            merged.append(current)
            index += 1

    return merged


def split_skill_block_details(
    block: str,
) -> list[dict[str, str | None]]:
    """
    Divide um bloco de competências e preserva categoria/evidência.

    A categoria de origem não determina automaticamente a categoria
    técnica da competência.
    """

    repaired_block = repair_common_encoding(block)

    details: list[dict[str, str | None]] = []

    raw_lines = [
        line.strip()
        for line in repaired_block.splitlines()
        if line.strip()
    ]

    category_prefixes = sorted(
        CATEGORY_PREFIXES,
        key=len,
        reverse=True,
    )

    for original_line in raw_lines:
        heading, inline_content = split_heading_and_content(
            original_line
        )

        normalized_heading = normalize_heading(heading)

        source_category: str | None = None

        if (
            inline_content
            and normalized_heading in CATEGORY_PREFIXES
        ):
            source_category = heading.strip()
            content = inline_content

        else:
            content = original_line

            # Algumas categorias aparecem sem dois-pontos.
            for prefix in category_prefixes:
                match = re.match(
                    rf"^{re.escape(prefix)}\s+(.+)$",
                    original_line,
                    flags=re.IGNORECASE,
                )

                if match:
                    source_category = prefix
                    content = match.group(1).strip()
                    break

        # Em controle de versão, "&" e "and" podem separar produtos.
        if source_category and normalize_heading(source_category) in {
            "version control",
            "version control system",
        }:
            content = re.sub(
                r"\s+(?:&|and)\s+",
                ", ",
                content,
                flags=re.IGNORECASE,
            )

        raw_candidates = re.split(
            r"[•●▪◦\n,;|]+",
            content,
        )

        # Remove fragmentos vazios antes de tentar reconstruir.
        raw_candidates = [
            item.strip()
            for item in raw_candidates
            if item.strip()
        ]

        reconstructed_candidates = merge_known_fragments(
            raw_candidates
        )

        for raw_candidate in reconstructed_candidates:
            cleaned = clean_skill_candidate(raw_candidate)

            if cleaned is None:
                continue

            technical_category = infer_technical_category(cleaned)

            details.append({
                "skill": cleaned,

                # Campo antigo mantido para compatibilidade.
                "category": source_category,

                # Categoria encontrada no currículo.
                "source_category": source_category,

                # Categoria inferida a partir da tecnologia.
                "technical_category": technical_category,

                "evidence_text": original_line,
            })

    return details


def split_skill_block(block: str) -> list[str]:
    """Mantém compatibilidade com a API anterior."""

    return [
        item["skill"]
        for item in split_skill_block_details(block)
        if item["skill"] is not None
    ]


# ============================================================
# 5. EXTRAÇÃO DE ENTIDADES DO NER
# ============================================================

def extract_ner_skill_blocks(
    ner_entities: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Seleciona somente entidades SKILLS previstas pelo NER."""

    if not ner_entities:
        return []

    blocks = []

    for entity in ner_entities:
        label = str(entity.get("label", "")).upper()

        if label != "SKILLS":
            continue

        entity_text = str(entity.get("text", ""))

        if not entity_text.strip():
            continue

        blocks.append({
            "text": entity_text,
            "confidence": float(entity.get("confidence", 0.0)),
            "start": entity.get("start"),
            "end": entity.get("end"),
        })

    return blocks


# ============================================================
# 6. EXTRAÇÃO DE CONTEXTO
# ============================================================

CONTEXT_SECTION_HEADINGS = {
    "projetos aplicados em dados & ia": "project",
    "projetos relevantes": "project", "relevant projects": "project",
    "applied data & ai projects": "project",
    "resumo profissional": "summary", "resumo": "summary",
    "professional summary": "summary", "summary": "summary", "profile": "summary",
    "formação acadêmica & certificações": "education",
    "formação acadêmica e certificações": "education",
    "formação acadêmica": "education", "formacao academica": "education",
    "formação": "education", "education": "education",
    "academic background": "education", "academic qualifications": "education",
    "education & certifications": "education",
    "idiomas": "language", "languages": "language",
    "experience": "experience",
    "professional experience": "experience",
    "work experience": "experience",
    "employment": "experience",
    "employment history": "experience",
    "work history": "experience",
    "internships": "experience",
    "volunteer experience": "experience",
    "experiência": "experience",
    "experiências": "experience",
    "experiência profissional": "experience",
    "experiências profissionais": "experience",
    "experiencia profissional": "experience",
    "estágios": "experience",
    "projects": "project",
    "personal projects": "project",
    "academic projects": "project",
    "professional projects": "project",
    "projetos": "project",
    "projetos pessoais": "project",
    "projetos acadêmicos": "project",
    "projetos profissionais": "project",
}

CONTEXT_STOP_HEADINGS = (
    SKILL_SECTION_HEADINGS
    | STOP_SECTION_HEADINGS
    | {
        "formação",
        "formação acadêmica",
        "educação",
        "habilidades",
        "competências",
        "certificações",
        "idiomas",
        "contato",
        "resumo",
        "objetivo",
        "referências",
    }
)
# Os limites precisam ser os mesmos para habilidades e contexto.
STOP_SECTION_HEADINGS.update(CONTEXT_SECTION_HEADINGS)


def segment_experience_block(
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    """Divide uma experiência profissional em evidências menores."""

    lines = block["text"].splitlines()

    header_lines: list[str] = []
    evidence_blocks: list[dict[str, Any]] = []
    current_lines: list[str] = []

    current_start: int | None = None
    first_bullet_found = False
    pending_blank_after_bullet = False
    collecting_next_header = False

    bullet_pattern = re.compile(
        r"^\s*(?:[•●▪◦]|\*|-)\s+(.+?)\s*$"
    )

    boundary_headings = {
        "role",
        "position",
        "job title",
        "company",
        "employer",
        "environment",
        "responsibilities",
        "declaration",
        "place",
        "date",
    }

    def save_current(end_line: int) -> None:
        nonlocal current_lines, current_start

        evidence_text = " ".join(
            line.strip()
            for line in current_lines
            if line.strip()
        ).strip()

        if evidence_text:
            evidence_blocks.append({
                "text": evidence_text,
                "source": block.get("source", "experience"),
                "heading": block.get("heading"),
                "evidence_type": "responsibility",
                "context_header": "\n".join(header_lines).strip(),
                "start_line": current_start,
                "end_line": end_line,
                "parent_start_line": block.get("start_line"),
                "parent_end_line": block.get("end_line"),
            })

        current_lines = []
        current_start = None

    base_line = block.get("start_line") or 0

    for index, raw_line in enumerate(lines):
        line_number = base_line + index + 1
        line = raw_line.strip()

        if not line:
            if current_lines:
                save_current(line_number - 1)

            if first_bullet_found:
                pending_blank_after_bullet = True

            continue

        heading, _ = split_heading_and_content(line)
        normalized_heading = normalize_heading(heading)

        if first_bullet_found and (
            normalized_heading in CONTEXT_STOP_HEADINGS
            or normalized_heading in boundary_headings
        ):
            if current_lines:
                save_current(line_number - 1)

            break

        match = bullet_pattern.match(raw_line)

        if match:
            if current_lines:
                save_current(line_number - 1)

            first_bullet_found = True
            current_start = line_number
            current_lines = [match.group(1).strip()]

            pending_blank_after_bullet = False
            collecting_next_header = False

        elif not first_bullet_found:
            header_lines.append(line)

        elif pending_blank_after_bullet:
            header_lines = [line]
            pending_blank_after_bullet = False
            collecting_next_header = True

        elif collecting_next_header and not current_lines:
            header_lines.append(line)

        elif current_lines:
            current_lines.append(line)

    if current_lines:
        save_current(
            block.get("end_line") or base_line + len(lines)
        )

    if not evidence_blocks:
        return [{**block, 'text': line.strip(), 'start_line': base_line + index + 1,
                 'end_line': base_line + index + 1}
                for index, line in enumerate(lines) if line.strip()]

    return evidence_blocks


def extract_context_blocks(
    text: str,
) -> list[dict[str, Any]]:
    """Extrai experiências e projetos."""

    blocks: list[dict[str, Any]] = []

    current_source = None
    current_heading = None
    current_lines: list[str] = []
    start_line = None

    def close_block(end_line: int) -> None:
        nonlocal current_source
        nonlocal current_heading
        nonlocal current_lines
        nonlocal start_line

        block_text = "\n".join(current_lines).strip()

        if current_source is not None and block_text:
            block = {
                "text": block_text,
                "source": current_source,
                "heading": current_heading,
                "start_line": start_line,
                "end_line": end_line,
            }

            if current_source == "experience":
                blocks.extend(segment_experience_block(block))
            else:
                # Uma linha/atividade por evidência; não unir projetos, diplomas
                # e níveis de idioma em um único trecho artificial.
                for offset, line in enumerate(current_lines):
                    value = re.sub(r'^\s*[-•●▪◦*]\s+', '', line).strip()
                    if value:
                        blocks.append({**block, 'text': value,
                                       'start_line': (start_line or 0) + offset + 1,
                                       'end_line': (start_line or 0) + offset + 1})

        current_source = None
        current_heading = None
        current_lines = []
        start_line = None

    lines = text.splitlines()

    for line_number, line in enumerate(lines, start=1):
        heading, inline_content = split_heading_and_content(line)
        normalized = normalize_heading(heading)

        if normalized in CONTEXT_SECTION_HEADINGS:
            close_block(line_number - 1)

            current_source = CONTEXT_SECTION_HEADINGS[normalized]
            current_heading = heading.strip()
            start_line = line_number

            if inline_content:
                current_lines.append(inline_content)

        elif normalized in CONTEXT_STOP_HEADINGS:
            close_block(line_number - 1)

        elif current_source is not None:
            current_lines.append(line)

    close_block(len(lines))

    return blocks


# ============================================================
# 7. PREPARAÇÃO DOS INPUTS SEMÂNTICOS
# ============================================================

def prepare_semantic_inputs(
    skill_details: list[dict[str, Any]],
    context_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Organiza os textos que serão enviados ao modelo de embeddings."""

    inputs = []

    for item in skill_details:
        inputs.append({
            "text": item["skill"],
            "source": "skill",
            "extraction_sources": item["sources"],
            "evidence": item["evidence"],
            "categories": item.get("categories", []),
            "source_categories": item.get("source_categories", []),
            "technical_category": item.get("technical_category"),
        })

    for block in context_blocks:
        inputs.append(dict(block))

    return inputs


# ============================================================
# 8. EXTRAÇÃO HÍBRIDA
# ============================================================

def extract_skills(
    text: str,
    ner_entities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Executa a extração híbrida de competências.

    Competências encontradas em mais de uma fonte são mantidas apenas
    uma vez, mas registram todas as suas origens.
    """

    sections = find_skill_sections(text)
    ner_blocks = extract_ner_skill_blocks(ner_entities)

    candidates: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def add_candidate(
        skill: str,
        source: str,
        evidence: str,
        confidence: float | None,
        category: str | None = None,
        technical_category: str | None = None,
    ) -> None:
        """Valida, normaliza e adiciona uma competência."""

        cleaned_skill = clean_skill_candidate(skill)

        if cleaned_skill is None:
            return

        key = normalize_skill_key(cleaned_skill)

        if not key:
            return

        if key not in candidates:
            candidates[key] = {
                "skill": cleaned_skill,
                "normalized": key,
                "sources": [],
                "evidence": [],

                # Campo antigo mantido para compatibilidade.
                "categories": [],

                # Categorias de origem do currículo.
                "source_categories": [],

                # Categoria técnica inferida.
                "technical_category": (
                    technical_category
                    or infer_technical_category(cleaned_skill)
                ),

                "ner_confidence": None,
            }

        record = candidates[key]

        if source not in record["sources"]:
            record["sources"].append(source)

        shortened_evidence = evidence[:300]

        if shortened_evidence not in record["evidence"]:
            record["evidence"].append(shortened_evidence)

        if category:
            if category not in record["categories"]:
                record["categories"].append(category)

            if category not in record["source_categories"]:
                record["source_categories"].append(category)

        if (
            technical_category
            and record["technical_category"] is None
        ):
            record["technical_category"] = technical_category

        if confidence is not None:
            previous_confidence = record["ner_confidence"]

            if (
                previous_confidence is None
                or confidence > previous_confidence
            ):
                record["ner_confidence"] = confidence

    # Primeiro: competências encontradas em seções explícitas.
    for section in sections:
        section_skills = split_skill_block_details(section["text"])

        for item in section_skills:
            add_candidate(
                skill=item["skill"] or "",
                source="section",
                evidence=item["evidence_text"] or section["text"],
                confidence=None,
                category=item["source_category"],
                technical_category=item["technical_category"],
            )

    # Depois: competências encontradas pelo NER.
    for block in ner_blocks:
        block_skills = split_skill_block_details(block["text"])

        for item in block_skills:
            add_candidate(
                skill=item["skill"] or "",
                source="ner",
                evidence=item["evidence_text"] or block["text"],
                confidence=block["confidence"],
                category=item["source_category"],
                technical_category=item["technical_category"],
            )

    skill_details = list(candidates.values())

    context_blocks = extract_context_blocks(text)

    semantic_inputs = prepare_semantic_inputs(
        skill_details=skill_details,
        context_blocks=context_blocks,
    )

    return {
        "skills": [
            item["skill"]
            for item in skill_details
        ],
        "skill_details": skill_details,
        "sections_found": sections,
        "ner_skill_blocks": ner_blocks,
        "context_blocks": context_blocks,
        "semantic_inputs": semantic_inputs,
        "statistics": {
            "sections_found": len(sections),
            "ner_blocks_found": len(ner_blocks),
            "unique_skills": len(skill_details),
            "skills_from_section": sum(
                1
                for item in skill_details
                if "section" in item["sources"]
            ),
            "skills_from_ner": sum(
                1
                for item in skill_details
                if "ner" in item["sources"]
            ),
            "skills_confirmed_by_both": sum(
                1
                for item in skill_details
                if {"section", "ner"}.issubset(item["sources"])
            ),
        },
    }


# ============================================================
# 9. EXECUÇÃO PELO TERMINAL
# ============================================================

def parse_args() -> argparse.Namespace:
    """Argumentos da linha de comando."""

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Arquivo TXT contendo o currículo.",
    )

    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("models/ner/augmented/best_model"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/skills_extraction.json"),
    )

    parser.add_argument(
        "--minimum-ner-confidence",
        type=float,
        default=0.0,
    )

    return parser.parse_args()


def main() -> None:
    """Executa NER e extração híbrida em um currículo."""

    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            f"Currículo não encontrado: {args.input}"
        )

    text = args.input.read_text(encoding="utf-8")

    # Importação local evita carregar Torch quando apenas as funções
    # de segmentação são utilizadas nos testes.
    from src.nlp.inference import ResumeNERPredictor

    predictor = ResumeNERPredictor(
        model_directory=args.model_dir
    )

    ner_result = predictor.predict(
        text=text,
        minimum_confidence=args.minimum_ner_confidence,
    )

    hybrid_result = extract_skills(
        text=text,
        ner_entities=ner_result["entities"],
    )

    complete_result = {
        "input_file": str(args.input),
        "ner_entity_count": ner_result["entity_count"],
        "ner_entities": ner_result["entities"],
        "hybrid_skills": hybrid_result,
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
        f"Skills encontradas: {len(hybrid_result['skills'])}"
    )

    for skill in hybrid_result["skills"]:
        print(f"- {skill}")

    print(f"\nResultado salvo em: {args.output}")


if __name__ == "__main__":
    main()
