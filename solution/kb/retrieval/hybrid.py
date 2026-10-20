"""The search index of one snapshot: keyword (BM25) and meaning (embedding) search, merged.

Keyword search finds exact names, terms and numbers; meaning search finds paraphrases (a question in the
member's own words matching a page that uses the official product wording). Their rankings are merged with
reciprocal-rank fusion (RRF): every chunk gets 1 / (RRF_K + rank) points from each ranking; the most points win.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from .. import config
from ..cleaning import page_type
from ..cleaning.site_rules import OFFICIAL_PAGE_TYPES
from .bm25 import BM25Index
from .chunk import Chunk
from .embeddings import Embedder


class SnapshotIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self.chunks = chunks
        self._record_copies(chunks)
        docs = [c.search_text() for c in chunks]
        self.bm25 = BM25Index(docs)
        self.embedder = embedder
        self.vectors = embedder.embed(docs)

    @staticmethod
    def _record_copies(chunks: list[Chunk]) -> None:
        """Shared rate tables and mirrored pages put identical text on several pages. Remember every page
        that carries a chunk's exact text, official product/rates pages first, so an answer can cite them."""
        pages_by_body: dict[str, list[str]] = defaultdict(list)
        for c in chunks:
            if c.url not in pages_by_body[c.body]:
                pages_by_body[c.body].append(c.url)
        for c in chunks:
            c.copies = sorted(pages_by_body[c.body], key=lambda u: page_type(u) not in OFFICIAL_PAGE_TYPES)

    def search(self, query: str, k: int = config.TOP_K) -> list[Chunk]:
        """Top-k chunks by fused rank; a text that appears on several pages is returned once."""
        depth = config.CANDIDATES_PER_RANKER
        rankings = [self.bm25.rank(query)[:depth]]
        query_vector = self.embedder.query(query)
        if query_vector is not None and self.vectors is not None:
            rankings.append(list(np.argsort(-(self.vectors @ query_vector))[:depth]))
        fused = Counter()
        for ranking in rankings:
            for rank, i in enumerate(ranking):
                fused[i] += 1 / (config.RRF_K + rank + 1)
        out, seen = [], set()
        for i, _points in fused.most_common():
            if self.chunks[i].body not in seen:
                seen.add(self.chunks[i].body)
                out.append(self.chunks[i])
            if len(out) == k:
                break
        return out
