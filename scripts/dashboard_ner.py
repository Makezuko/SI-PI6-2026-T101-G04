
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# 1. CONFIGURAÇÕES
# ============================================================

st.set_page_config(
    page_title="Dashboard - Avaliação NER",
    page_icon="📊",
    layout="wide"
)

# Mantém a leitura dos relatórios locais na raiz do repositório.
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "ner_consolidated"

MODELS = {
    "Baseline": "baseline",
    "Augmented": "augmented"
}


# ============================================================
# 2. FUNÇÕES DE LEITURA
# ============================================================

def load_json(path):
    """Carrega um arquivo JSON, retornando None em caso de erro."""

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    except (json.JSONDecodeError, OSError) as error:
        st.warning(f"Não foi possível ler {path.name}: {error}")
        return None


def get_model_path(model, split):
    """Retorna o diretório de avaliação de um modelo."""

    model_dir = MODELS[model]

    return REPORTS_DIR / model_dir / split


def get_available_splits():
    """Identifica os conjuntos disponíveis nos dois modelos."""

    baseline_dir = REPORTS_DIR / "baseline"
    augmented_dir = REPORTS_DIR / "augmented"

    if not baseline_dir.is_dir() or not augmented_dir.is_dir():
        return []

    baseline_splits = {
        folder.name
        for folder in baseline_dir.iterdir()
        if folder.is_dir()
    }

    augmented_splits = {
        folder.name
        for folder in augmented_dir.iterdir()
        if folder.is_dir()
    }

    return sorted(baseline_splits.intersection(augmented_splits))


def load_model_data(model, split):
    """Carrega os arquivos de avaliação de um modelo."""

    folder = get_model_path(model, split)

    return {
        "metrics": load_json(folder / "metrics.json"),
        "entity_metrics": load_json(folder / "entity_metrics.json"),
        "classification_report": load_json(
            folder / "classification_report.json"
        ),
        "confusion_matrix": load_json(
            folder / "confusion_matrix.json"
        ),
        "confusion_matrix_normalized": load_json(
            folder / "confusion_matrix_normalized.json"
        ),
        "error_examples": load_json(
            folder / "error_examples.json"
        ),
        "folder": folder
    }


# ============================================================
# 3. FUNÇÕES AUXILIARES PARA MÉTRICAS
# ============================================================

def normalize_metric_name(name):
    """Padroniza nomes de métricas."""

    return str(name).lower().replace("-", "_").replace(" ", "_")


def find_metric(data, possible_names):
    """Procura uma métrica considerando diferentes nomes possíveis."""

    if not isinstance(data, dict):
        return None

    normalized = {
        normalize_metric_name(key): value
        for key, value in data.items()
    }

    for name in possible_names:
        key = normalize_metric_name(name)

        if key in normalized:
            value = normalized[key]

            if isinstance(value, (int, float)):
                return value

    return None


def extract_main_metrics(data):
    """Extrai as principais métricas do arquivo metrics.json."""

    if not isinstance(data, dict):
        return {}

    return {
        "Precision": find_metric(
            data,
            ["precision", "eval_precision", "micro_precision"]
        ),
        "Recall": find_metric(
            data,
            ["recall", "eval_recall", "micro_recall"]
        ),
        "F1-score": find_metric(
            data,
            ["f1", "f1_score", "eval_f1", "micro_f1"]
        ),
        "Accuracy": find_metric(
            data,
            ["accuracy", "eval_accuracy"]
        ),
        "Loss": find_metric(
            data,
            ["loss", "eval_loss"]
        )
    }


def find_entity_metrics(data):
    """Localiza as métricas por entidade em diferentes formatos JSON."""

    if not isinstance(data, dict):
        return {}

    # Alguns relatórios armazenam as entidades dentro de uma chave.
    for key in [
        "entities",
        "entity_metrics",
        "per_entity",
        "classification_report"
    ]:
        value = data.get(key)

        if isinstance(value, dict):
            return value

    return data


