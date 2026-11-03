import json
from pathlib import Path

from src.nlp.embeddings import ResumeEmbedder
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

# Neste teste, não precisamos carregar o NER.
extraction = extract_skills(
    text=curriculo,
    ner_entities=[],
)

embedder = ResumeEmbedder()

result = embedder.encode(
    extraction["semantic_inputs"]
)

# Confere se cada vetor tem seu registro correspondente.
assert len(result["records"]) == len(result["embeddings"])
assert result["embedding_dimension"] == 768

for vector in result["embeddings"]:
    assert len(vector) == 768

    # Um vetor normalizado deve ter comprimento próximo de 1.
    squared_norm = sum(value * value for value in vector)
    assert abs(squared_norm - 1.0) < 0.001

output = Path("reports/resume_embeddings_example.json")
output.parent.mkdir(parents=True, exist_ok=True)

output.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"\nVetores gerados: {len(result['embeddings'])}")
print(f"Dimensão de cada vetor: {result['embedding_dimension']}")

for record in result["records"]:
    print(f"\nOrigem: {record['source']}")
    print(record["text"])

print(f"\nResultado salvo em: {output}")
print("Teste de embeddings concluído.")