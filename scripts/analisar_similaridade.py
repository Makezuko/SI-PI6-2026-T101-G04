"""Relatório de similaridade e recuperação de evidências, sem classificação."""
import argparse
import base64
import csv
import html
import io
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from src.matching.semantic import compare, evaluate_ranking

METRIC_GUIDE = [
 ('Similaridade de cosseno', 'Proximidade angular entre dois embeddings; varia de -1 a 1.', 'Quanto os textos estão próximos no espaço do modelo. Não confirma domínio de uma tecnologia e não é probabilidade.'),
 ('Margem Top1–Top2', 'Score da primeira entrada menos o da segunda. Varia de 0 a 2; N/A se houver só uma entrada.', 'Quanto a primeira evidência se destaca da segunda. Margem pequena pode indicar alternativas igualmente relevantes; margem grande não garante correção.'),
 ('Hit@1', 'Fração dos requisitos positivos anotados com uma evidência aceitável em primeiro lugar.', 'Se o primeiro resultado é útil. Valor entre 0 e 1; maior é melhor.'),
 ('Hit@3', 'Fração dos requisitos positivos anotados com alguma evidência aceitável entre as três primeiras entradas.', 'Se a equipe encontra uma evidência correta ao revisar até três resultados. Valor entre 0 e 1; maior é melhor.'),
 ('MRR', 'Média de 1/posição da primeira evidência aceitável; contribuição zero se ela não for recuperada.', 'Quão cedo aparece uma evidência correta. Valor entre 0 e 1; maior é melhor. Primeiro lugar contribui 1, segundo 0,5 e terceiro 0,333.')]


def chart_image(fig):
    buffer=io.BytesIO()
    fig.savefig(buffer,format='png',dpi=150,bbox_inches='tight')
    plt.close(fig)
    return '<img alt="Gráfico de similaridade ou ranking" src="data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()+'">'