def extract_entity_dataframe(data, model_name):
    """Transforma as métricas por entidade em DataFrame."""

    entities = find_entity_metrics(data)

    if not isinstance(entities, dict):
        return pd.DataFrame()

    rows = []

    ignored_keys = {
        "accuracy",
        "macro avg",
        "weighted avg",
        "micro avg",
        "samples avg",
        "overall",
        "total"
    }

    for entity, values in entities.items():

        if not isinstance(values, dict):
            continue

        if entity.lower() in ignored_keys:
            continue

        precision = find_metric(
            values,
            ["precision", "p"]
        )

        recall = find_metric(
            values,
            ["recall", "r"]
        )

        f1 = find_metric(
            values,
            ["f1", "f1_score", "f1-score"]
        )

        support = find_metric(
            values,
            ["support", "total"]
        )

        if precision is None and recall is None and f1 is None:
            continue

        rows.append({
            "Entidade": entity,
            "Modelo": model_name,
            "Precision": precision,
            "Recall": recall,
            "F1-score": f1,
            "Support": support
        })

    return pd.DataFrame(rows)


def format_percentage(value):
    """Formata valores entre 0 e 1 como porcentagem."""

    if value is None:
        return "N/A"

    if isinstance(value, (int, float)):
        if 0 <= value <= 1:
            return f"{value * 100:.2f}%"

        return f"{value:.2f}%"

    return str(value)


# ============================================================
# 4. CABEÇALHO
# ============================================================

st.title("📊 Dashboard de Avaliação NER")

st.markdown(
    """
    Comparação entre os modelos **Baseline** e **Augmented**
    utilizados na tarefa de Reconhecimento de Entidades Nomeadas
    (NER) em currículos.
    """
)

st.divider()


# ============================================================
# 5. VERIFICAÇÃO DOS RELATÓRIOS
# ============================================================

if not REPORTS_DIR.is_dir():

    st.error(
        f"""
        Diretório de relatórios não encontrado:

        `{REPORTS_DIR}`

        Verifique se a pasta `ner_consolidated` está dentro de `reports`.
        """
    )

    st.stop()


available_splits = get_available_splits()

if not available_splits:

    st.error(
        """
        Não foram encontrados conjuntos de avaliação compartilhados
        entre baseline e augmented.

        Verifique se existem as pastas:

        - reports/ner_consolidated/baseline
        - reports/ner_consolidated/augmented
        """
    )

    st.stop()


# ============================================================
# 6. SELEÇÃO DO CONJUNTO DE AVALIAÇÃO
# ============================================================

st.sidebar.header("Configurações")

selected_split = st.sidebar.selectbox(
    "Conjunto de avaliação",
    available_splits,
    index=(
        available_splits.index("test")
        if "test" in available_splits
        else 0
    )
)

st.sidebar.caption(
    "Os dois modelos serão comparados utilizando o mesmo conjunto."
)


# ============================================================
# 7. CARREGAMENTO DOS DADOS
# ============================================================

baseline_data = load_model_data(
    "Baseline",
    selected_split
)

augmented_data = load_model_data(
    "Augmented",
    selected_split
)

baseline_metrics = extract_main_metrics(
    baseline_data["metrics"]
)

augmented_metrics = extract_main_metrics(
    augmented_data["metrics"]
)

if baseline_data["metrics"] is None:
    st.error(
        f"Arquivo metrics.json não encontrado para Baseline: "
        f"{baseline_data['folder']}"
    )
    st.stop()

if augmented_data["metrics"] is None:
    st.error(
        f"Arquivo metrics.json não encontrado para Augmented: "
        f"{augmented_data['folder']}"
    )
    st.stop()


st.success(
    f"Relatórios carregados: conjunto **{selected_split}**."
)


# ============================================================
# 8. COMPARAÇÃO GERAL DOS MODELOS
# ============================================================

st.header("1. Comparação geral")

metric_names = [
    "Precision",
    "Recall",
    "F1-score",
    "Accuracy",
    "Loss"
]

comparison_rows = []

for metric in metric_names:

    baseline_value = baseline_metrics.get(metric)
    augmented_value = augmented_metrics.get(metric)

    comparison_rows.append({
        "Métrica": metric,
        "Baseline": baseline_value,
        "Augmented": augmented_value
    })

comparison_df = pd.DataFrame(comparison_rows)

display_df = comparison_df.copy()

for column in ["Baseline", "Augmented"]:

    display_df[column] = display_df[column].apply(
        lambda value: (
            f"{value:.4f}"
            if isinstance(value, (int, float))
            else "N/A"
        )
    )

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# 9. CARDS DE MÉTRICAS
# ============================================================

st.subheader("Principais indicadores")

metric_cards = [
    ("Precision", "Precisão"),
    ("Recall", "Revocação"),
    ("F1-score", "F1-score"),
    ("Accuracy", "Acurácia")
]

columns = st.columns(4)

