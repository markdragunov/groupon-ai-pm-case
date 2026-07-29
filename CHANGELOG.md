# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-29

### Added

- **v0 · Engine** — payment recovery simulator with rules baseline, bandit ranker, fraud guardrails, and pre-committed ship verdict (`run_v0_engine.py`)
- **v1 · Product Ops** — executable 90-day PM plan: cohort audit, instrumentation gate, pre-registered experiment, readout with decomposition (`run_v1_product_ops.py`)
- **v2 · Agent** — agentic rollout loop with heuristic/Claude brain, verifier, memory, and safety overrides (`run_v2_agent.py`)
- Architecture diagrams in `docs/` (SVG)
- GitHub Actions CI running all three demos
- MIT License

### Notes

- Initial public release. All data is synthetic and seeded; the repository demonstrates **method, not findings**.

[1.0.0]: https://github.com/markdragunov/groupon-ai-pm-case/releases/tag/v1.0.0
