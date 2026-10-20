# kb/conflicts — finding contradictions in the website's tables

Code does the mechanical work; the LLM makes every judgement. The stages run in this order (`pipeline.py`):

| Stage | File | What it does | LLM |
|---|---|---|---|
| s1 | `s1_read_tables.py` | Read every table on every cleaned page. Two readers, see the note below | – |
| s2 | `s2_group_layouts.py` | Group tables that share a header row into "layouts" (127 in the five downloads) | – |
| s3 | `s3_label_columns.py` + `s3_label_columns_prompt.py` | For each new layout, say what kind of table it is and which columns name the product, which are conditions (term, tier, model year) and which are values (rate, APY, fee) | yes, live in ingest |
| s4 | `s4_track_tables.py` | Merge identical copies, follow each page's table from download 01 to 05, group pages that always show the same table | – |
| s5 | `s5_pick_comparisons.py` | Choose which look-alike tables are compared together (rule E; never personal vs business) | – |
| s6 | `s6_judge_conflicts.py` + `s6_judge_prompt.py` | One comparison request per comparison set: which tables are the same thing, which differences are conflicts, the correct value | yes, cached |
| s7 | `s7_write_conflicts.py` | One record per conflict, labelled "same day" / "over time", plus differences not called conflicts | – |

Shared: `table_text.py` (cell clean-up and value comparison), `../llm.py` (the cached LLM caller), settings in
`../config.py` (model, effort, thresholds, cache files).

`conflicts()` in `solution.py` runs s4-s7 once on its first call and adds the fact conflicts judged in ingest
(`kb/facts`); `report.py` turns both into the scorer's `Conflict` objects.

## What runs where

- **Inside `ingest()`** (`tracker.py`): s1 reads each snapshot's pages as it arrives, s2 groups all tables seen so
  far into layouts, and s3 asks the LLM only about layouts never seen before (snapshot 01 labels almost all of them,
  later snapshots only new ones). 4 requests at a time; a failed request only leaves its layouts unlabelled (their
  tables are not read) and they are tried again with the next snapshot. Only layouts the LLM calls an "offer table"
  or a "listing" (`config.TRACKED_TABLE_KINDS`) are read by s4-s7.
- **s4-s7** (`pipeline.find_table_conflicts`): run by `conflicts()` on its first call (19 judge requests).
- Nothing the LLM said is shipped: on a fresh copy every request is sent live. The LLM caches
  (`solution/.cache/column_labels.json`, `conflict_judge.json`, git-ignored) only make repeated local runs free;
  they hold answers by exact request text.

## Two table readers (kept on purpose)

The column labelling (s2–s3) was built on one reader and the comparison (s4–s7) on another. They differ: reader 2
splits two tables printed directly after each other, reader 1 reads them as one; they also pick titles differently.
Merging them would change what both LLM stages see, so it is a separate change, to be measured and decided.