for column, (metric, label) in zip(columns, metric_cards):

    baseline_value = baseline_metrics.get(metric)
    augmented_value = augmented_metrics.get(metric)

    with column:

        st.metric(
            label=label,
            value=format_percentage(augmented_value),
            delta=(
                f"{(augmented_value - baseline_value) * 100:+.2f} p.p."
                if isinstance(baseline_value, (int, float))
                and isinstance(augmented_value, (int, float))
                and 0 <= baseline_value <= 1
                and 0 <= augmented_value <= 1
                else None
            )
        )

        st.caption(
            f"Baseline: {format_percentage(baseline_value)}"
        )


# ============================================================
# 10. GRÁFICO DE COMPARAÇÃO DAS MÉTRICAS
# ============================================================

st.divider()

st.header("2. Comparação visual das métricas")

plot_rows = []

for metric in [
    "Precision",
    "Recall",
    "F1-score",
    "Accuracy"
]:

    for model_name, metrics in [
        ("Baseline", baseline_metrics),
        ("Augmented", augmented_metrics)
    ]:

        value = metrics.get(metric)

        if isinstance(value, (int, float)):

            plot_rows.append({
                "Métrica": metric,
                "Modelo": model_name,
                "Valor": value * 100 if 0 <= value <= 1 else value
            })


