import html
import json
from pathlib import Path


BASELINE_PATH = Path(
    "reports/semantic_baseline_cv001/resultados.json"
)

V4_PATH = Path(
    "reports/semantic_segmentation_v4_cv001_anotado/resultados.json"
)

OUTPUT_DIR = Path("reports/comparacao_v2_v4_cv001")


def load_json(path):
    """Carrega um arquivo JSON."""
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}\n"
            "Execute primeiro os relatórios individuais."
        )

    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value):
    """Formata métricas numéricas."""
    if value is None:
        return "N/A"

    return f"{value:.3f}"


def get_top1(result):
    """Retorna a melhor evidência do requisito."""
    ranking = result.get("ranking", [])

    if not ranking:
        return None

    return ranking[0]


def get_metric_by_id(report, requirement_id):
    """Encontra o diagnóstico de um requisito."""
    for item in report["metrics"]["per_requirement"]:
        if item["id"] == requirement_id:
            return item

    return {}


def format_rank(diagnostic):
    """Formata a posição da primeira evidência aceitável."""
    status = diagnostic.get("annotation_status", "")

    if status == "positivo anotado":
        rank = diagnostic.get("first_relevant_rank")

        if rank is None:
            return "Não recuperada"

        return str(rank)

    if status == "sem evidência anotada":
        return "Sem evidência suficiente"

    return "Não anotado"


def render_evidence(evidence):
    """Transforma uma evidência em HTML."""
    if evidence is None:
        return "<p>Nenhuma evidência encontrada.</p>"

    score = fmt(evidence.get("similarity"))
    index = evidence.get("input_index", "?")
    source = html.escape(str(evidence.get("source", "N/A")))
    text = html.escape(str(evidence.get("text", "")))

    return (
        f"<div class='evidence'>"
        f"<b>Score: {score} | I{index} | {source}</b>"
        f"<p>{text}</p>"
        f"</div>"
    )


def render_top3(result):
    """Exibe as três melhores evidências."""
    if result is None:
        return "<p>Requisito não encontrado no relatório.</p>"

    ranking = result.get("ranking", [])

    if not ranking:
        return "<p>Nenhuma evidência encontrada.</p>"

    items = []

    for item in ranking[:3]:
        items.append(
            "<li>"
            f"<b>{fmt(item.get('similarity'))} "
            f"| I{item.get('input_index', '?')} "
            f"| {html.escape(str(item.get('source', 'N/A')))}</b>"
            f"<p>{html.escape(str(item.get('text', '')))}</p>"
            "</li>"
        )

    return "<ol>" + "".join(items) + "</ol>"


def metric_card(title, value):
    return (
        "<div class='card'>"
        f"<span>{html.escape(title)}</span>"
        f"<strong>{html.escape(fmt(value))}</strong>"
        "</div>"
    )


