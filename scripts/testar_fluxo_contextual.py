"""Demonstração local com os três modelos reais; não acessa Supabase."""
import argparse
import json
import os
from pathlib import Path
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--input', type=Path, default=Path('tests/fixtures/documental_resume.txt'))
    parser.add_argument('--requirements', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', type=Path, default=Path('reports/contextual-local.json'))
    args = parser.parse_args()
    manifest = json.loads(Path('models/contextual/manifest.json').read_text(encoding='utf-8'))
    selected = manifest.get('gguf') or manifest.get('evaluator')
    if not selected:
        parser.error('Prepare o runtime com scripts.preparar_runtime_contextual')
    os.environ.update(CONTEXTUAL_EVALUATOR='experimental',
                      CONTEXTUAL_MODEL_PATH=selected['path'],
                      CONTEXTUAL_MODEL_REVISION=selected['revision'])
    if 'gguf' in manifest:
        os.environ.update(CONTEXTUAL_BACKEND='llama_cpp', CONTEXTUAL_RUNTIME_PATH=selected['runtime'],
                          CONTEXTUAL_RUNTIME_REVISION=selected['runtime_sha256'])
    from src.nlp.inference import ResumeNERPredictor
    from src.nlp.skills_extractor import extract_skills
    from src.nlp.embeddings import ResumeEmbedder
    from src.data.privacy import anonymize_for_analysis, sanitize_semantic_inputs, valid_entity
    from src.matching.semantic import compare
    from src.matching.contextual import create_adapter, evaluate_batch
    text = args.input.read_text(encoding='utf-8')
    requirements = json.loads(args.requirements.read_text(encoding='utf-8')) if args.requirements else [
        dict(id='r1', text='Experiência prática desenvolvendo APIs com Python.', nivel='obrigatorio'),
        dict(id='r2', text='Graduação concluída em Sistemas de Informação ou área relacionada.', nivel='obrigatorio'),
        dict(id='r3', text='Conhecimento de inglês avançado.', nivel='desejavel'),
        dict(id='r4', text='Experiência administrando Kubernetes.', nivel='desejavel')]
    if args.limit:
        requirements = requirements[:args.limit]
    start = perf_counter()
    print('1/4 NER treinado', flush=True)
    ner = ResumeNERPredictor(model_directory='models/ner/augmented/best_model')
    prediction = ner.predict(text=text, minimum_confidence=0.0)
    safe_text = anonymize_for_analysis(text, prediction['entities'])
    # Extração NER de habilidades é combinada com seções e contextos.
    skills = [e for e in prediction['entities'] if e['label'] == 'SKILLS' and valid_entity(text, e)]
    entries = sanitize_semantic_inputs(extract_skills(safe_text, skills)['semantic_inputs'])
    print('2/4 Recuperação semântica multilíngue', flush=True)
    embedder = ResumeEmbedder(manifest['retrieval']['path'])
    vectors = embedder.encode([dict(text=r['text'], source='requirement') for r in requirements])
    rows, _ = compare(requirements, vectors['embeddings'], embedder.encode(entries))
    # Libera modelos da etapa anterior antes de carregar o avaliador na CPU.
    import gc
    del ner, embedder
    gc.collect()
    print('3/4 Avaliador contextual local', flush=True)
    adapter = create_adapter(selected['path'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw_path = args.output.with_suffix('.generations.jsonl')
    raw_path.write_text('', encoding='utf-8')
    class RecordingAdapter:
        def generate(self, payload):
            raw = adapter.generate(payload)
            with raw_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(dict(requirement=payload['requisito'], raw=raw), ensure_ascii=False) + '\n')
            return raw
    result = evaluate_batch(requirements, rows, entries, RecordingAdapter(),
                            progress=lambda identifier, verdict: print(
                                identifier, verdict['estado'], flush=True))
    report = dict(simulated=False, human_validated=False, models=manifest, result=result,
                  seconds=perf_counter() - start)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('4/4 Relatório:', args.output, flush=True)
    for detail in result['details']:
        print(detail['id'], detail['diagnostic']['contextual']['estado'], flush=True)
    print('Mínimo confirmado:', result['score'], 'Máximo possível:', result['maximum_score'], flush=True)


if __name__ == '__main__':
    main()
