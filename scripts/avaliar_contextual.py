"""Experimento offline; exige rótulos humanos e nunca usa respostas simuladas."""
import argparse
from collections import Counter
import json
from pathlib import Path
from time import perf_counter
from src.matching.contextual import create_adapter, evaluate, settings


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('reports/contextual.json'))
    args = parser.parse_args()
    rows = json.loads(args.annotations.read_text(encoding='utf-8'))
    if any(not row.get('human_reviewed') for row in rows):
        parser.error('Revise os rótulos e marque human_reviewed antes de executar.')
    config = settings()
    if not config['revision']:
        parser.error('Defina CONTEXTUAL_MODEL_REVISION (versão/hash dos pesos locais).')
    adapter = create_adapter(config['model'])
    output = []
    for row in rows:
        start = perf_counter()
        verdict = evaluate(row['requirement'], row['evidence'], adapter)
        output.append(dict(id=row['id'], expected=row['proposed_label'], decision=verdict,
                           seconds=perf_counter() - start))
    report = dict(configuration=config, simulated=False, results=output,
        decisions_by_class=dict(Counter(r['decision']['estado'] for r in output)),
        false_support=sum(r['decision']['estado'] == 'sustentado' and r['expected'] != 'sustentado' for r in output),
        missed_support=sum(r['expected'] == 'sustentado' and r['decision']['estado'] != 'sustentado' for r in output),
        indeterminate_frequency=sum(r['decision']['estado'] == 'indeterminado' for r in output) / len(output),
        citation_validity=sum(not any('Inferência não validada' in s for s in r['decision']['limitacoes']) for r in output) / len(output),
        total_seconds=sum(r['seconds'] for r in output))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
