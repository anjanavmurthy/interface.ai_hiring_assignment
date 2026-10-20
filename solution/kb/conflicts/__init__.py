"""Conflict detection: places where the website contradicts itself, with the value believed right.

Stages (see README.md in this folder): s1 read tables -> s2 group layouts -> s3 label columns (LLM) ->
s4 track tables -> s5 pick comparisons -> s6 judge conflicts (LLM) -> s7 write conflicts; pipeline.py runs them.
"""
