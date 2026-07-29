# Contributing

Thank you for your interest in AI Recovery Engine. This project is a personal open-source companion to a Senior AI PM case study — contributions that preserve its teaching intent are welcome.

## Before you start

1. Read the [README](README.md), especially [Design principles](README.md#design-principles) and [Honesty & limits](README.md#honesty--limits).
2. Run all three demos locally:

```bash
python3 run_v0_engine.py
python3 run_v1_product_ops.py
python3 run_v2_agent.py
```

Each run is seeded and should finish in under five seconds.

## What we welcome

- Documentation fixes and clarity improvements
- Bug fixes that preserve deterministic, seeded behaviour
- Tests that assert pre-committed outcomes (verdicts, guardrails, verifier rules)
- Diagram or README improvements that make the method easier to follow

## What we will not merge

- Changes that redesign core algorithms or business logic without a strong rationale
- Features that expand scope sideways (multi-funnel platform, production integrations) — v3 is deliberately not built
- Changes that break reproducibility of seeded runs
- Marketing exaggeration or claims not supported by the code

## Development notes

- **Python 3.10+**, stdlib only — no `requirements.txt` needed
- Generated artifacts go to `data/`, `logs/`, and `reports/` (gitignored)
- Optional LLM brain: `python3 run_v2_agent.py --brain claude` requires `ANTHROPIC_API_KEY`
- CI runs all three entry points on every push and pull request

## Break it on purpose

The README's [Break it on purpose](README.md#break-it-on-purpose) table lists tunables that demonstrate product decisions. If you change behaviour, update that table and the PM decision log when the lesson changes.

## Pull requests

1. Fork and create a branch from `main`
2. Keep diffs focused — one concern per PR when possible
3. Confirm all three demos still run
4. Describe **what** changed and **why**, especially if a product principle is affected

## Questions

Open a GitHub issue for bugs, documentation gaps, or discussion. This is a method repository, not a production service — issues about real payment integrations are out of scope.