def make_report(results,matrix,resume,requirements,metrics,note):
    images=[]
    fig,ax=plt.subplots(figsize=(11,max(4,len(results)*.55)))
    im=ax.imshow(matrix,vmin=-1,vmax=1,cmap='RdBu_r',aspect='auto')
    ax.set_yticks(range(len(results)),[r['id'] for r in results])
    ax.set_xticks(range(len(resume['records'])),[f"I{r['input_index']} / {r['source']} / C{r['chunk_index']}" for r in resume['records']],rotation=60,ha='right')
    if matrix.size<=100:
        for (i,j),v in np.ndenumerate(matrix): ax.text(j,i,f'{v:.2f}',ha='center',va='center',color='white' if abs(v)>.6 else '#17233c')
    ax.set_title('Similaridade: requisitos × trechos'); fig.colorbar(im,ax=ax,label='Cosseno')
    images.append(chart_image(fig))
    fig,ax=plt.subplots(figsize=(11,max(4,len(results)*.6)))
    pos=np.arange(len(results))
    ax.barh(pos-.18,[r['skills_only_similarity'] if r['skills_only_similarity'] is not None else np.nan for r in results],.35,label='Só skills',color='#94a3b8')
    ax.barh(pos+.18,[r['top_similarity'] for r in results],.35,label='Skills + contexto',color='#2563eb')
    ax.set_yticks(pos,[r['id'] for r in results]);ax.invert_yaxis();ax.set_xlim(-1,1);ax.legend()
    ax.set_xlabel('Maior similaridade de cosseno');ax.set_title('Efeito do contexto no score máximo')
    images.append(chart_image(fig))
    fig,ax=plt.subplots(figsize=(11,max(4,len(results)*.5)))
    margins=[r['top1_top2_margin'] if r['top1_top2_margin'] is not None else np.nan for r in metrics['per_requirement']]
    ax.barh(pos,margins,color='#0f766e');ax.set_yticks(pos,[r['id'] for r in results]);ax.invert_yaxis();ax.set_xlim(0,2)
    ax.set_xlabel('Diferença entre os scores Top1 e Top2');ax.set_title('Destaque da primeira evidência (não é confiança)')
    images.append(chart_image(fig))
    if metrics['evaluated_positive_count']:
        fig,ax=plt.subplots(figsize=(8,4))
        values=[metrics[k] for k in ('hit_at_1','hit_at_3','mrr')]
        ax.bar(['Hit@1','Hit@3','MRR'],values,color=['#2563eb','#0f766e','#7c3aed'])
        ax.set_ylim(0,1.12);ax.set_ylabel('Métrica, entre 0 e 1');ax.set_title(f"Qualidade do ranking: {metrics['evaluated_positive_count']} positivos anotados")
        for i,v in enumerate(values):ax.text(i,v+.02,f'{v:.3f}',ha='center')
        images.append(chart_image(fig))
    cards=''
    for key,label in [('hit_at_1','Hit@1'),('hit_at_3','Hit@3'),('mrr','MRR')]:
        v=metrics[key];display='N/A' if v is None else f'{v:.3f}'
        cards+=f'<div class="card"><small>{label}</small><strong>{display}</strong></div>'
    guide=''.join(f'<tr><td><b>{html.escape(name)}</b></td><td>{html.escape(definition)}</td><td>{html.escape(purpose)}</td></tr>' for name,definition,purpose in METRIC_GUIDE)
    rows=''
    for row,requirement,diagnostic in zip(results,requirements,metrics['per_requirement']):
        gold=requirement.get('acceptable_input_indices')
        expected='Não anotado' if gold is None else ('Sem evidência suficiente' if not gold else 'Entradas aceitáveis: '+str(gold))
        rank=diagnostic['first_relevant_rank'];rank_display='N/A' if diagnostic['annotation_status']!='positivo anotado' else (str(rank) if rank else 'Não recuperada')
        margin=diagnostic['top1_top2_margin'];margin_display='N/A' if margin is None else f'{margin:.3f}'
        evidence=''.join(f"<li><b>{e['similarity']:.3f} — I{e['input_index']} / {html.escape(str(e['source']))}</b><br>{html.escape(e['text'])}</li>" for e in row['ranking'][:3])
        rows+=f"<tr><td><b>{html.escape(row['id'])}</b><br>{html.escape(row['requirement'])}</td><td>{html.escape(expected)}</td><td>{rank_display}</td><td>{margin_display}</td><td><ol>{evidence}</ol></td></tr>"
    inputs=''.join(f"<li>I{r['input_index']} / C{r['chunk_index']} — {html.escape(r['text'])}</li>" for r in resume['records'])
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Similaridade e ranking</title>
<style>body{{font:16px system-ui;background:#f3f6fb;color:#17233c;margin:0}}main{{max-width:1200px;margin:auto;padding:32px}}section,.notice{{background:white;padding:24px;border-radius:14px;margin:20px 0}}.notice{{border-left:5px solid #d97706}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}.card{{background:#eaf0ff;padding:18px;min-width:140px;border-radius:12px}}strong{{display:block;font-size:28px}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:14px;border-bottom:1px solid #dbe2ed;text-align:left;vertical-align:top}}li{{margin-bottom:12px}}.scroll{{overflow:auto}}</style>
<main><h1>Similaridade e recuperação de evidências</h1><p>Sem limiar, classificação ou nota final de aderência.</p><p>Modelo: {html.escape(resume['model_name'])}</p>
<div class="notice">{html.escape(note)}<p>Similaridade mede proximidade textual; Hit@k e MRR avaliam o ranking contra anotações humanas. Nenhuma dessas métricas comprova qualificação do candidato.</p></div>
<section><h2>O que cada medida significa</h2><div class="scroll"><table><tr><th>Medida</th><th>O que é</th><th>O que deseja mostrar</th></tr>{guide}</table></div></section>
<section><h2>Qualidade do ranking no exemplo</h2><p>{metrics['total_requirements']} requisitos; {metrics['evaluated_positive_count']} positivos avaliados; {metrics['no_evidence_count']} sem evidência suficiente; {metrics['unannotated_count']} não anotados.</p><div class="cards">{cards}</div><p>Itens sem evidência não entram no denominador de Hit@k/MRR, mas continuam na revisão visual. N/A significa que não há positivos anotados para calcular a métrica. Hit@3 não é Recall@3: basta encontrar uma evidência aceitável.</p></section>
<section><h2>Gráficos para diagnóstico</h2>{''.join(images)}<p>O máximo com contexto é sempre maior ou igual ao máximo só de skills, pois há mais opções. Isso não comprova melhoria de qualidade. Compare as evidências com as anotações.</p></section>
<section><h2>Revisão requisito por requisito</h2><div class="scroll"><table><tr><th>Requisito</th><th>Anotação</th><th>Posição da 1ª evidência correta</th><th>Margem</th><th>Top 3</th></tr>{rows}</table></div></section>
<section><h2>Entradas do currículo</h2><ol>{inputs}</ol></section>
<section><h2>Limites e próximo experimento</h2><p>Os exemplos didáticos não validam desempenho geral. O gold atual é por entrada original; para blocos extensos, anote trechos específicos. Rankings agrupam chunks da mesma entrada para não inflar Hit@3 com sobreposição.</p><p>Amplie para vários currículos e vagas, com anotações revisadas pela equipe. Inclua paráfrases, casos relacionados sem comprovação e requisitos ausentes. Uma palavra relacionada, como Python, não confirma Pandas. Mantenha um teste independente para avaliar decisões futuras de modelagem.</p><a href="https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html">Documentação de similaridade</a></section></main></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',default='reports/resume_embeddings_example.json')
    parser.add_argument('--requirements',default='examples/requisitos_exemplo.json')
    parser.add_argument('--output-dir',default='reports/semantic_ranking')
    args=parser.parse_args()
    resume=json.loads(Path(args.resume).read_text(encoding='utf-8'))
    config=json.loads(Path(args.requirements).read_text(encoding='utf-8'));requirements=config['requirements']
    if not requirements or len({r['id'] for r in requirements})!=len(requirements):raise ValueError('Requisitos precisam de IDs únicos.')
    known_ids={r['input_index'] for r in resume['records']}
    for r in requirements:
        if not isinstance(r['text'],str) or not r['text'].strip():raise ValueError('Requisito vazio.')
        gold=r.get('acceptable_input_indices')
        if gold is not None and (not isinstance(gold,list) or not set(gold).issubset(known_ids)):raise ValueError('Anotação inválida ou entrada inexistente.')
    from src.nlp.embeddings import ResumeEmbedder
    embedder=ResumeEmbedder(model_name=resume['model_name'])
    queries=embedder.encode([{'text':r['text'],'source':'requirement'} for r in requirements])
    if len(queries['records'])!=len(requirements):raise ValueError('Divida requisitos longos em requisitos curtos.')
    results,matrix=compare(requirements,queries['embeddings'],resume)
    metrics=evaluate_ranking(results,requirements)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    note=config.get('dataset_note','Conjunto informado pelo usuário')
    payload={'dataset_note':note,'model_name':resume['model_name'],'requirements':requirements,'metrics':metrics,'results':results,'similarity_matrix':matrix.tolist(),'requirement_embeddings':queries}
    (out/'resultados.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'comparacao.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['id','requisito','cosseno_top1','cosseno_so_skills','margem_top1_top2','posicao_correta','origem','evidencia'])
        for row,diag in zip(results,metrics['per_requirement']):writer.writerow([row['id'],row['requirement'],row['top_similarity'],row['skills_only_similarity'],diag['top1_top2_margin'],diag['first_relevant_rank'],row['ranking'][0]['source'],row['ranking'][0]['text']])
    (out/'relatorio.html').write_text(make_report(results,matrix,resume,requirements,metrics,note),encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False,indent=2));print(f'\nRelatório: {out / "relatorio.html"}')
if __name__=='__main__':main()
