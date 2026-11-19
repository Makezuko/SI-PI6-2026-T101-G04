"""Gera relatório offline a partir de avaliações existentes, sem inferência."""
import argparse
import csv
import hashlib
import html
import json
import pickletools
from pathlib import Path
import subprocess
import zipfile


def read_json(path, sources):
    path = Path(path)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    sources[str(path)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw.decode('utf-8-sig'))


def percent(value):
    return 'N/D' if value is None else f'{value * 100:.1f}%'


def decimal(value, places):
    return 'N/D' if value is None else f'{value:.{places}f}'


def read_training_args(path, sources):
    """Extrai apenas literais simples do pickle; nunca desserializa objetos."""
    path = Path(path)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    sources[str(path)] = hashlib.sha256(raw).hexdigest()
    keys = {'per_device_train_batch_size', 'per_device_eval_batch_size',
            'gradient_accumulation_steps', 'learning_rate', 'num_train_epochs', 'seed', 'data_seed', '_n_gpu'}
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = [item for item in archive.infolist() if item.filename.endswith('/data.pkl')]
            if len(files) != 1 or files[0].file_size > 2_000_000:
                raise ValueError('Formato de training_args não reconhecido')
            operations = list(pickletools.genops(archive.read(files[0])))
        result = {}
        for index, (op, value, _) in enumerate(operations):
            if op.name not in {'BINUNICODE', 'SHORT_BINUNICODE', 'UNICODE'} or value not in keys:
                continue
            following = operations[index + 1:]
            while following and following[0][0].name in {'BINPUT', 'LONG_BINPUT', 'MEMOIZE', 'PUT'}:
                following = following[1:]
            if following and following[0][0].name in {'BININT', 'BININT1', 'BININT2', 'INT', 'BINFLOAT', 'FLOAT'}:
                if value in result:
                    raise ValueError('Campo training_args duplicado')
                result[value] = following[0][1]
        return result
    except (zipfile.BadZipFile, ValueError, EOFError):
        return None


def scalar(value):
    return 'N/D' if value is None else str(value)


def safe(value):
    return html.escape(scalar(value))