if plot_rows:

    plot_df = pd.DataFrame(plot_rows)

    fig = px.bar(
        plot_df,
        x="Métrica",
        y="Valor",
        color="Modelo",
        barmode="group",
        text_auto=".2f",
        title="Desempenho geral dos modelos",
        labels={
            "Valor": "Valor (%)",
            "Métrica": "Métrica",
            "Modelo": "Modelo"
        }
    )

    fig.update_layout(
        yaxis_title="Valor (%)",
        xaxis_title="",
        legend_title="Modelo",
        height=450
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

else:

    st.info("Não existem métricas suficientes para gerar o gráfico.")


# ============================================================
# 11. COMPARAÇÃO DA LOSS
# ============================================================

st.header("3. Loss")

loss_rows = []

for model_name, metrics in [
    ("Baseline", baseline_metrics),
    ("Augmented", augmented_metrics)
]:

    loss = metrics.get("Loss")

    if isinstance(loss, (int, float)):

        loss_rows.append({
            "Modelo": model_name,
            "Loss": loss
        })


if loss_rows:

    loss_df = pd.DataFrame(loss_rows)

    fig_loss = px.bar(
        loss_df,
        x="Modelo",
        y="Loss",
        color="Modelo",
        text_auto=".4f",
        title="Comparação da função de perda"
    )

    fig_loss.update_layout(
        showlegend=False,
        height=350
    )

    st.plotly_chart(
        fig_loss,
        use_container_width=True
    )

else:

    st.info("Métrica de Loss não encontrada nos relatórios.")


# ============================================================
# 12. MÉTRICAS POR ENTIDADE
# ============================================================

st.divider()

st.header("4. Desempenho por entidade")

baseline_entities = extract_entity_dataframe(
    baseline_data["entity_metrics"]
    or baseline_data["classification_report"],
    "Baseline"
)

augmented_entities = extract_entity_dataframe(
    augmented_data["entity_metrics"]
    or augmented_data["classification_report"],
    "Augmented"
)

entity_df = pd.concat(
    [
        baseline_entities,
        augmented_entities
    ],
    ignore_index=True
)

if not entity_df.empty:

    available_entity_metrics = [
        metric
        for metric in ["Precision", "Recall", "F1-score"]
        if entity_df[metric].notna().any()
    ]

    selected_entity_metric = st.selectbox(
        "Métrica por entidade",
        available_entity_metrics,
        index=(
            available_entity_metrics.index("F1-score")
            if "F1-score" in available_entity_metrics
            else 0
        )
    )

    entity_plot = entity_df.dropna(
        subset=[selected_entity_metric]
    ).copy()

    entity_plot["Valor (%)"] = entity_plot[
        selected_entity_metric
    ].apply(
        lambda value: value * 100 if 0 <= value <= 1 else value
    )

    fig_entities = px.bar(
        entity_plot,
        x="Entidade",
        y="Valor (%)",
        color="Modelo",
        barmode="group",
        text_auto=".2f",
        title=f"{selected_entity_metric} por entidade"
    )

    fig_entities.update_layout(
        xaxis_title="Entidade",
        yaxis_title="Valor (%)",
        height=550
    )

    st.plotly_chart(
        fig_entities,
        use_container_width=True
    )

    st.subheader("Tabela de métricas por entidade")

    entity_display = entity_df.copy()

    for metric in ["Precision", "Recall", "F1-score"]:

        entity_display[metric] = entity_display[metric].apply(
            lambda value: (
                f"{value:.4f}"
                if isinstance(value, (int, float))
                else "N/A"
            )
        )

    st.dataframe(
        entity_display,
        use_container_width=True,
        hide_index=True
    )

else:

    st.warning(
        """
        Não foram encontradas métricas por entidade.

        Verifique o conteúdo dos arquivos entity_metrics.json
        e classification_report.json.
        """
    )


# ============================================================
# 13. MATRIZ DE CONFUSÃO
# ============================================================

st.divider()

st.header("5. Matrizes de confusão")


def extract_matrix(data):
    """Extrai uma matriz de confusão de diferentes estruturas JSON."""

    if data is None:
        return None, None

    if isinstance(data, list):
        return data, None

    if isinstance(data, dict):

        labels = (
            data.get("labels")
            or data.get("classes")
            or data.get("entity_labels")
        )

        for key in [
            "confusion_matrix",
            "matrix",
            "normalized_matrix",
            "normalized_confusion_matrix"
        ]:

            matrix = data.get(key)

            if isinstance(matrix, list):
                return matrix, labels

        # Alguns arquivos contêm diretamente a matriz como lista de listas.
        if data and all(
            isinstance(value, list)
            for value in data.values()
        ):

            return list(data.values()), labels

    return None, None


def show_confusion_matrix(data, title):

    matrix, labels = extract_matrix(data)

    if matrix is None:

        st.info(
            f"Matriz de confusão não encontrada para {title}."
        )

        return

    try:

        matrix_df = pd.DataFrame(matrix)

        fig = px.imshow(
            matrix_df,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="Blues",
            title=title
        )

        if labels and len(labels) == len(matrix):
            fig.update_xaxes(
                tickmode="array",
                tickvals=list(range(len(labels))),
                ticktext=labels
            )

            fig.update_yaxes(
                tickmode="array",
                tickvals=list(range(len(labels))),
                ticktext=labels
            )

        fig.update_layout(
            xaxis_title="Classe predita",
            yaxis_title="Classe real",
            height=650
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    except (ValueError, TypeError) as error:

        st.warning(
            f"Não foi possível exibir a matriz: {error}"
        )


matrix_col1, matrix_col2 = st.columns(2)

with matrix_col1:

    st.subheader("Baseline")

    baseline_matrix = (
        baseline_data["confusion_matrix_normalized"]
        or baseline_data["confusion_matrix"]
    )

    show_confusion_matrix(
        baseline_matrix,
        "Matriz de confusão - Baseline"
    )


with matrix_col2:

    st.subheader("Augmented")

    augmented_matrix = (
        augmented_data["confusion_matrix_normalized"]
        or augmented_data["confusion_matrix"]
    )

    show_confusion_matrix(
        augmented_matrix,
        "Matriz de confusão - Augmented"
    )


# ============================================================
# 14. EXEMPLOS DE ERROS
# ============================================================

st.divider()

st.header("6. Exemplos de erros")

error_col1, error_col2 = st.columns(2)

for column, model_name, model_data in [
    (error_col1, "Baseline", baseline_data),
    (error_col2, "Augmented", augmented_data)
]:

    with column:

        st.subheader(model_name)

        errors = model_data["error_examples"]

        if errors is None:

            st.info(
                "Arquivo de exemplos de erros não encontrado."
            )

        elif isinstance(errors, list):

            st.write(
                f"Quantidade de exemplos: {len(errors)}"
            )

            st.json(errors[:10])

        else:

            st.json(errors)


# ============================================================
# 15. INFORMAÇÕES TÉCNICAS
# ============================================================

st.divider()

st.header("7. Informações técnicas")

st.markdown(
    """
    **Metodologia de avaliação**

    - Comparação entre os modelos Baseline e Augmented.
    - Avaliação utilizando o mesmo conjunto de dados.
    - Métricas gerais e métricas detalhadas por entidade.
    - Visualização das matrizes de confusão, quando disponíveis.
    """
)

with st.expander("Ver caminhos dos arquivos utilizados"):

    st.write("Diretório de relatórios:")

    st.code(str(REPORTS_DIR))

    st.write("Baseline:")

    st.code(str(baseline_data["folder"]))

    st.write("Augmented:")

    st.code(str(augmented_data["folder"]))


st.caption(
    "Dashboard de avaliação dos modelos NER."
)
