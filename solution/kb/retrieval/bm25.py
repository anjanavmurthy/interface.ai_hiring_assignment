"""Keyword search: BM25 over an inverted index (word -> the chunks that contain it).

Built once per snapshot at ingest. A search only scores the chunks listed under the question's words, so its
cost grows with how common those words are, not with the number of chunks.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import numpy as np

from .. import config

# a token is a number (kept whole with its $ / % / decimals: "$9,999", "1.23%") or a run of letters
TOKEN = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?|[a-z]+")
STOP_WORDS = set("a an the of on for to in is are what whats do does you your i my me can how and or with at by be "
                 "it this that from as was were will have has there their they we our us".split())


def _stem(word: str) -> str:
    """Light plural stemming so 'fees' matches 'fee' and 'IRAs' matches 'ira'. Numbers are left alone."""
    if word[0].isdigit() or word[0] == "$":
        return word
    if len(word) <= 4:   # short plurals and acronyms: "atms" -> "atm", "iras" -> "ira"; not "bus", "his"
        return word[:-1] if len(word) >= 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")) else word
    for suffix, replacement in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(suffix) and not word.endswith("ss"):
            return word[: -len(suffix)] + replacement
    return word


def tokens(text: str) -> list[str]:
    """Lowercase, drop possessive 's, split into tokens, remove stop words, stem."""
    text = text.lower().replace("'s", "").replace("’s", "")
    return [_stem(t) for t in TOKEN.findall(text) if t not in STOP_WORDS]


class BM25Index:
    def __init__(self, docs: list[str], k1: float = config.BM25_K1, b: float = config.BM25_B):
        self.k1, self.b = k1, b
        self.term_freqs = [Counter(tokens(d)) for d in docs]            # per doc: token -> count
        self.doc_len = np.array([sum(tf.values()) for tf in self.term_freqs], float)
        self.avg_len = float(self.doc_len.mean()) if len(docs) else 1.0
        doc_freq = Counter(w for tf in self.term_freqs for w in tf)      # token -> number of docs containing it
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in doc_freq.items()}   # rare = high
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)   # token -> [(doc, count)]
        for i, tf in enumerate(self.term_freqs):
            for w, f in tf.items():
                self.postings[w].append((i, f))

    def rank(self, query: str) -> list[int]:
        """Indices of all docs sharing a token with the query, best BM25 score first."""
        scores = np.zeros(len(self.term_freqs))
        for w in set(tokens(query)):
            for i, f in self.postings.get(w, []):
                length_norm = 1 - self.b + self.b * self.doc_len[i] / self.avg_len
                scores[i] += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * length_norm)
        hit = np.nonzero(scores)[0]
        return list(hit[np.argsort(-scores[hit])])
