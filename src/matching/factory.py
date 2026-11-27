"""Fábricas para criação de adaptadores do avaliador contextual (GoF: Factory Method)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.matching.contextual import Adapter


class ContextualAdapterFactory(ABC):
    """Criador abstrato que define o Factory Method ``create_adapter``."""

    @abstractmethod
    def create_adapter(self, model_path: str, runtime_path: str = "") -> Adapter:
        """Instancia o adaptador concreto compatível com o backend selecionado."""
        raise NotImplementedError


class TransformersAdapterFactory(ContextualAdapterFactory):
    """Fábrica concreta para execução local via HuggingFace Transformers."""

    def create_adapter(self, model_path: str, runtime_path: str = "") -> Adapter:
        from src.matching.contextual import LocalTransformersAdapter

        return LocalTransformersAdapter(model_path)


class LlamaCppAdapterFactory(ContextualAdapterFactory):
    """Fábrica concreta para execução local quantizada via llama.cpp."""

    def create_adapter(self, model_path: str, runtime_path: str = "") -> Adapter:
        from src.matching.local_runtime import LlamaCppAdapter

        return LlamaCppAdapter(model_path, runtime_path)


_CONTEXTUAL_FACTORIES: dict[str, type[ContextualAdapterFactory]] = {
    "transformers": TransformersAdapterFactory,
    "llama_cpp": LlamaCppAdapterFactory,
}


def get_contextual_adapter_factory(backend: str) -> ContextualAdapterFactory:
    """Retorna a fábrica correspondente ao backend configurado."""
    factory_cls = _CONTEXTUAL_FACTORIES.get(backend)
    if factory_cls is None:
        raise ValueError("Backend contextual desconhecido")
    return factory_cls()
