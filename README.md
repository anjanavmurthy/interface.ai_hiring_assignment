# Dupaco Knowledge System

A question-answering system for Dupaco Credit Union information. It searches the supplied website snapshots,
answers with relevant sources, and can decline when the snapshots do not support an answer. See [NOTES.md](NOTES.md)
for an overview of the system.

## Requirements

- Python 3.11
- An Anthropic API key to generate answers

## Install

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Set `ANTHROPIC_API_KEY` in `.env` before running the evaluator. Keep the key private and do not commit `.env`.

## Evaluate

```bash
.venv/bin/python harness/run_eval.py \
	--submission solution \
	--eval eval/public_eval.jsonl \
	--snapshots /path/to/unpacked/snapshots
```

The supplied website snapshots are excluded from this repository. Obtain them separately and point `--snapshots`
to the folder containing the snapshot directories and their `manifest.json` files. Run the unit tests with:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests
```

The submission implementation is in `solution/`; `harness/` provides the evaluation interface.
