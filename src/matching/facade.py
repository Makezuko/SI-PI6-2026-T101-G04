"""Fachada para o pipeline contextual completo de análise de currículos (GoF: Facade)."""
from __future__ import annotations

from threading import RLock

from src.data.clean import anonymize_resume_text
from src.data.privacy import (
    anonymize_for_analysis,
    latest_role,
    personal_spans,
    sanitize_semantic_inputs,
    uploaded_name_entities,
    valid_entity,
)
from src.matching.aggregators import AdherenceScoreStrategy
from src.matching.contextual import ContextualTechnicalError, evaluate_batch
from src.matching.documental_rules import unsafe
from src.matching.llm_justification import generate_llm_justification
from src.matching.semantic import aggregate_requirement_windows, compare
from src.matching.telemetry import event, execution_id, stage
from src.nlp.skills_extractor import extract_skills


class PipelineExecutionError(ValueError):
    """Erro de configuração ou falha técnica controlada durante a execução do pipeline."""


class TalentMatchPipelineFacade:
    """Unifica extração NER, anonimização, embeddings, avaliador contextual e justificativa."""

    def __init__(
        self,
        models_loader,
        contextual_loader,
        justification_generator=None,
        lock: RLock | None = None,
        strategy: AdherenceScoreStrategy | None = None,
    ) -> None:
        self._models_loader = models_loader
        self._contextual_loader = contextual_loader
        self._justification_generator = justification_generator or generate_llm_justification
        self._lock = lock or RLock()
        self._strategy = strategy

    def analyze_resume(
        self,
        job: dict,
        resume: dict,
        requirements: list[dict],
        config: dict,
        strategy: AdherenceScoreStrategy | None = None,
    ) -> dict:
        """Executa o fluxo contextual ponta a ponta e retorna o dicionário de resultado."""
        if not config["contextual"]["enabled"]:
            raise PipelineExecutionError(
                "Avaliador contextual não configurado. Prepare modelos e runtime e execute "
                "scripts/iniciar_contextual.ps1; consulte docs/avaliacao-contextual.md."
            )
        active_strategy = self._strategy if strategy is None else strategy
        raw = resume["raw_text"]

        with self._lock:
            with stage("input_extraction"):
                predictor, embedder = self._models_loader(
                    config["ner_model"], config["embedding_model"]
                )
                prediction = predictor.predict(text=raw, minimum_confidence=0.0)
                entities = prediction["entities"] + uploaded_name_entities(
                    raw, resume.get("anonymized_text")
                )
                anonymized_text = anonymize_for_analysis(raw, entities)
                spans = personal_spans(raw, entities)
                skills = [
                    {
                        "label": "SKILLS",
                        "text": anonymize_resume_text(entity["text"]),
                        "confidence": entity.get("confidence", 0),
                    }
                    for entity in entities
                    if entity["label"] == "SKILLS"
                    and valid_entity(raw, entity)
                    and not unsafe(
                        raw[
                            raw.rfind("\n", 0, entity["start"])
                            + 1 : raw.find("\n", entity["end"])
                            if "\n" in raw[entity["end"] :]
                            else len(raw)
                        ]
                    )
                    and not any(a < entity["end"] and entity["start"] < b for a, b in spans)
                ]
                inputs = extract_skills(text=anonymized_text, ner_entities=skills)[
                    "semantic_inputs"
                ]
                inputs = sanitize_semantic_inputs(inputs)
                safe_requirements = [
                    {k: v for k, v in item.items() if k != "condition"}
                    for item in requirements
                ]

            with stage("requirement_embeddings"):
                queries = embedder.encode(
                    [
                        {
                            "text": item["text"],
                            "source": "requirement",
                            "requirement_id": item["id"],
                        }
                        for item in safe_requirements
                    ]
                )
            with stage("requirement_window_validation"):
                query_vectors = aggregate_requirement_windows(safe_requirements, queries)
                event(
                    "ANALYSIS_SHAPE",
                    stage="requirement_window_validation",
                    count=len(requirements),
                    windows=len(queries["records"]),
                    dimension=len(query_vectors[0]),
                )
            if inputs:
                with stage("evidence_embeddings"):
                    embedded = embedder.encode(inputs)
                    event(
                        "ANALYSIS_SHAPE",
                        stage="evidence_embeddings",
                        count=len(inputs),
                        windows=len(embedded["records"]),
                        dimension=len(embedded["embeddings"][0]),
                    )
                with stage("semantic_comparison"):
                    results, _ = compare(safe_requirements, query_vectors, embedded)
            else:
                results = [{"id": item["id"], "ranking": []} for item in safe_requirements]

        with self._lock:
            ctx = config["contextual"]
            event("MODEL_LOAD_START")
            try:
                adapter = self._contextual_loader(
                    ctx["model"],
                    ctx["revision"],
                    ctx["backend"],
                    ctx["runtime"],
                    ctx["runtime_revision"],
                )
                if adapter is None:
                    raise ContextualTechnicalError("MODEL_LOAD_ERROR")
                event("MODEL_LOAD_OK")
                result = evaluate_batch(
                    safe_requirements,
                    results,
                    inputs,
                    adapter,
                    strategy=active_strategy,
                )
            except ContextualTechnicalError as error:
                event("ANALYSIS_TECHNICAL_ERROR", error_code=error.code)
                raise PipelineExecutionError(
                    f"Falha técnica contextual [{error.code}]. Execução {execution_id.get()}. Nenhuma nova análise foi salva."
                ) from None

        result["extraction_diagnostic"] = {
            "requirements_received": [item["id"] for item in safe_requirements],
            "entries_by_source": {
                source: sum(entry["source"] == source for entry in inputs)
                for source in sorted({entry["source"] for entry in inputs})
            },
            "entries_considered": len(inputs),
        }
        result["last_role"] = latest_role(raw, entities)
        result["execution_id"] = execution_id.get()
        result["llm_justification"] = self._justification_generator(
            job,
            anonymized_text=anonymized_text,
            candidate=resume,
            analysis_result=result,
        )
        return result
