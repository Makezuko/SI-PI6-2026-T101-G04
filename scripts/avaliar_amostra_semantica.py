"""Avalia somente após anotação humana; usa entradas congeladas e métricas existentes."""
import argparse
import csv
import html
import json
import os
from pathlib import Path

from scripts.avaliacao_semantica import (code_hashes, consolidate, digest, fingerprint,
    pipeline_version, private_output, read, save, validate_annotation)
from src.matching.semantic import compare


def preflight(directory):
    directory = private_output(directory)
    manifest = read(directory / 'manifest.json')
    if manifest['status'] != 'awaiting_human_review' or len(manifest['selected_resumes']) != 10:
        raise ValueError('Preparação incompleta.')
    if manifest['code_hashes'] != code_hashes() or manifest['pipeline_version'] != pipeline_version():
        raise ValueError('Pipeline mudou; entradas e anotações precisam de nova versão.')
    bundles = []
    for item in manifest['selected_resumes']:
        folder = directory / item['resume_id']
        if not folder.resolve().is_relative_to(directory):
            raise ValueError('Pasta de currículo inválida.')
        if digest((folder / 'curriculo.txt').read_bytes()) != item['text_sha256']:
            raise ValueError('Texto original alterado.')
        inputs = read(folder / 'entradas.json')
        annotation = read(folder / 'anotacoes.json')
        if annotation.get('resume_id') != item['resume_id']:
            raise ValueError('Anotação de outro currículo.')
        requirements = validate_annotation(annotation, inputs, item['inputs_sha256'])
        embeddings = read(folder / 'embeddings.json')
        if fingerprint(embeddings) != item['embeddings_sha256']:
            raise ValueError('Embeddings alterados.')
        if embeddings['model_name'] != manifest['embedding_model']:
            raise ValueError('Modelo incompatível.')
        if len(embeddings['records']) != len(embeddings['embeddings']):
            raise ValueError('Registros e vetores incompatíveis.')
        known = set(range(len(inputs)))
        for record in embeddings['records']:
            index = record['input_index']
            if type(index) is not int or index not in known:
                raise ValueError('Índice do embedding incompatível.')
            original = inputs[index]
            if (record['text'] != original['text'][record['start_char']:record['end_char']]
                    or record['source'] != original['source']):
                raise ValueError('Embedding não corresponde à entrada congelada.')
        bundles.append((item['resume_id'], requirements, embeddings, inputs, annotation))
    return manifest, bundles


def evaluate(bundles, embedder):
    rows = []
    for rid, requirements, embedded, inputs, annotation in bundles:
        # Apenas id/text entram na recuperação. Categorias e gold ficam fora.
        queries_data = [dict(id=r['id'], text=r['text']) for r in requirements]
        if embedded['records']:
            queries = embedder.encode([dict(text=r['text'], source='requirement') for r in queries_data])
            if (len(queries['records']) != len(requirements)
                    or [r['input_index'] for r in queries['records']] != list(range(len(requirements)))):
                raise ValueError('Divida requisitos longos em requisitos curtos.')
            results, _ = compare(queries_data, queries['embeddings'], embedded)
        else:
            # Extração vazia não é descartada nem recebe similaridade fictícia.
            results = [dict(id=r['id'], requirement=r['text'], ranking=[],
                            top_similarity=None, skills_only_similarity=None) for r in queries_data]
        for r, result in zip(requirements, results):
            rows.append(dict(resume_id=rid, requirement=r, result=result,
                             expected_inputs=[inputs[i] for i in r['acceptable_input_indices']],
                             human_review=annotation['human_review']))
    return rows


