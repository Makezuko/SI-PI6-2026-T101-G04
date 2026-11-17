import io
from pathlib import Path
import re
from typing import Any

from src.nlp.skills_extractor import (
    extract_skills,
    repair_common_encoding,
)

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
    """Usa o mesmo caminho de segmentacao do pipeline documental."""
    from src.nlp.skills_extractor import extract_context_blocks
    return [block for block in extract_context_blocks(text) if block['source'] == 'education']


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
    if candidate_name and len(candidate_name.split()) >= 2 and candidate_name.lower() != "candidato":
        escaped_name = re.escape(candidate_name.strip())
        anonymized = re.sub(rf"^{escaped_name}\s*$", "[NOME OCULTO]", anonymized, flags=re.IGNORECASE | re.MULTILINE)

    anonymized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[E-MAIL OCULTO]", anonymized)
    def mask_phone(match):
        value = match.group(0)
        if re.fullmatch(r'(?:19|20)\d{2}\s*-\s*(?:19|20)\d{2}', value.strip()):
            return value
        return '[TELEFONE OCULTO]'
    anonymized = re.sub(r"(?<![\w.])(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,3}\)?[ -]?)?\d{4,5}[ -]?\d{4}(?![\w.])", mask_phone, anonymized)
    anonymized = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF OCULTO]", anonymized)
    anonymized = re.sub(r"\bRG:?\s*\d{1,2}\.?\d{3}\.?\d{3}-?[\dX]\b", "[RG OCULTO]", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"\bCEP:?\s*\d{5}-?\d{3}\b", "[CEP OCULTO]", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"(?:https?://|www\.)\S+", "[LINK OCULTO]", anonymized, flags=re.IGNORECASE)
    anonymized = re.sub(r"\b(?:linkedin\.com|github\.com)/\S+", "[LINK OCULTO]", anonymized, flags=re.IGNORECASE)

    anonymized = re.sub(r"(?i)\b(?:foto(?:\s*3x4)?|photo|picture)\s*:\s*(?:\[[^\]\n]+\]|\S+)", "[FOTO OCULTA]", anonymized)
    anonymized = re.sub(r"(?i)\[\s*(?:foto(?:\s*3x4)?|photo|picture|imagem|image)\s*\]", "[FOTO OCULTA]", anonymized)

    anonymized = re.sub(r"(?i)\b(?:gênero|genero|sexo|gender|sex)\s*:\s*[A-Za-zÀ-ÿ/-]+", "[GÊNERO OCULTO]", anonymized)
    anonymized = re.sub(r"(?i)\b(?:pronomes?|pronouns?)\s*:\s*[A-Za-zÀ-ÿ/-]+", "[PRONOMES OCULTOS]", anonymized)
    anonymized = re.sub(r"(?i)^\s*(?:ele/dele|ela/dela|elu/delu|he/him|she/her|they/them)\s*$", "[PRONOMES OCULTOS]", anonymized, flags=re.MULTILINE)

    anonymized = re.sub(r"(?i)\b(?:idade|age)\s*:\s*\d{1,2}(?:[ \t]*(?:anos?(?:\s+de\s+idade)?|years?(?:\s+old)?))?", "[IDADE OCULTA]", anonymized)
    anonymized = re.sub(r"(?i)\b\d{1,2}[ \t]*(?:anos(?:\s+de\s+idade)?|years?(?:\s+old)?)\b(?!\s+(?:de\s+(?:experiência|experiencia|atuação|atuacao|carreira|mercado|prática|pratica)|com\b|em\b))", "[IDADE OCULTA]", anonymized)
    anonymized = re.sub(r"(?i)\b(?:data\s+de\s+nascimento|data\s+nasc\.?|nascimento|nasc\.?|date\s+of\s+birth|dob)\s*:\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "[DATA DE NASCIMENTO OCULTA]", anonymized)
    anonymized = re.sub(r"(?i)\b(?:nascido|nascida|born)\s+(?:em|on)?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "[DATA DE NASCIMENTO OCULTA]", anonymized)

    anonymized = re.sub(r"(?i)\b(?:estado\s+civil|marital\s+status)\s*:\s*[A-Za-zÀ-ÿ\s/-]+(?=[\n,;]|$)", "[ESTADO CIVIL OCULTO]", anonymized)
    anonymized = re.sub(r"(?i)\b(?:nacionalidade|nationality|naturalidade)\s*:\s*[A-Za-zÀ-ÿ\s/-]+(?=[\n,;]|$)", "[NACIONALIDADE OCULTA]", anonymized)
    anonymized = re.sub(r"(?i)\b(?:solteir[oa]|casad[oa]|divorciad[oa]|viúv[oa]|união\s+estável)\b", "[ESTADO CIVIL OCULTO]", anonymized)
    anonymized = re.sub(r"(?i)\b(?:brasileir[oa]|brasileir[oa]s)\b", "[NACIONALIDADE OCULTA]", anonymized)

    anonymized = re.sub(r"(?i)(?<!\bIP\s)(?<!\bMAC\s)(?<!\bMemory\s)\b(?:endereço|endereco|address)\s*:\s*[^\n]+", "[ENDEREÇO OCULTO]", anonymized)
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
    from src.data.privacy import latest_role
    experience_summary = latest_role(text, ner_entities)

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
