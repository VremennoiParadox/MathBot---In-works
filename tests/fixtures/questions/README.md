# Recheck test corpus (20 questions)

Each `*.json` file is a **vision output** (not a screenshot). Use these to validate the think-and-recheck pipeline without a live tutoring site.

## Run manually (needs Ollama + solver model)

```bash
source .venv/bin/activate
python scripts/run_recheck_corpus.py
```

## Run unit tests only (no Ollama)

```bash
pytest tests/test_recheck_prompt.py tests/test_math_recheck.py tests/test_math_solver.py -q
```

Review terminal output: Pass 1 working, Pass 2 verification, and whether recheck catches deliberate errors in `notes` fields.
