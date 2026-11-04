import io
from pathlib import Path
import re
from typing import Any

from src.nlp.skills_extractor import (
    extract_skills,
    normalize_heading,
    repair_common_encoding,
    split_heading_and_content,
)

EDUCATION_HEADINGS = {
    "education": "education",
    "academic background": "education",
    "academic qualifications": "education",
    "educational qualification": "education",
    "formação": "education",
    "formação acadêmica": "education",
    "formacao academica": "education",
    "educação": "education",
    "educacao": "education",
}

EDUCATION_STOP_HEADINGS = {
    "skills",
    "technical skills",
    "experience",
    "professional experience",
    "work experience",
    "projects",
    "languages",
    "certifications",
    "experiência",
    "projetos",
    "habilidades",
}


def extract_pdf_text(source: Any) -> str:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo não encontrado: {source}")
        stream = path.open("rb")
        close_stream = True
    elif hasattr(source, "read"):
        data = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
        stream = io.BytesIO(data)
        close_stream = False
    elif isinstance(source, bytes):
        stream = io.BytesIO(source)
        close_stream = False
    else:
        raise TypeError("Entrada deve ser caminho, bytes ou objeto de arquivo.")

    pages = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(stream)
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    except Exception:
        if hasattr(stream, "seek"):
            stream.seek(0)
        from pdfminer.high_level import extract_text as miner_extract
        text = miner_extract(stream) or ""
        if text.strip():
            pages.append(text)
    finally:
        if close_stream:
            stream.close()

    full_text = "\n".join(pages).strip()
    if not full_text:
        raise ValueError("Não foi possível extrair texto legível do PDF.")

    repaired = repair_common_encoding(full_text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in repaired.splitlines()]
    clean_lines = []
    for line in lines:
        if line or (clean_lines and clean_lines[-1] != ""):
            clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def extract_education_blocks(text: str) -> list[dict[str, Any]]:
    blocks = []
    current_source = None
    current_heading = None
    current_lines = []
    start_line = None

    def close_block(end_line: int):
        nonlocal current_source, current_heading, current_lines, start_line
        block_text = "\n".join(current_lines).strip()
        if current_source is not None and block_text:
            blocks.append({
                "text": block_text,
                "source": current_source,
                "heading": current_heading,
                "start_line": start_line,
                "end_line": end_line,
            })
        current_source = None
        current_heading = None
        current_lines = []
        start_line = None

    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        heading, inline_content = split_heading_and_content(line)
        normalized = normalize_heading(heading)

        if normalized in EDUCATION_HEADINGS:
            close_block(line_number - 1)
            current_source = EDUCATION_HEADINGS[normalized]
            current_heading = heading
            start_line = line_number
            if inline_content:
                current_lines.append(inline_content)
        elif normalized in EDUCATION_STOP_HEADINGS:
            close_block(line_number - 1)
        elif current_source is not None:
            current_lines.append(line)

    close_block(len(lines))
    return blocks


def extract_contact_info(text: str) -> dict[str, str | None]:
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    phone_match = re.search(
        r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,3}\)?[\s-]?)?\d{4,5}[\s-]?\d{4}\b",
        text,
    )
    return {
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0).strip() if phone_match else None,
    }


def anonymize_resume_text(text: str, candidate_name: str | None = None) -> str:
    anonymized = text
    if candidate_name and candidate_name.strip() and candidate_name.lower() != "candidato":
        escaped_name = re.escape(candidate_name.strip())
        anonymized = re.sub(rf"\b{escaped_name}\b", "[NOME OCULTO]", anonymized, flags=re.IGNORECASE)

    anonymized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[E-MAIL OCULTO]", anonymized)
    anonymized = re.sub(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,3}\)?[\s-]?)?\d{4,5}[\s-]?\d{4}\b", "[TELEFONE OCULTO]", anonymized)
    anonymized = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF OCULTO]", anonymized)
    anonymized = re.sub(r"(?:https?://|www\.)\S+", "[LINK OCULTO]", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"\b(?:linkedin\.com|github\.com)/\S+", "[LINK OCULTO]", anonymized, flags=re.IGNORECASE)
    return anonymized


def parse_resume_pdf(
    source: Any,
    filename: str = "",
    model_dir: Path | str | None = None,
) -> dict[str, Any]:
    text = extract_pdf_text(source)

    ner_entities = []
    if model_dir is not None:
        target_dir = Path(model_dir)
        if target_dir.is_dir():
            from src.nlp.inference import ResumeNERPredictor
            predictor = ResumeNERPredictor(model_directory=target_dir)
            prediction = predictor.predict(text=text, minimum_confidence=0.0)
            ner_entities = prediction.get("entities", [])

    hybrid_extraction = extract_skills(text=text, ner_entities=ner_entities)
    education_blocks = extract_education_blocks(text)
    contact = extract_contact_info(text)

    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:5]
    guessed_name = None
    for entity in ner_entities:
        if entity.get("label") == "Name" and entity.get("text"):
            guessed_name = entity["text"].strip()
            break
    if not guessed_name and first_lines:
        first = first_lines[0]
        if len(first.split()) <= 4 and re.search(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s]+$", first):
            guessed_name = first.title()
    if not guessed_name and filename:
        clean_file = Path(filename).stem.replace("_", " ").replace("-", " ")
        guessed_name = clean_file.title()

    initials = "".join(part[0] for part in (guessed_name or "CV").split()[:2]).upper()

    education_summary = education_blocks[0]["text"].splitlines()[0] if education_blocks else "Não especificada"
    experience_summary = hybrid_extraction["context_blocks"][0]["text"].splitlines()[0] if hybrid_extraction.get("context_blocks") else "Não especificada"

    anonymized = anonymize_resume_text(text, guessed_name)

    return {
        "filename": Path(filename).name if filename else "curriculo.pdf",
        "name": guessed_name or "Candidato",
        "initials": initials,
        "email": contact["email"] or "contato@candidato.com",
        "phone": contact["phone"] or "Telefone não informado",
        "education": education_summary,
        "education_blocks": education_blocks,
        "last_role": experience_summary,
        "experience_blocks": hybrid_extraction.get("context_blocks", []),
        "skills": hybrid_extraction.get("skills", []),
        "skill_details": hybrid_extraction.get("skill_details", []),
        "semantic_inputs": hybrid_extraction.get("semantic_inputs", []),
        "raw_text": text,
        "anonymized_text": anonymized,
        "text_preview": text[:500],
    }
