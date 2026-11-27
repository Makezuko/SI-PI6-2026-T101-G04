"""Regras documentais limitadas e auditáveis; não usa similaridade como decisão."""

import re
import unicodedata


def fold(value):
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )


ALIASES = {
    "python": ("python",),
    "sql": ("sql",),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "git": ("git",),
    "docker": ("docker",),
    "postgresql": ("postgresql", "postgres", "postgre sql"),
    "mysql": ("mysql", "my sql"),
    "oracle": ("oracle",),
    "react": ("react", "react.js", "reactjs"),
    "next.js": ("next.js", "nextjs"),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "java": ("java",),
    "flask": ("flask",),
    "fastapi": ("fastapi",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "tensorflow": ("tensorflow",),
    "pytorch": ("pytorch",),
    "power bi": ("power bi",),
}
LANGUAGES = {
    "ingles": ("ingles", "english"),
    "espanhol": ("espanhol", "spanish"),
    "portugues": ("portugues", "portuguese"),
    "frances": ("frances", "french"),
}
LEVELS = {
    "basico": 1,
    "basic": 1,
    "a1": 1,
    "a2": 1,
    "intermediario": 2,
    "intermediate": 2,
    "b1": 2,
    "b2": 2,
    "avancado": 3,
    "advanced": 3,
    "c1": 3,
    "fluente": 4,
    "fluent": 4,
    "c2": 4,
    "nativo": 5,
    "native": 5,
}


def literal(term, text):
    return bool(re.search(r"(?<![\w+#.])" + re.escape(fold(term)) + r"(?![\w+#]|\.\w)", fold(text)))


def canonical(term):
    term = fold(term.strip())
    return next((key for key, aliases in ALIASES.items() if term in aliases), None)


def mentions(term, text):
    return any(literal(alias, text) for alias in ALIASES.get(term, (term,)))


def unsafe(text):
    # Preferir revisão a confirmar menções negadas, hipotéticas ou de terceiros.
    return bool(
        re.search(
            r"\b(?:nao|sem|no|not|never|without|learning|aprendendo|estudando|"
            r"pretendo|planej\w*|planned|would|will|desejo|futur\w*|"
            r"equipe|team|colega\w*|colleague\w*|familiar|curso|course|tutorial)\b",
            fold(text),
        )
    )


def activity_mentions(kind, terms, clause):
    """Liga verbo, objeto e tecnologia; evita coocorrência dispersa na oração."""
    names = sorted(
        {alias for aliases in ALIASES.values() for alias in aliases}, key=len, reverse=True
    )
    technology = "(?:" + "|".join(re.escape(name) for name in names) + ")"
    technologies = technology + r"(?:\s*(?:,|\be\b|\band\b|&)\s*" + technology + ")*"
    verb = r"\b(?:desenvolvi|desenvolveu|desenvolvemos|implementei|implementou|criei|criou|developed|built|implemented|created)\s+"
    article = r"(?:(?:uma?|as?|an?|the|some)\s+)?"
    preposition = r"\s+(?:em|com|in|using|with|usando)\s+"
    objects = r"apis?(?:\s+rest(?:ful)?)?"
    if kind == "use":
        objects = r"(?:apis?(?:\s+rest(?:ful)?)?|pipelines?|servicos?|services?|sistemas?|systems?|aplicacoes|applications|modelos|models)"
    prefixes = [verb + article + objects + preposition]
    if kind == "use":
        prefixes.append(
            r"\b(?:utilizei|utilizou|usei|usamos|used)\s+"
            + article
            + r"(?:(?:biblioteca|linguagem|library|language|ferramenta|tool)\s+)?"
        )
    for prefix in prefixes:
        for match in re.finditer(prefix + "(" + technologies + r")(?![\w+#])", fold(clause)):
            if all(mentions(term, match[1]) for term in terms):
                return True
    return False


def infer_condition(text):
    """Só padrões textuais pequenos; operadores compostos exigem edição explícita."""
    value = fold(text.strip().rstrip("."))
    simple = re.sub(
        r"^(?:conhecimento(?:s)?(?: basico(?:s)?)? (?:em|de)|knowledge of|"
        r"familiaridade com|habilidade(?:s)? em)\s+",
        "",
        value,
    )
    if canonical(simple):
        return {"kind": "all", "terms": [canonical(simple)]}
    usage = re.fullmatch(r"(?:experiencia|experience) (?:com|em|with|in) (.+)", value)
    if usage and canonical(usage[1]):
        return {"kind": "use", "terms": [canonical(usage[1])]}
    activity = re.fullmatch(
        r"(?:desenvolver|desenvolvimento de|develop|build) apis? (?:em|com|in|using|with) (.+)",
        value,
    )
    if activity and canonical(activity[1]):
        return {"kind": "api", "terms": [canonical(activity[1])]}
    for language, aliases in LANGUAGES.items():
        for level in LEVELS:
            if any(value in (f"{alias} {level}", f"{alias} - {level}") for alias in aliases):
                return {"kind": "language", "terms": [language], "level": level}
    # Formação é explícita e delimitada: não inferir área ou conclusão por keyword.
    education = re.fullmatch(
        r"(?:graduacao|bacharelado|formacao superior|bachelor(?:s)?(?: degree)?) (?:em|in) (.+?)(?: (concluid[oa]|completed|em andamento|in progress))?",
        value,
    )
    if education:
        return {
            "kind": "education",
            "terms": [education[1]],
            "completion": "in_progress"
            if education[2] in ("em andamento", "in progress")
            else "completed",
        }
    return None


def condition_from_form(mode, terms):
    if not mode or mode == "auto":
        return None
    terms = [term.strip() for term in terms.split(";") if term.strip()]
    if not terms or len(terms) > 12 or any(len(term) > 120 for term in terms):
        raise ValueError(
            "Informe os termos da condição, separados por ponto e vírgula (máximo 12)."
        )
    if mode in {"all", "any", "api", "use"}:
        normalized = [canonical(term) for term in terms]
        if not all(normalized):
            raise ValueError(
                "Tecnologia sem regra validada. Use avaliação conservadora ou revise os termos."
            )
        return {"kind": mode, "terms": normalized}
    if mode.startswith("language:"):
        level = mode.split(":", 1)[1]
        language = next(
            (key for key, aliases in LANGUAGES.items() if fold(terms[0]) in aliases), None
        )
        if level not in LEVELS or language is None or len(terms) != 1:
            raise ValueError(
                "Informe um idioma reconhecido: inglês, espanhol, português ou francês."
            )
        return {"kind": "language", "terms": [language], "level": level}
    if mode in {"education:completed", "education:in_progress"} and len(terms) == 1:
        return {"kind": "education", "terms": terms, "completion": mode.split(":")[1]}
    raise ValueError("Condição de avaliação inválida.")


def validate_condition(condition):
    if condition is None:
        return None
    if (
        not isinstance(condition, dict)
        or not isinstance(condition.get("terms"), list)
        or any(not isinstance(term, str) for term in condition["terms"])
    ):
        raise ValueError("Condição estruturada inválida; revise o requisito.")
    kind = condition.get("kind")
    mode = kind
    if kind == "language":
        mode += ":" + str(condition.get("level"))
    elif kind == "education":
        mode += ":" + str(condition.get("completion"))
    return condition_from_form(mode, ";".join(condition["terms"]))


def suggest_condition(text):
    # Sugestões são apenas para a edição; jamais são aplicadas pelo avaliador.
    value = fold(text.strip().rstrip("."))
    for separator, kind in [(" e ", "all"), (" and ", "all"), (" ou ", "any"), (" or ", "any")]:
        if separator in value:
            terms = [part.strip() for part in re.split(r",|" + separator, value) if part.strip()]
            if len(terms) > 1 and all(canonical(term) for term in terms):
                return {"kind": kind, "terms": [canonical(term) for term in terms]}
    return infer_condition(text)


def evaluate_condition(condition, entries):
    """Retorna evidências literais suficientes e rastreio sem texto pessoal extra."""
    kind, terms = condition["kind"], condition["terms"]
    eligible = [
        e
        for e in entries
        if e.get("source") in {"skill", "experience", "project", "summary", "education", "language"}
    ]
    valid = []
    rejected = 0
    for entry in eligible:
        # A extração pode normalizar uma habilidade; a negação deve ser verificada
        # também no trecho original que gerou essa habilidade.
        original = entry.get("evidence", entry.get("metadata", {}).get("evidence", []))
        texts = [entry["text"]] + (original if isinstance(original, list) else [])
        if any(unsafe(t) for t in texts):
            rejected += 1
        else:
            valid.append(entry)
    hits, found = [], set()
    for entry in valid:
        text = entry["text"]
        if kind in {"all", "any", "api", "use"}:
            matched = {term for term in terms if mentions(term, text)}
            if kind in {"api", "use"}:
                if entry["source"] not in {"experience", "project"}:
                    continue
                # Todos os elementos da atividade na MESMA oração, com verbo
                # de execução explícito; não combinar palavras de fontes distintas.
                clauses = re.split(r"[;.!?](?:\s|$)", text)
                matched = set()
                for clause in clauses:
                    if activity_mentions(kind, terms, clause):
                        matched = set(terms)
                        break
            if matched:
                found.update(matched)
                hits.append(entry)
        elif kind == "language" and entry["source"] == "language":
            if not any(literal(alias, text) for alias in LANGUAGES.get(terms[0], ())):
                continue
            # Um idioma por linha/oração para não atribuir o nível de outro.
            other = [
                key
                for key, aliases in LANGUAGES.items()
                if key != terms[0] and any(literal(alias, text) for alias in aliases)
            ]
            levels = {value for label, value in LEVELS.items() if literal(label, text)}
            if not other and len(levels) == 1 and min(levels) >= LEVELS[condition["level"]]:
                hits.append(entry)
                found.update(terms)
        elif kind == "education" and entry["source"] == "education":
            value = fold(text)
            degree = re.search(
                r"\b(?:graduacao|bacharelado|bachelor|bachelors|licenciatura|tecnologo)\b", value
            )
            progress = re.search(r"\b(?:cursando|em andamento|in progress|studying)\b", value)
            completed = re.search(
                r"\b(?:concluido|concluida|completed|graduated|formado|formada)\b", value
            )
            status = (
                progress if condition["completion"] == "in_progress" else completed and not progress
            )
            if degree and status and literal(terms[0], text):
                hits.append(entry)
                found.update(terms)
    passed = bool(found) if kind == "any" else set(terms).issubset(found)
    trace = {
        "rule": kind,
        "eligible_entries": len(eligible),
        "rejected_contexts": rejected,
        "matched_terms": sorted(found),
        "missing_terms": sorted(set(terms) - found),
    }
    reason = (
        f"Regra {kind}: evidência literal suficiente para {', '.join(sorted(found))}."
        if passed
        else f"Regra {kind}: evidência insuficiente ou ambígua; falta confirmar {', '.join(trace['missing_terms'])}."
    )
    return passed, hits if passed else [], reason, trace
