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

experiencias = [item for item in contextos if item['source'] == 'experience']
projetos = [item for item in contextos if item['source'] == 'project']
assert experiencias and projetos
assert any(item['source'] == 'education' for item in contextos)

# A frase deve ser preservada mesmo sem previsão do NER.
assert any("Worked with Python" in item['text'] for item in experiencias)

# A formação não deve entrar no bloco de projetos.
assert all("Bachelor" not in item['text'] for item in projetos)

# Não acrescentamos uma biblioteca que não foi mencionada.
assert "Pandas" not in resultado["skills"]

for item in resultado["semantic_inputs"]:
    print(f"\nOrigem: {item['source']}")
    print(item["text"])

print("\nTeste concluído.")