def write_reports(output, rows, summary, manifest, bundles):
    output = private_output(output)
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'resultados.json', dict(summary=summary, rows=rows, manifest=manifest,
         annotations_sha256={rid: fingerprint(annotation) for rid, _, _, _, annotation in bundles}))
    # Arquivo separado sem textos/IDs de currículos: base para documentação futura.
    save(output / 'agregados_sem_dados_pessoais.json', dict(
        commit=manifest['commit'], pipeline_version=manifest['pipeline_version'],
        resume_count=summary['resume_count'], requirement_count=summary['requirement_count'],
        overall={k: v for k, v in summary['overall'].items() if k != 'per_requirement'},
        ranking_only={k: v for k, v in summary['ranking_only'].items() if k != 'per_requirement'}))
    with (output / 'comparacao.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['curriculo', 'requisito_id', 'requisito', 'categoria', 'esperado',
                         'falha_extracao', 'posicao_correta', 'top3'])
        for row, diagnostic in zip(rows, summary['overall']['per_requirement']):
            r = row['requirement']
            writer.writerow([row['resume_id'], r['id'], r['text'], r['category'], r['expected_evidence'],
                             r['extraction_failure'], diagnostic['first_relevant_rank'],
                             json.dumps(row['result']['ranking'][:3], ensure_ascii=False)])
    with (output / 'metricas.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['grupo', 'nome', 'denominador', 'Hit@1', 'Hit@3', 'MRR'])
        groups = [('geral', 'ponta a ponta', summary['overall']),
                  ('geral', 'somente ranking', summary['ranking_only'])]
        groups += [('curriculo', name, m) for name, m in summary['by_resume'].items()]
        groups += [('categoria', name, m) for name, m in summary['by_category'].items()]
        for group, name, m in groups:
            writer.writerow([group, name, m['denominator'], *[
                m[k] if m[k] is not None else 'N/A' for k in ('hit_at_1', 'hit_at_3', 'mrr')]])
    (output / 'relatorio.html').write_text(render(rows, summary), encoding='utf-8')


def render(rows, summary):
    from scripts.analisar_similaridade import chart_image
    import matplotlib.pyplot as plt
    import numpy as np
    keys = ['hit_at_1', 'hit_at_3', 'mrr']
    groups = [('Geral', summary['overall']), *summary['by_resume'].items()]
    fig, ax = plt.subplots(figsize=(13, 6))
    for i, key in enumerate(keys):
        values = [m[key] if m[key] is not None else np.nan for _, m in groups]
        ax.bar(np.arange(len(groups)) + i * .25, values, .25, label=key)
    ax.set_xticks(np.arange(len(groups)) + .25,
                  [f"{name}\nn={m['denominator']}" for name, m in groups], rotation=60, ha='right')
    ax.set_ylim(0, 1.1)
    ax.legend()
    ax.set_title('Recuperação ponta a ponta; N/A quando n=0')
    chart = chart_image(fig)
    esc = lambda value: html.escape(str(value))
    fmt = lambda value: 'N/A' if value is None else f'{value:.3f}'
    tables = ''
    for label, metrics in [('Ponta a ponta', {'Geral': summary['overall']}),
                           ('Somente ranking', {'Recuperáveis': summary['ranking_only']}),
                           ('Por currículo', summary['by_resume']), ('Por categoria', summary['by_category'])]:
        tables += f'<h2>{label}</h2><table><tr><th>Grupo</th><th>n</th><th>Hit@1</th><th>Hit@3</th><th>MRR</th></tr>'
        for name, m in metrics.items():
            tables += f'<tr><td>{esc(name)}</td><td>{m["denominator"]}</td>' + ''.join(
                f'<td>{fmt(m[key])}</td>' for key in keys) + '</tr>'
        tables += '</table>'
    details = ''
    for row, diagnostic in zip(rows, summary['overall']['per_requirement']):
        r = row['requirement']
        expected = r['expected_evidence'] or 'Sem evidência suficiente no original'
        expected += '\n' + '\n'.join(f"I{x['input_index']} / {x['source']}: {x['text']}" for x in row['expected_inputs'])
        top = ''.join(f"<li>I{e['input_index']} / {esc(e['source'])} / cosseno {e['similarity']:.4f}<br>{esc(e['text'])}</li>"
                      for e in row['result']['ranking'][:3]) or 'Nenhuma entrada extraída'
        rank = diagnostic['first_relevant_rank']
        status = ('Falha de extração' if r['extraction_failure'] else
                  'Inspeção sem evidência' if not r['evidence_in_original'] else
                  'Acerto Top1' if rank == 1 else 'Acerto Top3' if rank and rank <= 3 else 'Erro Top3')
        details += (f"<tr><td>{esc(row['resume_id'])} / {esc(r['id'])}<br>{esc(r['text'])}<br>{esc(r['category'])}</td>"
                    f"<td>{esc(expected)}</td><td>{status}<br>Posição: {rank or 'N/A'}</td><td><ol>{top}</ol></td>"
                    f"<td>{esc(r['notes'])}<br>{esc(json.dumps(r['human_analysis'], ensure_ascii=False))}</td></tr>")
    overall = summary['overall']
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Avaliação ampliada</title>
<style>body{{font:16px system-ui;margin:32px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border:1px solid #ccc;text-align:left;vertical-align:top;white-space:pre-wrap}}img{{max-width:100%}}</style>
<h1>Avaliação semântica ampliada</h1><p>{summary['resume_count']} currículos; {summary['requirement_count']} requisitos;
{overall['denominator']} positivos anotados (incluindo {overall['extraction_lost_positive_count']} perdidos na extração);
{overall['no_evidence_count']} sem evidência no original.</p>
<p>Métricas gerais reúnem todos os positivos. Falhas de extração contam como zero na visão ponta a ponta.
A visão somente ranking exclui {summary['ranking_only']['excluded_extraction_failures']} falhas de extração e informa seu denominador.
N/A significa ausência de casos elegíveis. Categorias são humanas e não influenciam a recuperação.</p>
<p>Sem evidência: o sistema ainda retorna o trecho mais próximo quando há entradas. Estes casos ficam fora de Hit@k/MRR;
isto não avalia capacidade de abstenção. Cosseno não confirma competência. Campos humanos registram hipóteses, não causas demonstradas.</p>
{tables}{chart}<h2>Acertos, erros e inspeção por requisito</h2><table><tr><th>Requisito</th><th>Evidência esperada</th><th>Diagnóstico</th><th>Top3</th><th>Análise humana</th></tr>{details}</table></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-dir', type=Path, default=Path('reports/avaliacao_semantica_ampliada'))
    parser.add_argument('--output-dir', type=Path, default=Path('reports/avaliacao_semantica_ampliada_resultados'))
    args = parser.parse_args()
    manifest, bundles = preflight(args.sample_dir)  # antes de carregar modelo ou consultar ranking
    output = private_output(args.output_dir)
    if output.exists():
        raise ValueError('Destino já existe; preserve os relatórios anteriores.')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from src.nlp.embeddings import ResumeEmbedder
    embedder = ResumeEmbedder(model_name=manifest['embedding_model'])
    model_hash = fingerprint({k: digest(v.detach().cpu().numpy().tobytes())
                              for k, v in embedder.model.state_dict().items()})
    if (model_hash != manifest['embedding_model_sha256']
            or digest(embedder.tokenizer.backend_tokenizer.to_str().encode()) != manifest['embedding_tokenizer_sha256']
            or embedder.window_size != manifest['parameters']['window_size']
            or embedder.overlap != manifest['parameters']['overlap']):
        raise ValueError('Modelo, tokenizer ou segmentação mudou.')
    rows = evaluate(bundles, embedder)
    summary = consolidate(rows, [bundle[0] for bundle in bundles])
    write_reports(output, rows, summary, manifest, bundles)
    print('Relatórios salvos em ' + str(output))


if __name__ == '__main__':
    main()
