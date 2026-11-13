"""Prepara dez currículos adicionais da validação, sem comparar ou ranquear."""
import argparse
import os
from pathlib import Path

from scripts.avaliacao_semantica import (ROOT, VALIDATION, EXCLUDED, code_hashes,
    digest, fingerprint, git, integrated_inputs, annotation_template, pipeline_version,
    private_output, read, save, select_sample)


def prepare(output, predictor, embedder, ner_dir):
    output = private_output(output)
    if output.exists():
        raise ValueError('Destino já existe; não sobrescrever anotações ou entradas congeladas.')
    data = read(VALIDATION)
    sample = select_sample(data)
    output.mkdir(parents=True)
    files = sorted(p for p in Path(ner_dir).rglob('*') if p.is_file())
    manifest = dict(schema_version=1, split='validation', seed=42, sample_size=10,
        source_file='data/processed/splits/validation.json', source_sha256=digest(VALIDATION.read_bytes()),
        commit=git('rev-parse', 'HEAD'), pipeline_version=pipeline_version(), code_hashes=code_hashes(),
        integration_in_main=subprocess_ancestor(),
        integration_dependency='33a0f6c885e97dc09f77db7643727c5eaef2332d',
        excluded_ids=EXCLUDED, exclusion_verification='IDs recalculados no validation; não são IDs nativos.',
        previous_artifacts=verify_previous(data),
        ner_model=str(ner_dir), ner_files={str(p.relative_to(ner_dir)): digest(p.read_bytes()) for p in files},
        embedding_model=embedder.model_name,
        embedding_model_sha256=fingerprint({k: digest(v.detach().cpu().numpy().tobytes())
                                            for k, v in embedder.model.state_dict().items()}),
        embedding_tokenizer_sha256=digest(embedder.tokenizer.backend_tokenizer.to_str().encode()),
        parameters=dict(ner_minimum_confidence=0.0, window_size=embedder.window_size,
                        overlap=embedder.overlap, batch_size=8, normalized=True,
                        comparison='cosine; max por input_index; desempate input_index crescente',
                        top_k=3, ranking_metrics=['Hit@1', 'Hit@3', 'MRR']),
        selected_resumes=[], status='preparing')
    save(output / 'manifest.json', manifest)
    for item in sample:
        folder = output / item['resume_id']
        folder.mkdir()
        raw = item['text']
        (folder / 'curriculo.txt').write_bytes(raw.encode('utf-8'))
        extraction = integrated_inputs(raw, predictor.predict(text=raw, minimum_confidence=0.0)['entities'])
        inputs = [dict(entry, input_index=i) for i, entry in enumerate(extraction['semantic_inputs'])]
        save(folder / 'entradas.json', inputs)
        save(folder / 'extracao.json', extraction)
        embedded = embedder.encode(extraction['semantic_inputs']) if inputs else dict(
            model_name=embedder.model_name, records=[], embeddings=[])
        save(folder / 'embeddings.json', embedded)
        sha = fingerprint(inputs)
        save(folder / 'anotacoes.json', annotation_template(item, sha))
        (folder / 'entradas.md').write_text('\n\n'.join(
            f"I{x['input_index']} | {x['source']}\n{x['text']}" for x in inputs) or
            'Nenhuma entrada extraída. Revise o currículo completo; não substitua este caso.', encoding='utf-8')
        manifest['selected_resumes'].append(dict(
            **{k: v for k, v in item.items() if k != 'text'}, inputs_sha256=sha,
            embeddings_sha256=fingerprint(embedded), input_count=len(inputs),
            status='ready_for_annotation' if inputs else 'empty_extraction'))
        save(output / 'manifest.json', manifest)
        print(f"Preparado {item['resume_id']}: {len(inputs)} entradas; sem ranking.")
    manifest['status'] = 'awaiting_human_review'
    save(output / 'manifest.json', manifest)
    print('Primeiro arquivo: ' + str(output / sample[0]['resume_id'] / 'anotacoes.json'))


def subprocess_ancestor():
    import subprocess
    return subprocess.run(['git', 'merge-base', '--is-ancestor',
                           '33a0f6c885e97dc09f77db7643727c5eaef2332d', 'main'], cwd=ROOT).returncode == 0


def verify_previous(data):
    result = []
    for base in ['amostra_real_validation', 'amostra_real_validation_v2']:
        folder = ROOT / 'reports' / base
        manifest_path = folder / 'manifest.json'
        if manifest_path.is_file():
            previous = read(manifest_path)
            for old in previous.get('selected_resumes', []):
                index = old['source_index']
                if digest(data[index]['content'].encode()) != old['text_sha256']:
                    raise ValueError('Manifesto anterior diverge do validation.')
        checked = 0
        for rid in EXCLUDED:
            path = folder / rid / 'curriculo.txt'
            if path.is_file():
                index = int(rid.split('_')[1])
                if path.read_text(encoding='utf-8') != data[index]['content']:
                    raise ValueError('Texto anterior diverge do validation: ' + rid)
                checked += 1
        result.append(dict(directory=str(folder.relative_to(ROOT)),
                           manifest_present=manifest_path.is_file(), texts_checked=checked))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('reports/avaliacao_semantica_ampliada'))
    parser.add_argument('--model-dir', type=Path, default=Path('models/ner/augmented/best_model'))
    args = parser.parse_args()
    # Apenas cache local: não baixa nem muda modelos durante a preparação.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from src.nlp.inference import ResumeNERPredictor
    from src.nlp.embeddings import ResumeEmbedder
    predictor = ResumeNERPredictor(model_directory=args.model_dir)
    embedder = ResumeEmbedder()
    prepare(args.output_dir, predictor, embedder, args.model_dir)


if __name__ == '__main__':
    main()