def main():
    baseline = load_json(BASELINE_PATH)
    v4 = load_json(V4_PATH)

    baseline_results = {
        row["id"]: row
        for row in baseline["results"]
    }

    v4_results = {
        row["id"]: row
        for row in v4["results"]
    }

    baseline_requirements = {
        row["id"]: row
        for row in baseline["requirements"]
    }

    v4_requirements = {
        row["id"]: row
        for row in v4["requirements"]
    }

    all_ids = list(dict.fromkeys(
        list(baseline_results) + list(v4_results)
    ))

    # Métricas de cada execução.
    baseline_metrics = baseline["metrics"]
    v4_metrics = v4["metrics"]

    metric_rows = []

    metric_names = [
        ("total_requirements", "Total de requisitos"),
        ("evaluated_positive_count", "Requisitos positivos avaliados"),
        ("no_evidence_count", "Requisitos sem evidência suficiente"),
        ("unannotated_count", "Requisitos não anotados"),
        ("hit_at_1", "Hit@1"),
        ("hit_at_3", "Hit@3"),
        ("mrr", "MRR"),
    ]

    for key, label in metric_names:
        metric_rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td>{fmt(baseline_metrics.get(key))}</td>"
            f"<td>{fmt(v4_metrics.get(key))}</td>"
            "</tr>"
        )

    requirement_sections = []

    for requirement_id in all_ids:
        baseline_result = baseline_results.get(requirement_id)
        v4_result = v4_results.get(requirement_id)

        requirement = (
            baseline_requirements.get(requirement_id)
            or v4_requirements.get(requirement_id)
            or {}
        )

        requirement_text = (
            requirement.get("text")
            or (
                baseline_result or v4_result
            ).get("requirement", "")
        )

        baseline_top1 = (
            get_top1(baseline_result)
            if baseline_result else None
        )

        v4_top1 = (
            get_top1(v4_result)
            if v4_result else None
        )

        baseline_score = (
            baseline_top1.get("similarity")
            if baseline_top1 else None
        )

        v4_score = (
            v4_top1.get("similarity")
            if v4_top1 else None
        )

        if baseline_score is not None and v4_score is not None:
            score_difference = v4_score - baseline_score
        else:
            score_difference = None

        baseline_diagnostic = get_metric_by_id(
            baseline, requirement_id
        )

        v4_diagnostic = get_metric_by_id(
            v4, requirement_id
        )

        baseline_rank = format_rank(baseline_diagnostic)
        v4_rank = format_rank(v4_diagnostic)

        requirement_sections.append(
            f"""
            <section class="requirement">
                <h2>{html.escape(requirement_id)} — 
                    {html.escape(requirement_text)}</h2>

                <div class="comparison">
                    <div>
                        <h3>Baseline (v2)</h3>
                        <p><b>Top 1:</b> {fmt(baseline_score)}</p>
                        {render_evidence(baseline_top1)}
                        <p><b>Posição da primeira evidência aceitável:</b>
                            {html.escape(baseline_rank)}</p>
                        <details>
                            <summary>Ver Top 3 do baseline</summary>
                            {render_top3(baseline_result)}
                        </details>
                    </div>

                    <div>
                        <h3>Versão segmentada (v4)</h3>
                        <p><b>Top 1:</b> {fmt(v4_score)}</p>
                        {render_evidence(v4_top1)}
                        <p><b>Posição da primeira evidência aceitável:</b>
                            {html.escape(v4_rank)}</p>
                        <details>
                            <summary>Ver Top 3 da v4</summary>
                            {render_top3(v4_result)}
                        </details>
                    </div>
                </div>

                <p class="difference">
                    Diferença numérica do score Top 1 (v4 − v2):
                    <b>{fmt(score_difference)}</b>
                </p>
            </section>
            """
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparação semântica — v2 × v4</title>

<style>
body {{
    font: 16px system-ui, sans-serif;
    background: #f3f6fb;
    color: #17233c;
    margin: 0;
}}
main {{
    max-width: 1250px;
    margin: auto;
    padding: 28px;
}}
section, .notice {{
    background: white;
    padding: 22px;
    border-radius: 14px;
    margin: 20px 0;
}}
.notice {{
    border-left: 5px solid #d97706;
}}
.cards {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
}}
.card {{
    flex: 1;
    min-width: 140px;
    background: #eaf0ff;
    border-radius: 12px;
    padding: 16px;
}}
.card span {{
    display: block;
    font-size: 14px;
}}
.card strong {{
    display: block;
    font-size: 28px;
    margin-top: 6px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
}}
td, th {{
    text-align: left;
    vertical-align: top;
    border-bottom: 1px solid #dbe2ed;
    padding: 12px;
}}
.comparison {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
}}
.comparison > div {{
    background: #f8fafc;
    padding: 16px;
    border-radius: 10px;
    overflow-wrap: anywhere;
}}
.evidence {{
    background: white;
    border: 1px solid #dbe2ed;
    border-radius: 8px;
    padding: 12px;
    margin: 12px 0;
    white-space: normal;
}}
.difference {{
    color: #475569;
    font-size: 14px;
}}
details {{
    margin-top: 14px;
}}
li {{
    margin: 12px 0;
    overflow-wrap: anywhere;
}}
@media (max-width: 800px) {{
    .comparison {{
        grid-template-columns: 1fr;
    }}
    main {{
        padding: 14px;
    }}
}}
</style>
</head>

<body>
<main>
    <h1>Comparação semântica: baseline v2 × segmentação v4</h1>

    <p>
         
        Modelo: {html.escape(str(baseline.get("model_name", "N/A")))}
        
    </p>

    <div class="notice">
        <b>Como interpretar este relatório</b>
        <p>
            A v2 usa a extração e os chunks originais; a v4 usa
            habilidades e responsabilidades segmentadas. Os scores Top 1
            mostram as correspondências recuperadas em cada versão.
        </p>
        <p>
            As anotações da v4 foram revisadas depois da inspeção do ranking.
            Portanto, os valores Hit@1, Hit@3 e MRR abaixo são diagnósticos
            preliminares e não constituem uma comparação independente.
            Para uma comparação rigorosa, os critérios de relevância precisam
            ser revisados da mesma forma nas duas versões.
        </p>
        <p>
            Similaridade de cosseno não é probabilidade e não comprova
            domínio de uma competência.
        </p>
    </div>

    <section>
        <h2>Métricas lado a lado</h2>
        <div style="overflow-x:auto">
            <table>
                <thead>
                    <tr>
                        <th>Métrica</th>
                        <th>Baseline v2</th>
                        <th>Segmentação v4</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(metric_rows)}
                </tbody>
            </table>
        </div>
    </section>

    <section>
        <h2>Comparação por requisito</h2>
        <p>
            Compare o texto recuperado, o score e a posição da evidência
            aceitável. Use “Ver Top 3” para inspecionar as alternativas.
        </p>
    </section>

    {"".join(requirement_sections)}

    <section>
        <h2>Próximos passos</h2>
        <p>
            Revisar as evidências aceitáveis com os mesmos critérios,
            validar requisitos sem evidência suficiente e ampliar a avaliação
            para outros currículos e vagas.
        </p>
    </section>
</main>
</body>
</html>
"""

    output_path = OUTPUT_DIR / "relatorio_comparativo.html"

    output_path.write_text(
        report_html,
        encoding="utf-8",
    )

    print("Relatório comparativo gerado:")
    print(output_path)


if __name__ == "__main__":
    main()
