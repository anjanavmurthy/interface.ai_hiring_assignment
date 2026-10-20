"""Knowledge system for the Dupaco website snapshots.

Pipeline, one sub-package per stage:
    cleaning/   raw page markdown  -> clean text + links          (no LLM)
    retrieval/  clean text         -> chunks -> hybrid search index (no LLM)
    qa/         question + chunks  -> one Claude call -> Answer
    conflicts/  tables across snapshots -> list of contradictions

solution.py (one level up) wires these together behind the three methods the scorer calls.
"""
