"""Reavalia rankings e anotações congelados, sem modelos ou inferência."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

VERSION = 'recuperacao-binaria-top3-1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def top3_distinct(ranking):
    if not isinstance(ranking, list):
        raise ValueError('Ranking ausente ou inválido.')
    seen, ordered = set(), []
    for entry in ranking:
        index = entry.get('input_index') if isinstance(entry, dict) else None
        if type(index) is not int or index < 0:
            raise ValueError('input_index inválido no ranking.')
        if index not in seen:
            seen.add(index)
            ordered.append(index)
    return ordered[:3]


def score_requirement(requirement, ranking, reviewed=True):
    top = top3_distinct(ranking)
    gold = requirement.get('acceptable_input_indices')
    result = dict(status=None, relevantes_anotados=None, relevantes_top3=None,
                  entradas_top3=len(top), ranking_curto=len(top) < 3,
                  hit_at_3=None, precision_at_3=None, recall_at_3=None, ndcg_at_3=None)
    if not reviewed or gold is None:
        result['status'] = 'pendente'
        return result
    if (not isinstance(gold, list) or any(type(i) is not int or i < 0 for i in gold)
            or len(set(gold)) != len(gold)):
        raise ValueError('Gold inválido.')
    failure = requirement.get('extraction_failure')
    original = requirement.get('evidence_in_original')
    if type(failure) is not bool or type(original) is not bool:
        raise ValueError('Estado de anotação incompleto.')
    if failure:
        if gold or not original:
            raise ValueError('Falha de extração incompatível com gold.')
        result.update(status='falha_extracao', hit_at_3=0)
    elif gold:
        if not original:
            raise ValueError('Gold positivo incompatível com evidência original.')
        matches = [i in set(gold) for i in top]
        count = sum(matches)
        dcg = sum(int(rel) / math.log2(position + 1) for position, rel in enumerate(matches, 1))
        ideal = sum(1 / math.log2(position + 1) for position in range(1, min(3, len(gold)) + 1))
        result.update(status='recuperavel', relevantes_anotados=len(gold), relevantes_top3=count,
                      hit_at_3=int(count > 0), precision_at_3=count / 3,
                      recall_at_3=count / len(gold), ndcg_at_3=dcg / ideal)
    elif original:
        raise ValueError('Positivo sem gold ou falha de extração.')
    else:
        result.update(status='sem_evidencia', relevantes_anotados=0, relevantes_top3=0)
    return result


def aggregate(rows):
    recoverable = [r for r in rows if r['status'] == 'recuperavel']
    losses = [r for r in rows if r['status'] == 'falha_extracao']
    positives = recoverable + losses
    def mean(group, key):
        return sum(r[key] for r in group) / len(group) if group else None
    return dict(total=len(rows), recuperaveis=len(recoverable), falhas_extracao=len(losses),
                sem_evidencia=sum(r['status'] == 'sem_evidencia' for r in rows),
                pendentes=sum(r['status'] == 'pendente' for r in rows),
                relevantes_anotados=sum(r['relevantes_anotados'] for r in recoverable),
                relevantes_top3=sum(r['relevantes_top3'] for r in recoverable),
                rankings_curtos=sum(r['ranking_curto'] for r in recoverable),
                rankings_curtos_positivos=sum(r['ranking_curto'] for r in positives),
                hit_denominador_ponta_a_ponta=len(positives), denominador_recuperavel=len(recoverable),
                hit_at_3_ponta_a_ponta=mean(positives, 'hit_at_3'),
                hit_at_3=mean(recoverable, 'hit_at_3'), precision_at_3=mean(recoverable, 'precision_at_3'),
                recall_at_3=mean(recoverable, 'recall_at_3'), ndcg_at_3=mean(recoverable, 'ndcg_at_3'))


def load_verified(result_path, sample_dir):
    """Verifica hashes originais de anotação/entradas e igualdade das linhas salvas."""
    result_path, sample_dir = Path(result_path), Path(sample_dir)
    data = json.loads(result_path.read_text(encoding='utf-8-sig'))
    if not isinstance(data.get('rows'), list) or not isinstance(data.get('annotations_sha256'), dict):
        raise ValueError('Resultados completos com rankings e hashes de anotação são necessários.')
    hashes = {str(result_path): hashlib.sha256(result_path.read_bytes()).hexdigest()}
    members = {x['resume_id']: x for x in data['manifest']['selected_resumes']}
    if set(members) != set(data['annotations_sha256']):
        raise ValueError('Manifesto e hashes de anotações incompatíveis.')
    annotations, input_counts = {}, {}
    for rid, expected in data['annotations_sha256'].items():
        folder = (sample_dir / rid).resolve()
        if not folder.is_relative_to(sample_dir.resolve()):
            raise ValueError('Identificador de currículo inválido.')
        paths = [folder / 'anotacoes.json', folder / 'entradas.json']
        values = []
        for path in paths:
            raw = path.read_bytes()
            hashes[str(path)] = hashlib.sha256(raw).hexdigest()
            values.append(json.loads(raw.decode('utf-8-sig')))
        annotation, inputs = values
        if fingerprint(annotation) != expected or annotation.get('resume_id') != rid:
            raise ValueError('Hash ou identificação da anotação incompatível.')
        input_hash = fingerprint(inputs)
        if input_hash != annotation.get('inputs_sha256') or input_hash != members[rid]['inputs_sha256']:
            raise ValueError('Hash das entradas incompatível.')
        if [item.get('input_index') for item in inputs] != list(range(len(inputs))):
            raise ValueError('Índices das entradas incompatíveis.')
        annotations[rid] = annotation
        input_counts[rid] = len(inputs)
    expected_keys = {(rid, req['id']) for rid, a in annotations.items() for req in a['requirements']}
    seen = set()
    for row in data['rows']:
        rid = row['resume_id']; req = row['requirement']; key = (rid, req['id'])
        if key in seen or key not in expected_keys:
            raise ValueError('Requisito duplicado ou sem anotação.')
        seen.add(key)
        annotation = annotations[rid]
        original = next(item for item in annotation['requirements'] if item['id'] == req['id'])
        if req != original or row.get('human_review') != annotation.get('human_review'):
            raise ValueError('Requisito ou revisão diverge da anotação congelada.')
        if row['result'].get('id') != req['id']:
            raise ValueError('Ranking associado a outro requisito.')
        ranking = row['result'].get('ranking')
        indices = top3_distinct(ranking)
        all_indices = [entry['input_index'] for entry in ranking]
        gold = req.get('acceptable_input_indices')
        if any(i >= input_counts[rid] for i in all_indices) or (gold is not None and any(type(i) is not int or i < 0 or i >= input_counts[rid] for i in gold)):
            raise ValueError('Índice fora das entradas congeladas.')
    if seen != expected_keys:
        raise ValueError('Resultados não cobrem todas as anotações.')
    return data, hashes


def calculate(data):
    rows = []
    for row in data['rows']:
        review = row.get('human_review', {})
        reviewed = review.get('completed') is True and bool(str(review.get('reviewer') or '').strip())
        item = score_requirement(row['requirement'], row['result']['ranking'], reviewed=reviewed)
        item.update(resume_id=row['resume_id'], requirement_id=row['requirement']['id'],
                    categoria=row['requirement'].get('category'))
        rows.append(item)
    ids = list(dict.fromkeys(row['resume_id'] for row in rows))
    categories = list(dict.fromkeys(row['categoria'] for row in rows))
    return dict(por_requisito=rows, geral=aggregate(rows),
                por_curriculo={rid: aggregate([r for r in rows if r['resume_id'] == rid]) for rid in ids},
                por_categoria={cat: aggregate([r for r in rows if r['categoria'] == cat]) for cat in categories})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('reports/avaliacao_semantica_ampliada_resultados/resultados.json'))
    parser.add_argument('--sample-dir', type=Path, default=Path('reports/avaliacao_semantica_ampliada'))
    parser.add_argument('--output-dir', type=Path, default=Path('reports/reavaliacao_recuperacao_top3'))
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    reports = Path('reports').resolve()
    if (output == reports or not output.is_relative_to(reports)
            or output.is_relative_to(args.sample_dir.resolve()) or args.sample_dir.resolve().is_relative_to(output)
            or output.is_relative_to(args.results.resolve().parent) or args.results.resolve().parent.is_relative_to(output)):
        raise ValueError('Saída deve ser diretório separado dentro de reports/.')
    data, hashes = load_verified(args.results, args.sample_dir)
    report = calculate(data)
    try:
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = None
    report['proveniencia'] = dict(versao=VERSION, ranking_commit=data['manifest'].get('commit'),
        ranking_pipeline=data['manifest'].get('pipeline_version'), reavaliador_head=head,
        reavaliador_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        fontes_sha256=hashes, nota='Hashes atuais identificam arquivos lidos; hashes congelados das anotações e entradas foram verificados.')
    report['convencoes'] = dict(
        unidade='requisito por currículo; média macro por consulta',
        ranking='primeiros três input_index distintos na ordem salva',
        relevancia='binária: somente acceptable_input_indices',
        hit='1 quando há pelo menos um relevante no Top-3; falhas de extração contam zero na visão ponta a ponta',
        precision='acertos/3 mesmo para ranking curto; somente positivos recuperáveis',
        recall='acertos/quantidade de todos os relevantes anotados; somente positivos recuperáveis',
        ndcg='DCG binário por log2(posição+1) dividido pelo DCG ideal de todos os relevantes anotados, limitado a três; somente positivos recuperáveis',
        exclusoes='negativos e pendentes excluídos dos positivos; falhas de extração são N/D para precision, recall e NDCG',
        limitacao='exaustividade das evidências anotadas não comprovada; relevância não é cosseno')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'metricas.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, values in [('por_requisito', report['por_requisito']),
                         ('por_curriculo', [dict(curriculo=k, **v) for k, v in report['por_curriculo'].items()]),
                         ('por_categoria', [dict(categoria=k, **v) for k, v in report['por_categoria'].items()]),
                         ('geral', [report['geral']])]:
        if values:
            with (output / f'{name}.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    print(json.dumps(report['geral'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
