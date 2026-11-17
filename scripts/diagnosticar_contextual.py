"""Executa o avaliador existente em três fixtures sintéticas reais, sem Flask/banco."""
import json
import logging
import os
from pathlib import Path
from time import perf_counter
from src.matching.contextual import create_adapter, evaluate, settings
from src.matching.telemetry import new_execution, execution_id


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    manifest = json.loads(Path('models/contextual/manifest.json').read_text(encoding='utf-8'))
    model = manifest['gguf']
    os.environ.update(CONTEXTUAL_EVALUATOR='experimental', CONTEXTUAL_BACKEND='llama_cpp',
                      CONTEXTUAL_MODEL_PATH=model['path'], CONTEXTUAL_MODEL_REVISION=model['revision'],
                      CONTEXTUAL_RUNTIME_PATH=model['runtime'], CONTEXTUAL_RUNTIME_REVISION=model['runtime_sha256'])
    token = new_execution()
    adapter = create_adapter()
    report = dict(simulated=False, database_used=False, run_id=execution_id.get(),
                  configuration=settings(), cases=[])
    try:
        cases = json.loads(Path('tests/fixtures/contextual_operational.json').read_text(encoding='utf-8'))
        for case in cases:
            start = perf_counter()
            verdict = evaluate(case['requirement'], case['evidence'], adapter, strict=True)
            row = dict(case=case['case'], evidence=case['evidence'], verdict=verdict,
                       seconds=round(perf_counter() - start, 3))
            report['cases'].append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)
        output = Path('reports/contextual-operational.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        adapter.close()
        execution_id.reset(token)


if __name__ == '__main__':
    main()
