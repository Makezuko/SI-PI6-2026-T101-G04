"""Redação conservadora por offsets do texto original; sem regras globais NER."""

import re

from src.data.clean import anonymize_resume_text


def uploaded_name_entities(text, anonymized_text):
    """Reutiliza nome já ocultado no cabeçalho pelo upload, sem adivinhar pelo arquivo."""
    original_lines = [line.strip() for line in text.splitlines() if line.strip()]
    saved_lines = [line.strip() for line in (anonymized_text or "").splitlines() if line.strip()]
    if (
        not original_lines
        or not saved_lines
        or saved_lines[0] not in {"[NOME OCULTO]", "[DADO PESSOAL OCULTO]"}
    ):
        return []
    name = original_lines[0]
    if not re.fullmatch(r"[^\W\d_]+(?:[ \t]+[^\W\d_]+){1,5}", name):
        return []
    start = text.index(name)
    return [dict(label="NAME", text=name, start=start, end=start + len(name))]


def valid_entity(text, entity):
    start, end = entity.get("start"), entity.get("end")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(text)
        or text[start:end] != entity.get("text")
    ):
        return False
    # Nunca expandir um token parcial para a palavra que o contém.
    return not (
        (start and text[start - 1].isalnum() and text[start].isalnum())
        or (end < len(text) and text[end - 1].isalnum() and text[end].isalnum())
    )


def personal_spans(text, entities):
    spans = []
    confirmed_names = set()
    for entity in entities:
        if not valid_entity(text, entity):
            continue
        value, label = entity["text"], entity["label"]
        # Nome de um só token/fragmento é ambíguo, sobretudo fora do idioma NER.
        if label == "NAME" and len(re.findall(r"[^\W\d_]{2,}", value)) >= 2:
            spans.append((entity["start"], entity["end"]))
            confirmed_names.add(value)
        elif label == "EMAIL_ADDRESS" and "@" in value:
            spans.append((entity["start"], entity["end"]))
        elif label == "LOCATION":
            prefix = text[text.rfind("\n", 0, entity["start"]) + 1 : entity["start"]]
            if re.fullmatch(r"\s*(?:location|localização|endereço|address)\s*:\s*", prefix, re.I):
                spans.append((entity["start"], entity["end"]))
    # Repete apenas nomes completos confirmados, com fronteiras. Nunca propaga
    # tokens parciais ou nomes inferidos de uma palavra para o restante do texto.
    for name in confirmed_names:
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(part) for part in name.split()) + r"(?!\w)"
        spans.extend((match.start(), match.end()) for match in re.finditer(pattern, text, re.I))
    merged = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def anonymize_for_analysis(text, entities):
    for start, end in reversed(personal_spans(text, entities)):
        text = text[:start] + "[DADO PESSOAL OCULTO]" + text[end:]
    return anonymize_resume_text(text)


def sanitize_text_for_embedding(text):
    cleaned = re.sub(r"\[[^\[\]]*OCULT[OA]S?\]", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[,;:\s*•-]+\s*$", "", cleaned)
    cleaned = re.sub(r"^\s*[,;:\s*•-]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def sanitize_semantic_inputs(inputs):
    sanitized = []
    for item in inputs:
        new_item = dict(item)
        if "text" in new_item:
            cleaned = sanitize_text_for_embedding(new_item["text"])
            if cleaned:
                new_item["text"] = cleaned
                sanitized.append(new_item)
        else:
            sanitized.append(new_item)
    return sanitized


def latest_role(text, entities):
    """Exige cargo NER em cabeçalho de experiência e intervalo temporal explícito."""
    from src.nlp.skills_extractor import extract_context_blocks

    blocks = [
        block
        for block in extract_context_blocks(text)
        if block["source"] == "experience" and block.get("context_header")
    ]
    original_lines = text.splitlines()
    roles = []
    undated = False
    for entity in entities:
        if entity.get("label") != "DESIGNATION" or not valid_entity(text, entity):
            continue
        role = entity["text"].strip()
        if (
            not role
            or "\n" in role
            or len(role.split()) > 10
            or re.match(
                r"^(?:[-•]|helping\b|built\b|developed\b|responsible\b|ajudando\b|realizando\b|responsável\b|atendimento\b)",
                role,
                re.I,
            )
        ):
            continue
        entity_line = text.count("\n", 0, entity["start"])
        for block in blocks:
            lines = block["context_header"].splitlines()
            # A entidade deve pertencer a esta ocorrência do cabeçalho no
            # original, não apenas ter texto igual a um cargo em outro local.
            lower = block.get("parent_start_line", 1) - 1
            upper = min(block["start_line"] - 1, len(original_lines))
            header_starts = [
                start
                for start in range(lower, upper - len(lines) + 1)
                if [line.strip() for line in original_lines[start : start + len(lines)]] == lines
            ]
            for i, line in enumerate(lines):
                if line.strip() != role or not any(
                    start + i == entity_line for start in header_starts
                ):
                    continue
                dates = lines[max(0, i - 1) : i + 3]
                matches = [
                    match
                    for date in dates
                    if (
                        match := re.fullmatch(
                            r"\s*((?:19|20)\d{2})\s*[-–—]\s*(present|current|atual|(?:19|20)\d{2})\s*",
                            date,
                            re.I,
                        )
                    )
                ]
                if len(matches) == 1:
                    match = matches[0]
                    end = 9999 if not match[2].isdigit() else int(match[2])
                    if end >= int(match[1]):
                        roles.append(((end, int(match[1])), role))
                    else:
                        undated = True
                else:
                    undated = True
    if not roles or undated:
        return "Não identificado"
    newest = max(key for key, _ in roles)
    candidates = {role for key, role in roles if key == newest}
    return candidates.pop() if len(candidates) == 1 else "Não identificado"
