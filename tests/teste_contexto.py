from src.nlp.skills_extractor import extract_skills

curriculo = """
TECHNICAL SKILLS
Python, SQL

PROFESSIONAL EXPERIENCE
Data Analyst
Worked with Python to clean data and build analytical reports.

PROJECTS
Sales analysis
Created visualizations and investigated sales trends using Python.

EDUCATION
Bachelor of Information Systems
"""

resultado = extract_skills(
    text=curriculo,
    ner_entities=[],
)

assert resultado["skills"] == ["Python", "SQL"]

contextos = resultado["context_blocks"]

assert len(contextos) == 2
assert contextos[0]["source"] == "experience"
assert contextos[1]["source"] == "project"

# A frase deve ser preservada mesmo sem previsão do NER.
assert "Worked with Python" in contextos[0]["text"]

# A formação não deve entrar no bloco de projetos.
assert "Bachelor" not in contextos[1]["text"]

# Não acrescentamos uma biblioteca que não foi mencionada.
assert "Pandas" not in resultado["skills"]

for item in resultado["semantic_inputs"]:
    print(f"\nOrigem: {item['source']}")
    print(item["text"])

print("\nTeste concluído.")