"""
Geração de embeddings de skills e contextos do currículo.

Não treina um modelo e não calcula a aderência final.
Cada vetor permanece associado ao texto que o originou.
"""

from typing import Any

from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = "sentence-transformers/all-mpnet-base-v2"


class ResumeEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        # CPU permite executar sem depender de uma GPU.
        self.model = SentenceTransformer(model_name, device="cpu")
        self.model_name = model_name
        self.tokenizer = self.model.tokenizer

        if not self.tokenizer.is_fast:
            raise ValueError("É necessário um tokenizer com offsets.")

        # Reserva espaço para os tokens especiais do modelo.
        special_tokens = self.tokenizer.num_special_tokens_to_add(pair=False)

        self.window_size = min(
            256,
            self.model.max_seq_length - special_tokens,
        )

        if self.window_size <= 0:
            raise ValueError("Limite de tokens inválido.")

        self.overlap = min(32, self.window_size // 4)

    def _split_text(self, text: str) -> list[dict[str, Any]]:
        """
        Divide por tokens, mas mantém trechos do texto original.

        Os offsets são relativos ao texto recebido neste método.
        """
        if not text.strip():
            return []

        # Tokeniza o texto completo para obter os offsets.
        # verbose=False evita avisos de sequências longas nesta etapa.
        # O texto não é truncado: todos os tokens são preservados.
        encoded = self.tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
            verbose=False,
        )

        offsets = encoded["offset_mapping"]

        if not offsets:
            return []

        chunks = []
        start = 0
        while start < len(text):
            local = self.tokenizer(
                text[start:],
                add_special_tokens=False,
                return_offsets_mapping=True,
                truncation=False,
                verbose=False,
            )
            spans = local["offset_mapping"]
            if not spans:
                # Preserve trailing whitespace in the preceding evidence window.
                if chunks:
                    chunks[-1]["end_char"] = len(text)
                    chunks[-1]["text"] = text[chunks[-1]["start_char"] :]
                break
            end = (
                len(text) if len(spans) <= self.window_size else start + spans[self.window_size][0]
            )
            # Prefer a complete word, but never exceed the real retokenized limit.
            while (
                end < len(text) and end > start and text[end - 1].isalnum() and text[end].isalnum()
            ):
                end += 1
            while True:
                chunk_text = text[start:end]
                tokens = self.tokenizer(
                    chunk_text, add_special_tokens=True, truncation=False, verbose=False
                )["input_ids"]
                if len(tokens) <= self.model.max_seq_length:
                    break
                end -= max(1, (end - start) // 10)
                boundary = end
                while (
                    boundary > start and text[boundary - 1].isalnum() and text[boundary].isalnum()
                ):
                    boundary -= 1
                if boundary > start:
                    end = boundary
                if end <= start:
                    raise ValueError("Nenhum trecho cabe no limite real do modelo.")
            chunks.append(
                dict(text=chunk_text, start_char=start, end_char=end, token_count=len(tokens))
            )
            if end == len(text):
                break
            accepted = self.tokenizer(
                chunk_text,
                add_special_tokens=False,
                return_offsets_mapping=True,
                truncation=False,
                verbose=False,
            )["offset_mapping"]
            next_start = (
                start + accepted[-self.overlap][0]
                if self.overlap and len(accepted) > self.overlap
                else end
            )
            boundary = next_start
            while (
                boundary > start
                and boundary < len(text)
                and text[boundary - 1].isalnum()
                and text[boundary].isalnum()
            ):
                boundary -= 1
            next_start = boundary if boundary > start else end
            start = next_start if start < next_start <= end else end

        return chunks

    def encode(
        self,
        semantic_inputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Gera uma matriz: uma linha por trecho.

        records[i] descreve o texto do vetor embeddings[i].
        """
        records = []

        for input_index, item in enumerate(semantic_inputs):
            text = item.get("text")

            if not isinstance(text, str):
                raise ValueError(f"Entrada {input_index} sem texto válido.")

            chunks = self._split_text(text)

            for chunk_index, chunk in enumerate(chunks):
                records.append(
                    {
                        "input_index": input_index,
                        "chunk_index": chunk_index,
                        "source": item.get("source"),
                        "metadata": {key: value for key, value in item.items() if key != "text"},
                        **chunk,
                    }
                )

        if not records:
            raise ValueError("Nenhum texto disponível para gerar embeddings.")

        vectors = self.model.encode(
            [record["text"] for record in records],
            batch_size=8,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return {
            "model_name": self.model_name,
            "normalized": True,
            "embedding_dimension": int(vectors.shape[1]),
            "records": records,
            "embeddings": vectors.tolist(),
        }
