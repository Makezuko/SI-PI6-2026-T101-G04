"""Proteção de texto na apresentação; não modifica resultados persistidos."""

import re
from src.data.privacy import anonymize_for_analysis, uploaded_name_entities, personal_spans


def candidate_text(value, candidate):
    value = str(value or "")
    if candidate.get("status") == "Aprovado":
        return value
    raw = candidate.get("raw_text", "")
    entities = uploaded_name_entities(raw, candidate.get("anonymized_text"))
    hidden = [raw[a:b] for a, b in personal_spans(raw, entities)]
    # O nome já conhecido pela camada de apresentação também deve permanecer oculto.
    name = candidate.get("real_name")
    if name:
        hidden.append(name)
    for fragment in sorted(set(hidden), key=len, reverse=True):
        if fragment.strip():
            value = re.sub(
                r"(?<!\w)" + re.escape(fragment) + r"(?!\w)",
                "[DADO PESSOAL OCULTO]",
                value,
                flags=re.IGNORECASE,
            )
    return anonymize_for_analysis(value, [])
