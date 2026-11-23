"""Testes unitários dos padrões GoF (Strategy, Factory Method e Facade)."""
import json
import os
import unittest
from unittest.mock import patch

from src.matching.aggregators import ProvisionalWeightedAdherence
from src.matching.contextual import create_adapter
from src.matching.facade import PipelineExecutionError, TalentMatchPipelineFacade
from src.matching.factory import (
    ContextualAdapterFactory,
    LlamaCppAdapterFactory,
    TransformersAdapterFactory,
    get_contextual_adapter_factory,
)


class _FakePredictor:
    def __init__(self, entities):
        self._entities = entities

    def predict(self, text: str, minimum_confidence: float = 0.0) -> dict:
        return {"entities": list(self._entities)}


class _FakeEmbedder:
    def encode(self, items: list[dict]) -> dict:
        records, vectors = [], []
        for idx, item in enumerate(items):
            records.append(dict(item, input_index=idx, chunk_index=0))
            text = item["text"].lower()
            if "python" in text:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.6, 0.8])
        return {"records": records, "embeddings": vectors}


class _FakeContextualAdapter:
    def generate(self, payload: dict) -> str:
        text = payload.get("requisito", "").lower()
        evidences = payload.get("evidencias", [])
        matching = [entry["id"] for entry in evidences if text in entry["text"].lower()]
        if matching:
            return json.dumps(
                {
                    "estado": "sustentado",
                    "evidence_ids": matching[:1],
                    "justificativa": "Evidência direta apresentada no currículo.",
                    "limitacoes": [],
                    "base": "evidencia",
                }
            )
        return json.dumps(
            {
                "estado": "indeterminado",
                "evidence_ids": [],
                "justificativa": "Evidência insuficiente para decidir.",
                "limitacoes": ["Revisão humana necessária."],
                "base": "ambiguidade",
            }
        )


class FactoryMethodTests(unittest.TestCase):
    def test_get_contextual_adapter_factory_returns_expected_creators(self):
        transformers_factory = get_contextual_adapter_factory("transformers")
        llama_factory = get_contextual_adapter_factory("llama_cpp")
        self.assertIsInstance(transformers_factory, ContextualAdapterFactory)
        self.assertIsInstance(transformers_factory, TransformersAdapterFactory)
        self.assertIsInstance(llama_factory, ContextualAdapterFactory)
        self.assertIsInstance(llama_factory, LlamaCppAdapterFactory)

    def test_get_contextual_adapter_factory_rejects_unknown_backend(self):
        with self.assertRaises(ValueError):
            get_contextual_adapter_factory("backend_inexistente")

    def test_create_adapter_delegates_to_factory_method(self):
        sentinel = object()

        class _StubFactory(ContextualAdapterFactory):
            def create_adapter(self, model_path: str, runtime_path: str = ""):
                return (sentinel, model_path, runtime_path)

        with patch.dict(
            os.environ,
            {
                "CONTEXTUAL_BACKEND": "llama_cpp",
                "CONTEXTUAL_MODEL_PATH": "modelos/qwen.gguf",
                "CONTEXTUAL_RUNTIME_PATH": "bin/llama-cli",
            },
        ), patch(
            "src.matching.factory.get_contextual_adapter_factory",
            return_value=_StubFactory(),
        ) as getter:
            created = create_adapter()

        getter.assert_called_once_with("llama_cpp")
        self.assertEqual(created, (sentinel, "modelos/qwen.gguf", "bin/llama-cli"))


class FacadeTests(unittest.TestCase):
    def setUp(self):
        self.raw_text = "EXPERIENCE\nBackend Developer\n2021-2024\n- Built APIs\nSKILLS\nPython"
        start_role = self.raw_text.index("Backend Developer")
        start_skill = self.raw_text.index("Python")
        self.entities = [
            {
                "label": "DESIGNATION",
                "text": "Backend Developer",
                "start": start_role,
                "end": start_role + len("Backend Developer"),
                "confidence": 0.95,
            },
            {
                "label": "SKILLS",
                "text": "Python",
                "start": start_skill,
                "end": start_skill + len("Python"),
                "confidence": 0.98,
            },
        ]
        self.requirements = [
            {
                "id": "req-1",
                "text": "Python",
                "tipo": "tecnico",
                "nivel": "obrigatorio",
                "condition": {"kind": "all", "terms": ["python"]},
            }
        ]
        self.job = {"id": "1", "titulo": "Dev Python"}
        self.resume = {"id": "10", "raw_text": self.raw_text}
        self.contextual_config = {
            "ner_model": "models/ner",
            "embedding_model": "models/emb",
            "contextual": {
                "enabled": True,
                "model": "models/qwen",
                "revision": "rev-1",
                "backend": "transformers",
                "runtime": "",
                "runtime_revision": "",
                "top_k": 5,
            },
        }

    def _facade(self, entities=None, contextual_loader=None, strategy=None):
        predictor = _FakePredictor(self.entities if entities is None else entities)
        embedder = _FakeEmbedder()
        loader = contextual_loader or (lambda *_: _FakeContextualAdapter())
        return TalentMatchPipelineFacade(
            models_loader=lambda *_: (predictor, embedder),
            contextual_loader=loader,
            justification_generator=lambda *args, **kwargs: {
                "status": "disponivel",
                "resumo": "Justificativa gerada.",
            },
            strategy=strategy,
        )

    def test_facade_orchestrates_contextual_qwen_pipeline(self):
        with patch.dict(os.environ, {"CONTEXTUAL_EVALUATOR": "experimental"}):
            result = self._facade().analyze_resume(
                self.job, self.resume, self.requirements, self.contextual_config
            )
        self.assertEqual(result["score_name"], "aderencia_documental")
        self.assertEqual(result["contextual_formula_version"], "contextual-bounds-1")
        self.assertAlmostEqual(result["score"], 100.0)
        self.assertEqual(result["last_role"], "Backend Developer")
        self.assertEqual(result["llm_justification"]["status"], "disponivel")

    def test_facade_forwards_alternative_adherence_strategy_to_contextual_batch(self):
        reqs = self.requirements + [
            {
                "id": "req-2",
                "text": "Liderança estratégica",
                "tipo": "comportamental",
                "nivel": "desejavel",
            }
        ]
        with patch.dict(os.environ, {"CONTEXTUAL_EVALUATOR": "experimental"}):
            result = self._facade(
                strategy=ProvisionalWeightedAdherence(provisional_factor=0.5)
            ).analyze_resume(self.job, self.resume, reqs, self.contextual_config)
        self.assertEqual(result["formula_version"], "3.1-provisional-weighted")
        self.assertGreater(result["score"], 66.0)

    def test_facade_rejects_disabled_contextual_evaluator(self):
        disabled_cfg = dict(
            self.contextual_config,
            contextual=dict(self.contextual_config["contextual"], enabled=False),
        )
        with self.assertRaises(PipelineExecutionError):
            self._facade().analyze_resume(
                self.job, self.resume, self.requirements, disabled_cfg
            )

    def test_facade_raises_pipeline_error_when_contextual_model_unavailable(self):
        with self.assertRaises(PipelineExecutionError):
            self._facade(contextual_loader=lambda *_: None).analyze_resume(
                self.job, self.resume, self.requirements, self.contextual_config
            )


if __name__ == "__main__":
    unittest.main()
