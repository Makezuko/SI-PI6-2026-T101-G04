"""Diagnóstico reproduzível e sem modelos/dados pessoais, com fixture sintética."""
import json
from pathlib import Path

from src.data.privacy import anonymize_for_analysis, sanitize_semantic_inputs
from src.nlp.skills_extractor import extract_skills
from src.matching.adherence import calculate_adherence, evaluate_requirements


def synthetic_diagnostic():
    raw = (Path(__file__).resolve().parents[1] / 'tests/fixtures/documental_resume.txt').read_text(encoding='utf-8')
    name = 'Pessoa Sintética'
    safe = anonymize_for_analysis(raw, [dict(label='NAME', text=name, start=0, end=len(name))])
    entries = sanitize_semantic_inputs(extract_skills(safe)['semantic_inputs'])
    specifications = [
        ('Python', None),
        ('SQL com alternativa PostgreSQL', {'kind': 'any', 'terms': ['sql', 'postgresql']}),
        ('Pandas e NumPy', {'kind': 'all', 'terms': ['pandas', 'numpy']}),
        ('Git e Docker', {'kind': 'all', 'terms': ['git', 'docker']}),
        ('Desenvolver APIs em Python', None),
        ('Inglês intermediário', None),
        ('Bacharelado em Sistemas de Informação', None),
        ('Experiência de cinco anos em liderança', None),
        ('React', None),
    ]
    requirements = [dict(id=f'R{i}', text=text, tipo='tecnico',
                         nivel='obrigatorio' if i < 8 else 'desejavel',
                         **({'condition': condition} if condition else {}))
                    for i, (text, condition) in enumerate(specifications, 1)]
    # Deliberadamente errado para Python: somente SQL no ranking retornado.
    results = [dict(id=r['id'], top_similarity=.9,
                    ranking=[dict(text='SQL', source='skill', similarity=.9,
                                  input_index=0, chunk_index=0)]) for r in requirements]
    decisions = evaluate_requirements(requirements, results, entries)
    result = calculate_adherence(requirements, decisions)
    return dict(requirements_received=requirements, extracted_entries=entries,
                semantic_top1='SQL (sintético, deliberadamente errado para Python)', result=result)


if __name__ == '__main__':
    print(json.dumps(synthetic_diagnostic(), ensure_ascii=False, indent=2, allow_nan=False))
