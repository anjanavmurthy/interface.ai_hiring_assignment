"""Every tunable setting of the system, in one place.

Changing behaviour should mean changing a value here, so a diff of this file shows exactly what was tuned.
"""
from __future__ import annotations

from pathlib import Path

SOLUTION_DIR = Path(__file__).resolve().parents[1]      # the submission folder (contains solution.py)

# --- embeddings -------------------------------------------------------------------------------------------
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"               # small local model via fastembed; no API key needed
EMBEDDINGS_CACHE = SOLUTION_DIR / ".cache" / "embeddings.npz"   # vectors by text hash, reused across runs

# --- chunking (characters; ~4 characters per token) -------------------------------------------------------
CHUNK_TARGET_CHARS = 1200        # start a new chunk once the current one would grow past this
CHUNK_MAX_CHARS = 1800           # tables longer than this are split into row groups that repeat the header
CHUNK_MIN_CHARS = 200            # sections shorter than this are merged into the next one

# --- search -----------------------------------------------------------------------------------------------
TOP_K = 16                       # chunks given to Claude per question
CANDIDATES_PER_RANKER = 200      # how deep each ranking (BM25, embeddings) is read before merging
RRF_K = 60                       # reciprocal-rank-fusion constant: score = sum(1 / (RRF_K + rank))
BM25_K1, BM25_B = 1.2, 0.75      # standard BM25 parameters

# --- answering --------------------------------------------------------------------------------------------
MODEL = "claude-opus-5-5"
EFFORT = "low"                   # low effort keeps answers fast (speed is 15% of the score)
MAX_TOKENS = 4000
API_TIMEOUT_S = 45.0             # the scorer allows 60 s per answer
API_MAX_RETRIES = 1
ANSWER_HISTORY = True            # add <history> (dated fact values, kb/history.py) and, for questions about another
                                 # time, <changes> (page changes, kb/changes.py) to every answer
HISTORY_RECORDS = 8             # history: at most this many facts that best match the question
HISTORY_EXCERPT_FACTS = 4       # plus up to this many judged facts stated in the 16 excerpts
CHANGES_PER_QUESTION = 3        # questions about another time: this many page changes (kb/changes.py)
CHANGE_SIDE_CHARS = 1200        # each change shows at most this much of its before and its after text
CITED_URLS_PER_SOURCE = 4        # a cited chunk may exist on several pages; cite at most this many of them

# --- conflicts (kb/conflicts, stages s1-s7) ----------------------------------------------------------------
CONFLICTS_MODEL = "claude-opus-5-5"   # used by both LLM stages: column labelling (s3) and the judge (s6)
CONFLICTS_EFFORT = "medium"
COLUMN_LABELS_CACHE = SOLUTION_DIR / ".cache" / "column_labels.json"      # s3 answers, by exact request
CONFLICT_JUDGE_CACHE = SOLUTION_DIR / ".cache" / "conflict_judge.json"    # s6 answers, by exact request
LABEL_LAYOUTS_PER_CALL = 15           # s3: layouts per labelling request
TRACKED_TABLE_KINDS = ("offer table", "listing")   # s3 kinds whose tables are followed; forms, worked examples
                                                   # and other tables state no facts of the credit union's that change
SAME_ROWS_MIN = 0.6                   # s4/s5: share of row names that must look alike ("MIN_OVERLAP")
ROW_NAME_SIMILAR = 0.85               # s4/s5: two row names look alike at this similarity or more
TITLE_MAX_CHARS = 60                  # s4: a longer "line above" is a sentence, not a table title
LLM_PARALLEL = 4                      # s3/s6/facts: requests sent at the same time (kept low for rate limits)

# Time for the Claude steps of ingest(), from the first ingest() call: the scorer allows 30 minutes for all five
# snapshots; the rest is left for cleaning, indexing and requests already under way.
INGEST_BUDGET_S = 24 * 60
INGEST_HARD_STOP_S = 28 * 60     # a request sent before the budget ran out still stops waiting by this point

