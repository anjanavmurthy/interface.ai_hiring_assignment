"""Meaning-based search vectors: bge-small via fastembed, cached on disk by text hash.

Most text is identical across the five snapshots, so each distinct chunk is embedded once, ever; this keeps
ingest at a few seconds after the first run. If the model can't load (no package / no network on the very
first run), search falls back to keywords only instead of failing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .. import config


class Embedder:
    def __init__(self, cache_file: Path = config.EMBEDDINGS_CACHE, model_name: str = config.EMBEDDING_MODEL):
        self.cache_file = cache_file
        self.cache: dict[str, np.ndarray] = dict(np.load(cache_file)) if cache_file.exists() else {}
        try:
            from fastembed import TextEmbedding
            self.model = TextEmbedding(model_name)
        except Exception as e:
            print(f"embedding model unavailable ({e}); using keyword search only", flush=True)
            self.model = None

    def embed(self, texts: list[str]) -> np.ndarray | None:
        """Unit-length vectors for `texts` (one row each); new texts are embedded and added to the cache."""
        if self.model is None:
            return None
        keys = [hashlib.md5(t.encode()).hexdigest() for t in texts]
        todo = {k: t for k, t in zip(keys, texts) if k not in self.cache}
        if todo:
            for k, v in zip(todo, self.model.embed(list(todo.values()), batch_size=64)):
                self.cache[k] = v / np.linalg.norm(v)
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            np.savez(self.cache_file, **self.cache)
        return np.stack([self.cache[k] for k in keys])

    def query(self, text: str) -> np.ndarray | None:
        """Unit-length vector for a question (bge uses a query-specific prefix internally)."""
        if self.model is None:
            return None
        v = next(iter(self.model.query_embed(text)))
        return v / np.linalg.norm(v)
