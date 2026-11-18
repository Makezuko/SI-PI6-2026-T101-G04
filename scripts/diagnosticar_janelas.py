"""Offline synthetic reproduction with the configured local retrieval model."""
import json
import time
from pathlib import Path
from src.nlp.embeddings import ResumeEmbedder
from src.matching.semantic import aggregate_requirement_windows, compare


def fixture():
    requirements = [dict(id='R1', text='Desenvolvimento de APIs Python e testes automatizados. ' * 100),
                    dict(id='R2', text='Administrar Kubernetes em producao.')]
    page = 'Experiencia em desenvolvimento ' + 'microarquiteturainternacionalizada ' * 200
    return requirements, [dict(text=page + '\f' + page, source='experience')]


def main():
    started = time.perf_counter()
    manifest = json.loads(Path('models/contextual/manifest.json').read_text(encoding='utf-8'))
    embedder = ResumeEmbedder(manifest['retrieval']['path'])
    requirements, evidence = fixture()
    queries = embedder.encode([dict(text=r['text'], requirement_id=r['id'], source='requirement') for r in requirements])
    vectors = aggregate_requirement_windows(requirements, queries)
    embedded = embedder.encode(evidence)
    for inputs, encoded in [(requirements, queries), (evidence, embedded)]:
        for i, item in enumerate(inputs):
            covered = 0
            for r in [r for r in encoded['records'] if r['input_index'] == i]:
                assert r['start_char'] <= covered
                covered = max(covered, r['end_char'])
                count = len(embedder.tokenizer(r['text'], truncation=False)['input_ids'])
                assert count <= embedder.model.max_seq_length
            assert covered == len(item['text'])
    rows, _ = compare(requirements, vectors, embedded)
    assert [r['id'] for r in rows] == ['R1', 'R2']
    result = dict(model_limit=embedder.model.max_seq_length, requirements=len(requirements),
                  requirement_windows=len(queries['records']), evidence_windows=len(embedded['records']),
                  dimension=len(vectors[0]), complete_coverage=True, ids=[r['id'] for r in rows],
                  seconds=round(time.perf_counter()-started, 3))
    Path('reports/window-real.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
