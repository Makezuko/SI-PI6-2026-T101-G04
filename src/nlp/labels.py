"""
Definição centralizada dos rótulos utilizados pelo modelo de NER.

O dataset contém entidades em formato de spans de caracteres:

    {
        "start": 10,
        "end": 25,
        "label": "College Name"
    }

Para treinar um Transformer para classificação de tokens, esses rótulos são
convertidos para o padrão BIO:

B = Beginning: primeiro token da entidade.
I = Inside: continuação da entidade.
O = Outside: token que não pertence a uma entidade.
"""


# Rótulos válidos encontrados no dataset Dataturks após a limpeza.
ENTITY_LABELS = [
    "College Name",
    "Companies worked at",
    "Degree",
    "Designation",
    "Email Address",
    "Graduation Year",
    "Location",
    "Name",
    "Skills",
    "Years of Experience",
]


def normalize_entity_label(label: str) -> str:
    """
    Converte o nome original para o formato utilizado nos rótulos BIO.

    Exemplos:
        "College Name" -> "COLLEGE_NAME"
        "Email Address" -> "EMAIL_ADDRESS"
    """
    return "_".join(
        label.strip().upper().split()
    )


# O primeiro rótulo é sempre O.
BIO_LABELS = ["O"]

# Para cada entidade, criamos uma versão B e uma versão I.
for entity_label in ENTITY_LABELS:
    normalized_label = normalize_entity_label(
        entity_label
    )

    BIO_LABELS.append(
        f"B-{normalized_label}"
    )

    BIO_LABELS.append(
        f"I-{normalized_label}"
    )


# Mapeamento utilizado pelo modelo:
# nome do rótulo -> número.
LABEL2ID = {
    label: index
    for index, label in enumerate(BIO_LABELS)
}


# Mapeamento inverso:
# número -> nome do rótulo.
ID2LABEL = {
    index: label
    for label, index in LABEL2ID.items()
}