def table(headers, rows):
    return '<table><thead><tr>' + ''.join(f'<th>{safe(x)}</th>' for x in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{safe(v)}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table>'


def synthetic_evidence(case, original):
    """Apresenta evidências fornecidas separadamente dos IDs citados pelo modelo."""
    evidence = original.get('evidence')
    if not isinstance(evidence, list) or evidence != case.get('evidence'):
        return 'Não exibidas: origem sintética não confirmada'
    return '; '.join(f"{entry['id']}: {entry['text']}" for entry in evidence)


def validate_metrics(data, split):
    if data.get('evaluation_scope') != 'document_consolidated':
        raise ValueError('Métricas NER não consolidadas por documento')
    expected = 'train' if split == 'train_original' else split
    if data.get('split') != expected:
        raise ValueError('Split NER incompatível')
    if split == 'train_original' and data.get('train_subset') != 'original':
        raise ValueError('Treino NER não identificado como original')
    for key in ('precision', 'recall', 'f1', 'accuracy'):
        value = data.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
            raise ValueError(f'Métrica NER inválida: {key}')
    return data


def validate_ranking(data):
    for key in ('overall', 'ranking_only'):
        group = data[key]
        if group['denominator'] != group['evaluated_positive_count']:
            raise ValueError('Denominador da recuperação inconsistente')
        for metric in ('hit_at_1', 'hit_at_3', 'mrr'):
            value = group.get(metric)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
                raise ValueError(f'Métrica de recuperação inválida: {metric}')
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ner-dir', type=Path, default=Path('reports/ner_documentacao'))
    parser.add_argument('--semantic-dir', type=Path, default=Path('reports/avaliacao_semantica_ampliada_resultados'))
    parser.add_argument('--contextual-local', type=Path, default=Path('reports/contextual-local.json'))
    parser.add_argument('--contextual-operational', type=Path, default=Path('reports/contextual-operational.json'))
    parser.add_argument('--manifest', type=Path, default=Path('models/contextual/manifest.json'))
    parser.add_argument('--ner-models', type=Path, default=Path('models/ner'))
    parser.add_argument('--ner-preparation', type=Path, default=Path('data/processed/huggingface_ner/preparation_metadata.json'))
    parser.add_argument('--ner-split-manifest', type=Path, default=Path('data/processed/splits/manifest.json'))
    parser.add_argument('--output-dir', type=Path, default=Path('reports/resultados_visuais'))
    args = parser.parse_args(argv)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    output = args.output_dir
    for source_dir in (args.ner_dir, args.semantic_dir, args.ner_models):
        if (output.resolve().is_relative_to(source_dir.resolve())
                or source_dir.resolve().is_relative_to(output.resolve())):
            raise ValueError('O diretório de saída não pode conter nem estar dentro de uma fonte.')
    figures, tables = output / 'figuras', output / 'tabelas'
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    sources, sections, missing = {}, [], []
    for path in map(Path, ('src/nlp/train.py', 'src/nlp/prepare_ner_dataset.py',
                           'src/matching/contextual.py', 'src/matching/local_runtime.py',
                           'src/data/load.py', 'src/data/validate.py')):
        if path.is_file():
            sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            missing.append(str(path))
    plt.rcParams.update({'font.size': 10, 'figure.facecolor': 'white', 'savefig.facecolor': 'white'})

    def save_plot(fig, name):
        for ext in ('png', 'svg'):
            fig.savefig(figures / f'{name}.{ext}', dpi=300, bbox_inches='tight')
        plt.close(fig)
        return f'<figure><img src="figuras/{name}.svg" alt="{safe(name)}"><figcaption>{safe(name.replace("_", " "))}</figcaption></figure>'

    def write_csv(name, headers, rows):
        with (tables / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)

    ner, ner_rows, ner_raw, entity_rows, entity_raw, entity_values = {}, [], [], [], [], {}
    model_labels = {'baseline': 'Modelo de referência', 'augmented': 'Com aumento de dados'}
    split_labels = {'train_original': 'Treino original', 'validation': 'Validação', 'test': 'Teste'}
    for model in ('baseline', 'augmented'):
        for split in ('train_original', 'validation', 'test'):
            folder = args.ner_dir / model / split
            metric = read_json(folder / 'metrics.json', sources)
            if metric is None:
                missing.append(str(folder / 'metrics.json'))
                continue
            metric = validate_metrics(metric, split)
            ner[model, split] = metric
            ner_rows.append([model, split, metric.get('documents'), metric.get('windows'),
                             percent(metric.get('precision')), percent(metric.get('recall')),
                             percent(metric.get('f1')), percent(metric.get('accuracy')), decimal(metric.get('window_loss'), 4)])
            ner_raw.append([model, split, metric.get('documents'), metric.get('windows'), metric.get('precision'),
                            metric.get('recall'), metric.get('f1'), metric.get('accuracy'), metric.get('window_loss')])
            if split == 'test':
                entities = read_json(folder / 'entity_metrics.json', sources)
                if entities is not None:
                    for e in entities:
                        entity_values[model, e['entity']] = e.get('f1-score')
                        entity_rows.append([model, e['entity'], percent(e.get('precision')), percent(e.get('recall')),
                                            percent(e.get('f1-score')), e.get('support')])
                        entity_raw.append([model, e['entity'], e.get('precision'), e.get('recall'), e.get('f1-score'), e.get('support')])
                else:
                    missing.append(str(folder / 'entity_metrics.json'))
                for suffix in ('confusion_matrix', 'confusion_matrix_normalized'):
                    matrix = read_json(folder / (suffix + '.json'), sources)
                    if matrix is None:
                        missing.append(str(folder / (suffix + '.json')))
                        continue
                    labels, values = matrix['labels'], np.asarray(matrix['matrix'], dtype=float)
                    if values.shape != (len(labels), len(labels)) or matrix.get('evaluation_unit') != 'consolidated_token':
                        raise ValueError('Matriz BIO incompatível')
                    fig, ax = plt.subplots(figsize=(12, 10))
                    img = ax.imshow(values, cmap='Blues', aspect='auto')
                    ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=7)
                    ax.set_yticks(range(len(labels)), labels, fontsize=7)
                    title = 'matriz BIO normalizada' if suffix.endswith('normalized') else 'matriz BIO absoluta'
                    ax.set(xlabel='Predição', ylabel='Referência', title=f'{model_labels[model]}: {title} — teste')
                    fig.colorbar(img, ax=ax, label='Proporção por linha' if suffix.endswith('normalized') else 'Tokens')
                    sections.append(save_plot(fig, f'ner_{model}_{suffix}'))
                    write_csv(f'ner_{model}_{suffix}.csv', ['referência / predição'] + labels,
                              [[label] + list(row) for label, row in zip(labels, matrix['matrix'])])
    for split in ('train_original', 'validation', 'test'):
        a, b = ner.get(('baseline', split)), ner.get(('augmented', split))
        if a and b and any(a.get(k) != b.get(k) for k in ('dataset', 'documents', 'windows', 'train_subset')):
            raise ValueError(f'Fontes NER não comparáveis em {split}')
    headers = ['Modelo', 'Split', 'Currículos', 'Janelas', 'Precisão micro', 'Recall micro', 'F1 micro', 'Acurácia token', 'Perda por janela']
    write_csv('ner_metricas.csv', ['Modelo', 'Split', 'Currículos', 'Janelas', 'Precisão micro (0–1)',
                                  'Recall micro (0–1)', 'F1 micro (0–1)', 'Acurácia token (0–1)', 'Perda por janela'], ner_raw)
    entity_headers = ['Modelo', 'Entidade', 'Precisão', 'Recall', 'F1', 'Suporte']
    write_csv('ner_entidades_teste.csv', ['Modelo', 'Entidade', 'Precisão (0–1)', 'Recall (0–1)', 'F1 (0–1)', 'Suporte'], entity_raw)
    if ner:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
        for ax, model in zip(axes, ('baseline', 'augmented')):
            splits = [s for s in ('train_original', 'validation', 'test') if (model, s) in ner]
            x = np.arange(len(splits))
            for i, (field, label) in enumerate((('precision', 'Precisão'), ('recall', 'Recall'), ('f1', 'F1 micro'))):
                ax.bar(x + (i-1)*.23, [ner[model, s].get(field, float('nan')) * 100 for s in splits], .23, label=label)
            ax.set_xticks(x, [split_labels[s] for s in splits], rotation=15); ax.set_title(model_labels[model]); ax.set_ylim(0, 100); ax.set_ylabel('% de entidades'); ax.legend()
        fig.suptitle('NER: métricas de entidades consolidadas por currículo')
        overview = save_plot(fig, 'ner_micro')
        fig, ax = plt.subplots(figsize=(11, 6))
        entities = sorted({r[1] for r in entity_rows})
        for i, model in enumerate(('baseline', 'augmented')):
            values = []
            for entity in entities:
                value = entity_values.get((model, entity))
                values.append(value * 100 if value is not None else float('nan'))
            ax.barh(np.arange(len(entities)) + (i-.5)*.35, values, .35, label=model_labels[model])
        ax.set_yticks(np.arange(len(entities)), entities); ax.set_xlim(0, 100); ax.set_xlabel('F1 por entidade (%)'); ax.legend(); ax.set_title('NER — entidades no teste')
        entity_figure = save_plot(fig, 'ner_entidades_teste')
    else:
        overview = entity_figure = '<p>Resultados NER indisponíveis.</p>'
    ner_html = '<h2>NER — DistilBERT</h2><p>Precisão, recall e F1 micro de spans BIO consolidados por currículo (seqeval padrão, não estrito); acurácia por token é complementar. Perda é por janela. Treino original não é treino ampliado; treino não mede generalização. Matrizes BIO comparam tokens; linhas normalizadas sem suporte não representam desempenho zero.</p>' + overview + table(headers, ner_rows) + entity_figure + table(entity_headers, entity_rows) + ''.join(sections)
    ner_html += '<p>SKILLS exige cautela: resultados por entidade mostram a limitação do NER; o extrator híbrido complementa entidades com regras e seções. O augmentation altera também o número de atualizações; ganhos não podem ser atribuídos isoladamente a ele.</p>'
    sections = [ner_html]

    agg = read_json(args.semantic_dir / 'agregados_sem_dados_pessoais.json', sources)
    full = read_json(args.semantic_dir / 'resultados.json', sources)
    if agg:
        validate_ranking(agg)
        if full:
            for group in ('overall', 'ranking_only'):
                observed = full.get('summary', {}).get(group, {})
                for key in ('denominator', 'hit_at_1', 'hit_at_3', 'mrr'):
                    if observed.get(key) != agg[group].get(key):
                        raise ValueError('Agregado semântico diverge do relatório completo')
        rows = [[label, g['denominator'], g.get('extraction_lost_positive_count'), g.get('excluded_extraction_failures'),
                 percent(g.get('hit_at_1')), percent(g.get('hit_at_3')), 'N/D' if g.get('mrr') is None else f"{g['mrr']:.3f}"]
                for label, g in [('Ponta a ponta', agg['overall']), ('Somente ranking', agg['ranking_only'])]]
        headers = ['Visão', 'Positivos', 'Perdidos na extração', 'Excluídos', 'Hit@1', 'Hit@3', 'MRR (0–1)']
        write_csv('recuperacao.csv', ['Visão', 'Positivos', 'Perdidos na extração', 'Excluídos',
                                       'Hit@1 (0–1)', 'Hit@3 (0–1)', 'MRR (0–1)'],
                  [[label, g['denominator'], g.get('extraction_lost_positive_count'), g.get('excluded_extraction_failures'),
                    g.get('hit_at_1'), g.get('hit_at_3'), g.get('mrr')]
                   for label, g in [('Ponta a ponta', agg['overall']), ('Somente ranking', agg['ranking_only'])]])
        fig, ax = plt.subplots(figsize=(8, 4.5)); x = np.arange(2)
        for i, (key, label) in enumerate((('hit_at_1', 'Hit@1'), ('hit_at_3', 'Hit@3'))):
            ax.bar(x + (i-.5)*.3, [agg[g][key]*100 if agg[g].get(key) is not None else float('nan') for g in ('overall', 'ranking_only')], .3, label=label)
        ax.set_xticks(x, ['Ponta a ponta', 'Somente ranking']); ax.set_ylim(0, 100); ax.set_ylabel('% dos positivos'); ax.legend(); ax.set_title('Recuperação: Hit@k')
        plot = save_plot(fig, 'recuperacao_hit')
        manifest = full.get('manifest', {}) if full else {}
        reviewed = {r.get('human_review', {}).get('reviewed_before_ranking') for r in full.get('rows', [])} if full else set()
        sections.append('<h2>Recuperação semântica — avaliação histórica</h2>' + plot + table(headers, rows) +
                        f"<p>Currículos: {safe(agg.get('resume_count'))}; requisitos: {safe(agg.get('requirement_count'))}; sem evidência: {safe(agg['overall'].get('no_evidence_count'))}. Modelo: {safe(manifest.get('embedding_model'))}; split: {safe(manifest.get('split'))}; commit: {safe(agg.get('commit'))}; pipeline: {safe(agg.get('pipeline_version'))}. Anotações humanas: campo reviewed_before_ranking observado = {safe(sorted(str(x) for x in reviewed))}; idioma não registrado no agregado. Itens sem evidência não entram no denominador positivo; isso não mede abstenção.</p>")
        if full:
            categories = full.get('summary', {}).get('by_category', {})
            eligible = [(name, value) for name, value in categories.items() if value.get('denominator', 0) > 0]
            category_rows = [[name, data.get('denominator'), percent(data.get('hit_at_1')),
                              percent(data.get('hit_at_3')),
                              'N/D' if data.get('mrr') is None else f"{data['mrr']:.3f}"] for name, data in categories.items()]
            write_csv('recuperacao_categorias.csv', ['Categoria', 'Positivos', 'Hit@1 (0–1)', 'Hit@3 (0–1)', 'MRR (0–1)'],
                      [[name, data.get('denominator'), data.get('hit_at_1'), data.get('hit_at_3'), data.get('mrr')]
                       for name, data in categories.items()])
            category_plot = ''
            if eligible:
                fig, ax = plt.subplots(figsize=(8, 4.5)); x = np.arange(len(eligible))
                for i, (key, label) in enumerate((('hit_at_1', 'Hit@1'), ('hit_at_3', 'Hit@3'))):
                    ax.bar(x + (i-.5)*.3, [v[key]*100 if v.get(key) is not None else float('nan') for _, v in eligible], .3, label=label)
                ax.set_xticks(x, [f"{name}\n(n={value['denominator']})" for name, value in eligible]); ax.set_ylim(0, 100); ax.set_ylabel('% dos positivos'); ax.set_title('Recuperação por categoria — ponta a ponta'); ax.legend()
                category_plot = save_plot(fig, 'recuperacao_categorias')
            sections.append(category_plot + table(['Categoria', 'Positivos', 'Hit@1', 'Hit@3', 'MRR'], category_rows) + '<p>Categorias sem positivos permanecem sem métrica; os recortes são pequenos.</p>')
            resumes = list(full.get('summary', {}).get('by_resume', {}).values())
            if resumes:
                labels = [f'Currículo {i+1}\n(n={v.get("denominator", "N/D")})' for i, v in enumerate(resumes)]
                fig, ax = plt.subplots(figsize=(11, 4.5)); x = np.arange(len(resumes))
                for i, (key, label) in enumerate((('hit_at_1', 'Hit@1'), ('hit_at_3', 'Hit@3'))):
                    ax.bar(x + (i-.5)*.35, [v[key]*100 if v.get(key) is not None else float('nan') for v in resumes], .35, label=label)
                ax.set_xticks(x, labels, rotation=35, ha='right'); ax.set_ylim(0, 100); ax.set_ylabel('% dos positivos'); ax.set_title('Recuperação por currículo — ponta a ponta'); ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1))
                sections.append(save_plot(fig, 'recuperacao_curriculos') + '<p>Identificadores substituídos por numeração local; denominadores pequenos. Não são exemplos textuais de candidatos.</p>')
    else:
        missing.append(str(args.semantic_dir / 'agregados_sem_dados_pessoais.json'))
        sections.append('<h2>Recuperação semântica</h2><p>Fonte agregada indisponível.</p>')

    manifest = read_json(args.manifest, sources)
    if manifest is None:
        missing.append(str(args.manifest))
        manifest = {}
    local = read_json(args.contextual_local, sources)
    operational = read_json(args.contextual_operational, sources)
    fixture = read_json('tests/fixtures/contextual_operational.json', sources)
    context = '<h2>Avaliador contextual — ensaio operacional; qualidade não validada</h2>'
    gguf = manifest.get('gguf', {}); retrieval = manifest.get('retrieval', {})
    context += f"<p>Modelo GGUF no manifesto: {safe(gguf.get('repository'))}; revisão {safe(gguf.get('revision'))}; runtime {safe(gguf.get('runtime_asset'))}, SHA-256 {safe(gguf.get('runtime_sha256'))}. Recuperação atual: {safe(retrieval.get('repository'))}, revisão {safe(retrieval.get('revision'))}. O commit executado nesses ensaios não está registrado no relatório. Qwen é o modelo; llama.cpp é o runtime CPU local. A escolha permite ensaio local, sem demonstrar superioridade sobre Llama.</p>"
    config = operational.get('configuration', {}) if operational else {}
    context += f"<p>Configuração observada: backend {safe(config.get('backend'))}; quantização {safe(config.get('quantization'))}; prompt {safe(config.get('prompt_version'))}; Top-k {safe(config.get('top_k'))}; limite de saída {safe(config.get('max_new_tokens'))} tokens. Código llama.cpp: contexto 4096, CPU, timeout HTTP 120 s; max_seconds={safe(config.get('max_seconds'))} é o limite de geração do adaptador Transformers e não um limite de geração aplicado ao llama.cpp.</p>"
    if local:
        context += f"<p>Ensaio local completo: {decimal(local.get('seconds'), 2)} s, {len(local.get('result', {}).get('details', []))} requisitos; tempo inclui etapas anteriores e não representa latência por chamada.</p>"
        write_csv('contextual_tempo_total.csv', ['Segundos', 'Requisitos'],
                  [[local.get('seconds'), len(local.get('result', {}).get('details', []))]])
    else:
        missing.append(str(args.contextual_local))
    if operational:
        fixture_map = {x['case']: x for x in fixture} if isinstance(fixture, list) else {}
        cases = []
        for case in operational.get('cases', []):
            verdict = case.get('verdict', {})
            # Citações só são divulgadas quando evidências coincidem com a fixture sintética versionada.
            original = fixture_map.get(case.get('case'), {})
            ids = verdict.get('evidence_ids', [])
            citations = ', '.join(ids)
            cases.append([case.get('case'), verdict.get('estado'), synthetic_evidence(case, original), citations, case.get('seconds')])
        write_csv('contextual_casos.csv', ['Caso', 'Decisão', 'Evidências sintéticas fornecidas', 'IDs citados', 'Segundos'], cases)
        display_cases = [row[:4] + [decimal(row[4], 2)] for row in cases]
        context += f'<p>{len(cases)} casos sintéticos; tempos medem cada chamada evaluate, sem carga do modelo. As evidências fornecidas são distintas das citadas; a presença de citações não prova correção.</p>' + table(['Caso', 'Decisão', 'Evidências fornecidas', 'IDs citados', 'Segundos'], display_cases)
    else:
        missing.append(str(args.contextual_operational))
    sections.append(context)

    sections.append('''<h2>Aderência documental — exemplo didático</h2><p>Dois obrigatórios pesam 2 cada e um desejável pesa 1: total 5. Se um obrigatório está sustentado, outro está parcial/indeterminado e o desejável não está sustentado, o mínimo confirmado é 2/5 = 40% e o máximo possível é (2+2)/5 = 80%. Parcial ou indeterminado permanece pendente; somente sustentado soma o peso completo. Aderência é regra de negócio, não acurácia, confiança nem probabilidade de contratação.</p>''')
    technologies = [
        ('DistilBERT NER', 'Entidades BIO', 'Base compacta; fine-tuning da equipe', 'Confira checkpoints e tabelas', 'Sim', 'SKILLS limitado; domínio e idioma'),
        ('Extrator híbrido', 'Seções e habilidades', 'Complementa NER com regras', 'Código da equipe', 'Não', 'Regras e extração podem perder evidências'),
        ('Sentence Transformers', 'Recuperação', 'Comparação semântica por embeddings', 'Histórico MPNet; atual MiniLM multilíngue', 'Não', 'Similaridade não comprova atendimento'),
        ('Qwen', 'Avaliação contextual', 'Ensaio local com instruções', 'GGUF no manifesto', 'Não', 'Qualidade não validada'),
        ('llama.cpp', 'Runtime local', 'Execução quantizada em CPU', 'Versão e hash do manifesto', 'Não', 'Tempo e recursos locais'),
        ('pypdf/pdfminer', 'Extração PDF', 'Ler texto de documentos', 'Pipeline de extração', 'Não', 'PDFs digitalizados e layout'),
        ('Flask', 'Aplicação web', 'Interface e rotas', 'Servidor local', 'Não', 'Depende de configuração'),
        ('Supabase', 'Banco e autenticação', 'Persistência e controle de acesso', 'RLS e migrações', 'Não', 'Depende de configuração externa')]
    sections.append('<h2>Tecnologias e justificativas</h2>' + table(['Tecnologia', 'Papel', 'Motivo', 'Configuração', 'Treinada?', 'Limitações'], technologies))
    sections.append('<p>DistilBERT recebeu fine-tuning pela equipe para NER. Sentence Transformer foi usado pré-treinado e avaliado em recuperação; Qwen foi usado pré-treinado em ensaios operacionais. Não há obrigação técnica de treinar todos os modelos: a adequação depende da tarefa e de avaliação apropriada.</p>')
    write_csv('tecnologias.csv', ['Tecnologia', 'Papel', 'Motivo', 'Configuração', 'Treinada?', 'Limitações'], technologies)
    preparation = read_json(args.ner_preparation, sources)
    splits = read_json(args.ner_split_manifest, sources)
    if not preparation:
        missing.append(str(args.ner_preparation))
    if not splits:
        missing.append(str(args.ner_split_manifest))
    prep = preparation or {}
    split_data = (splits or {}).get('split', {})
    augmentation = (splits or {}).get('augmentation', {})
    checks = (splits or {}).get('validation', {})
    sections.append('<h2>Dataset e preparação do NER</h2>' +
        '<p>Origem prevista pelo carregador do projeto: Dataturks <code>resume-entities-for-ner</code> no Kaggle. O manifesto local de splits não registra identificador, versão ou hash da fonte; a origem histórica específica não foi comprovada. Idioma e distribuição linguística não são declarados nos manifestos lidos; não foram comprovados.</p>' +
        f"<p>Manifesto local: {safe((splits or {}).get('input_resumes'))} currículos de entrada, seed {safe((splits or {}).get('seed'))}; treino original {safe(split_data.get('train_original'))}, validação {safe(split_data.get('validation'))}, teste {safe(split_data.get('test'))}. Treino após augmentation: {safe(split_data.get('train_after_augmentation'))}, incluindo {safe(augmentation.get('synthetic_resumes_created'))} sintéticos. O campo augmentation_applied_to registra {safe(checks.get('augmentation_applied_to'))}; vazamento entre splits registrado: {safe(checks.get('split_leakage_detected'))}.</p>" +
        f"<p>Metadados de preparação: base {safe(prep.get('model_name'))}; janela {safe(prep.get('max_length'))}; sobreposição {safe(prep.get('stride'))}; entidades {safe(', '.join(prep.get('entity_labels', [])) if prep.get('entity_labels') else None)}, representadas em BIO. O código de validação descreve correção de offsets, remoção de duplicatas e resolução de sobreposições; os registros lidos não demonstram individualmente cada alteração. Os relatórios não registram hash que comprove a identidade histórica do dataset; as contagens e o idioma não demonstram generalização para outras populações.</p>")
    training, training_args_rows, histories = [], [], {}
    for model, checkpoint in [('baseline', 'checkpoint-255'), ('augmented', 'checkpoint-745')]:
        path = args.ner_models / model / checkpoint / 'trainer_state.json'
        state = read_json(path, sources)
        if state:
            training.append([model, state.get('num_train_epochs'), state.get('train_batch_size'), state.get('global_step'), state.get('best_model_checkpoint')])
            histories[model] = [entry for entry in state.get('log_history', []) if entry.get('epoch') is not None and entry.get('eval_loss') is not None]
        else:
            missing.append(str(path))
        read_json(args.ner_models / model / 'best_model/config.json', sources)
        args_path = args.ner_models / model / 'best_model/training_args.bin'
        saved = read_training_args(args_path, sources)
        if saved is None:
            missing.append(str(args_path) + ' (ausente ou formato não reconhecido)')
            saved = {}
        training_args_rows.append([model, saved.get('per_device_train_batch_size'), saved.get('per_device_eval_batch_size'),
                                   saved.get('gradient_accumulation_steps'), saved.get('learning_rate'),
                                   saved.get('num_train_epochs'), saved.get('seed'), saved.get('_n_gpu')])
    history_plot = ''
    if any(len(items) >= 2 for items in histories.values()):
        from matplotlib.ticker import FormatStrFormatter
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for model, items in histories.items():
            if len(items) >= 2:
                ax.plot([item['epoch'] for item in items], [item['eval_loss'] for item in items], marker='o', label=model_labels[model])
        ax.set(xlabel='Época', ylabel='Perda de validação por janela', title='Perda de validação por época'); ax.legend()
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.4f'))
        history_plot = save_plot(fig, 'ner_historico_perda_janela')
    write_csv('ner_parametros_checkpoints.csv', ['Modelo', 'Batch treino/dispositivo', 'Batch avaliação/dispositivo',
              'Acumulação', 'Taxa de aprendizado', 'Épocas', 'Seed', 'GPUs registradas'], training_args_rows)
    sections.append('<h2>Proveniência e configuração NER</h2>' + table(['Modelo', 'Épocas registradas', 'Batch de treino registrado', 'Atualizações registradas', 'Melhor checkpoint'], training) +
        '<h3>Parâmetros registrados nos checkpoints</h3>' + table(['Modelo', 'Batch treino/dispositivo', 'Batch avaliação/dispositivo', 'Acumulação', 'Taxa de aprendizado', 'Épocas', 'Seed', 'GPUs registradas'], training_args_rows) + history_plot +
        '<p>Fontes: trainer_state.json e literais de training_args.bin dos melhores modelos, lidos sem desserializar objetos. Os arquivos locais registram os valores, mas a associação histórica ao relatório não é demonstrada por hash. GPUs registradas não comprovam sozinhas o dispositivo efetivamente utilizado. Revisão do modelo-base e commit da avaliação NER não foram comprovados. Histórico de validação do treino é por janela, diferente das métricas consolidadas acima.</p>' +
        '<p>O código atual possui defaults próprios (batch treino 4, avaliação 8 e acumulação 2); são apenas defaults e não descrevem os parâmetros registrados nesses checkpoints.</p>')
    baseline_test = ner.get(('baseline', 'test'), {}).get('f1')
    augmented_test = ner.get(('augmented', 'test'), {}).get('f1')
    augmented_train = ner.get(('augmented', 'train_original'), {}).get('f1')
    augmented_validation = ner.get(('augmented', 'validation'), {}).get('f1')
    if all(value is not None for value in (baseline_test, augmented_test, augmented_train, augmented_validation)):
        interpretation = (f'O F1 micro no teste passou de {percent(baseline_test)} no modelo de referência para '
                          f'{percent(augmented_test)} no modelo com aumento de dados, diferença de '
                          f'{(augmented_test-baseline_test)*100:.1f} pontos percentuais. No segundo modelo, '
                          f'o F1 de {percent(augmented_train)} no treino original é superior aos '
                          f'{percent(augmented_validation)} na validação e {percent(augmented_test)} no teste; '
                          'essa diferença indica desempenho menor fora do treino, sem determinar sua causa.')
    else:
        interpretation = 'Comparação de F1 e diferença entre treino e avaliação indisponíveis: faltam métricas consolidadas.'
    sections.append('<h2>Conclusão</h2><p>' + safe(interpretation) + ' A amostra é limitada, a identidade histórica dos dados não foi comprovada por hash e os treinamentos também tiveram quantidades diferentes de atualizações; não é possível atribuir o ganho exclusivamente ao augmentation nem generalizá-lo para outras populações. O ensaio contextual não valida a qualidade das decisões.</p>')
    sections.append('<h2>Fontes e limites</h2><p>Relatório offline; apenas agregados e exemplos sintéticos. Sem inferência nem conexão com banco. Os hashes de fontes em fontes.json foram calculados agora: identificam os arquivos lidos, mas não comprovam sua procedência histórica. Lacunas: ' + safe(', '.join(missing) if missing else 'nenhuma entre as fontes requeridas pelo leitor') + '.</p><p>Referências oficiais: <a href="https://huggingface.co/distilbert/distilbert-base-cased">DistilBERT</a>; <a href="https://huggingface.co/sentence-transformers/all-mpnet-base-v2">all-mpnet-base-v2</a>; <a href="https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2">MiniLM multilíngue</a>; <a href="https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507">Qwen3</a>; <a href="https://github.com/ggml-org/llama.cpp">llama.cpp</a>.</p>')
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    generator = Path(__file__)
    provenance = {'git_head': commit, 'generator_sha256': hashlib.sha256(generator.read_bytes()).hexdigest(),
                  'generator_commit_note': 'HEAD é a base; hash identifica o conteúdo executado, inclusive alterações não commitadas.',
                  'sources_hash_note': 'Hashes calculados na geração identificam arquivos atuais; não comprovam procedência histórica.',
                  'sources_sha256': sources, 'missing': missing}
    (output / 'fontes.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    page = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TalentMatch — resultados</title><style>body{font:16px system-ui,sans-serif;color:#172438;background:#f5f8fc;max-width:1200px;margin:auto;padding:24px}h1,h2{color:#173b68}h2{margin-top:3em}p{line-height:1.55}table{border-collapse:collapse;background:white;width:100%;margin:1em 0}td,th{border:1px solid #d2dce7;padding:8px;text-align:left}th{background:#e4edf7}figure{background:white;margin:1.5em 0;padding:12px}img{max-width:100%;height:auto}figcaption{font-size:.85em;color:#41556a}a{color:#174a80}</style><h1>TalentMatch AI — resultados e limites</h1><p>Relatório estático para apresentação acadêmica; não é validação geral dos modelos.</p>''' + ''.join(sections) + '</html>'
    (output / 'relatorio.html').write_text(page, encoding='utf-8')
    print(f'Relatório: {output / "relatorio.html"}; fontes: {len(sources)}; ausências: {len(missing)}')


if __name__ == '__main__':
    main()