# --- facts from page text (kb/facts) -----------------------------------------------------------------------
FACTS_MODEL = "claude-opus-5-5"
FACTS_EFFORT = "low"                  # reading and listing; the judgement calls are in s6 and the grouping step
FACTS_CACHE = SOLUTION_DIR / ".cache" / "facts.json"                    # answers by exact request (local runs only)
FACTS_REQUEST_CHARS = 30_000          # documents packed into one request up to about this size (~8,000 tokens)
FACTS_GROUP_EFFORT = "medium"         # step 3: deciding which differently worded facts are the same one
FACTS_GROUP_CACHE = SOLUTION_DIR / ".cache" / "fact_names.json"       # answers by exact request (local runs only)
FACTS_JUDGE_EFFORT = "medium"         # step 5: is a fact with several values a real contradiction, which value wins
FACTS_JUDGE_CACHE = SOLUTION_DIR / ".cache" / "fact_judge.json"       # answers by exact request (local runs only)
FACTS_JUDGE_PER_REQUEST = 15          # step 5: facts per request

# --- more page text for conflicts (kb/facts/wider.py) and text vs tables (kb/bridge) -----------------------
# With every switch below off, the system sends exactly the requests it sent without them. The extra page text feeds
# conflicts() only, never the answers, unless HISTORY_NEW_WARNINGS is on.
FACTS_READ_MORE = True                # on pages read in part, also read paragraphs (READ_MORE_MIN_WORDS or more)
                                      # with an amount, a %, a date or a time, that mention Dupaco/we/our/us outside
                                      # quotes, or that name a known product or subject
FACTS_CATCHUP = True                  # with FACTS_READ_MORE: after extraction, also read this snapshot's unread
                                      # paragraphs that name a subject first found in it
FACTS_MORE_MODEL = "claude-opus-5-5"  # extraction of the new text (claude-sonnet-5-5 allowed); naming/judging stay Opus
FACTS_MORE_EFFORT = "low"
FACTS_MORE_CACHE = SOLUTION_DIR / ".cache" / "facts_more.json"
FACTS_MORE_NAMES_CACHE = SOLUTION_DIR / ".cache" / "fact_names_more.json"
FACTS_MORE_JUDGE_CACHE = SOLUTION_DIR / ".cache" / "fact_judge_more.json"
READ_MORE_MIN_WORDS = 6               # the new rules only pick paragraphs of at least this many words (a byline,
                                      # "4 min read" or a widget's figure states nothing)
KNOWN_NAME_MIN_CHARS = 4              # a known name shorter than this is not looked for
KNOWN_NAME_MAX_SHARE = 0.02           # a known name in more than this share of a snapshot's paragraphs is too common
NAMING_BATCH_OVER = 300               # new-text naming only: a fact type with more new pairs is named in batches
NAMING_BATCH_PAIRS = 150              # pairs per batch
NAMING_NEARBY_KNOWN = 30              # known names shown with each batch: the ones sharing most words with it
HISTORY_NEW_WARNINGS = False          # answers: also show 'X is current; outdated values ...' lines for facts judged
                                      # with the extra text (off: answers see exactly what they saw without it; on
                                      # showed no gain and can put a site typo or a weak conflict in front of answers)
TEXT_VS_TABLES = False                # conflicts(): add contradictions between page text and table rows
TEXT_VS_TABLES_JUDGE_CACHE = SOLUTION_DIR / ".cache" / "text_table_check.json"
TEXT_VS_TABLES_SIMILAR = 0.75         # shortlist: a text fact's subject this close in meaning to a table's title and
                                      # products (loose on purpose: Claude decides what the sentence is about)
TEXT_VS_TABLES_PER_TABLE = 12         # shortlist: at most this many sentences per table, the closest first
TEXT_VS_TABLES_TABLES_PER_REQUEST = 6 # tables (each with its sentences) per request
