"""Optional frozen MiniLM retriever over the same CC-BY corpus.

The model is loaded from the local HuggingFace cache and is never trained. This
is an embedding retriever, not a generative proposer; absence of the model
fails explicitly rather than falling back to a different score silently.
"""

import math
import os
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .real_corpus_retriever import RealCorpusRetriever

Encoder = Callable[[Sequence[str]], List[List[float]]]


class MiniLMUnavailable(RuntimeError):
    pass


class MiniLMRetriever(RealCorpusRetriever):
    model_id = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, corpus_path: Path, encoder: Optional[Encoder] = None):
        super().__init__(Path(corpus_path))
        self._encoder = encoder or self._load_encoder()
        self._doc_vectors = self._encode([
            self._doc_text(paper) for paper in self._docs.values()
        ])

    @staticmethod
    def _doc_text(paper) -> str:
        return str(paper.get("title", "")) + "\n" + str(paper.get("abstract", ""))

    def _load_encoder(self) -> Encoder:
        os.environ.setdefault("USE_TF", "0")
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise MiniLMUnavailable("transformers/torch are required for MiniLM retrieval") from exc
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=True)
            model = AutoModel.from_pretrained(self.model_id, local_files_only=True)
        except OSError as exc:
            raise MiniLMUnavailable("MiniLM weights are not available locally: " + self.model_id) from exc
        model.eval()

        def encode(texts: Sequence[str]) -> List[List[float]]:
            batch = tokenizer(
                list(texts), padding=True, truncation=True, max_length=256, return_tensors="pt"
            )
            with torch.no_grad():
                hidden = model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).float()
            vectors = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            vectors = torch.nn.functional.normalize(vectors, dim=-1)
            return vectors.tolist()

        return encode

    def _encode(self, texts: Sequence[str]) -> List[List[float]]:
        vectors = self._encoder(list(texts))
        if len(vectors) != len(texts):
            raise MiniLMUnavailable("encoder returned a different number of vectors")
        return [self._normalize([float(value) for value in vector]) for vector in vectors]

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    def search(self, query: str, limit: int):
        query_vector = self._encode([query])[0]
        ranked = []
        for (source_id, paper), vector in zip(self._docs.items(), self._doc_vectors):
            score = sum(left * right for left, right in zip(query_vector, vector))
            ranked.append((score, paper))
        ranked.sort(key=lambda item: (-item[0], str(item[1]["source_id"])))
        return [self._hit(paper) for _, paper in ranked[: max(0, limit)]]
