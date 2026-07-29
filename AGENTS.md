# AGENTS.md

## Cursor Cloud specific instructions

### Project overview
This repo ("AI Recovery Engine") is a **stdlib-only Python 3.10+** project with **zero external
dependencies**. It is a set of seeded, deterministic CLI simulations across three maturity
levels (see `README.md` for full detail):

- `python3 run_v0_engine.py` — v0 decision engine
- `python3 run_v1_product_ops.py` — v1 product-ops 90-day plan
- `python3 run_v2_agent.py` — v2 agentic rollout loop

### Running
- **No dependency install is required** — the code is stdlib-only. The VM ships Python 3.12,
  which satisfies `Python 3.10+`. There is no package manifest (`requirements.txt` /
  `pyproject.toml`), lockfile, virtualenv, build step, web server, or database.
- Each run is seeded/reproducible, finishes in seconds, and prints its result to stdout.

### Testing / lint
- Tests: `python3 -m unittest tests/smoke_test.py -v` (deterministic smoke checks that assert
  the pre-committed verdict strings and artifact paths for all three demos).
- CI (`.github/workflows/demo.yml`) runs all three entry points followed by the smoke test.
- There is **no lint tooling** configured in the repo.

### Generated artifacts (gitignored)
Runs write to `data/`, `logs/`, and `reports/` (all in `.gitignore`); these are created on run
and are not committed. Deleting them is safe — they regenerate on the next run.

### Optional LLM brain
`python3 run_v2_agent.py --brain claude` uses an LLM decide-step and needs `ANTHROPIC_API_KEY`.
It is **non-blocking**: with no key (or on any error) it falls back to the deterministic
heuristic brain, so the demo still completes without a key.
