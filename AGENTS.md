# AGENTS.md

## Cursor Cloud specific instructions

### Project overview
This repo ("AI Recovery Engine") is documented in `README.md` as a **stdlib-only Python 3.10+**
project with **zero external dependencies**. It is a set of seeded, deterministic CLI
simulations across three maturity levels (see `README.md` for full detail):

- `python3 run_v0_engine.py` — v0 decision engine
- `python3 run_v1_product_ops.py` — v1 product-ops 90-day plan
- `python3 run_v2_agent.py` — v2 agentic rollout loop (optional LLM brain via
  `--brain claude`, which needs `ANTHROPIC_API_KEY`; otherwise falls back to a heuristic brain)

Each run is seeded/reproducible, finishes in seconds, and writes artifacts to `reports/` and
`logs/` (both generated at runtime).

### Environment / running
- **No dependency install is required** — the code is stdlib-only. The VM ships Python 3.12,
  which satisfies `Python 3.10+`. There is no package manifest (`requirements.txt` /
  `pyproject.toml`), lockfile, virtualenv, build step, web server, or database.
- To run a level, invoke the corresponding `run_v*.py` script directly with `python3`. There is
  no lint/test tooling configured in the repo; validation is done by running the scripts and
  inspecting the generated `reports/`/`logs/` artifacts.

### IMPORTANT: source code is currently missing from the repo
As of this setup, the repository contains **only `README.md`**. None of the source files or
directories the README references (`run_v0_engine.py`, `run_v1_product_ops.py`,
`run_v2_agent.py`, `engine/`, `pm_ops/`, `agent/`, `docs/`) have been committed on any branch.
The application therefore cannot be run until that source code is added to the repository.
Once the code is present, the run commands above should work with no additional setup.
