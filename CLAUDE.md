# CLAUDE.md

Guidance for AI assistants (Claude Code and others) working in this repository.

## What this project is

**AI Recovery Engine** — an executable companion to a Groupon Senior AI PM case
study (Checkout & Payments). It is *not* a payments product; it is a
demonstration of a decision discipline: how a PM introduces AI into a
money-critical path without granting it authority it has not earned.

The same product idea is expressed at three **maturity levels** (`v0`/`v1`/`v2`
denote maturity, *not* semver releases — they are layers, not successors, and
v2 contains v0 unchanged):

| Level | Entry point | What it demonstrates |
|---|---|---|
| **v0 · Engine** | `run_v0_engine.py` | A deterministic cage around a rules-vs-bandit competition for one failed payment; pre-committed "ship the table" verdict |
| **v1 · Product Ops** | `run_v1_product_ops.py` | A PM's first 90 days as running code: audit → pre-registered experiment behind an instrumentation gate → readout |
| **v2 · Agent** | `run_v2_agent.py` | The rollout operated by an agent loop: bounded actions, evidence gates, a kill switch, human approval it cannot forge |

Read `README.md` for the full narrative — it is the source of truth for intent.
This file is the operational quick reference.

## Ground rules (read before changing anything)

This is a **teaching repository**. Its value is in what it demonstrates, so the
constraints below are the product, not incidental:

- **Stdlib only, Python 3.10+.** Zero external dependencies. No
  `requirements.txt`, `pyproject.toml`, lockfile, virtualenv, or build step.
  Do **not** add a dependency — if a change seems to need one, it is almost
  certainly the wrong change here.
- **Seeded and deterministic.** Every run is reproducible. The smoke tests
  assert exact, pre-committed verdict strings. Any change that alters those
  strings or breaks reproducibility breaks the tests and the case.
- **The invariants never move.** Deterministic execution, bounded action
  spaces, evidence gates, and a human owning irreversible risk hold at every
  level. AI ranks within a cage; it never receives authority automatically,
  and it can never touch safety rules or guardrail thresholds.
- **Do not grow sideways.** `v3 · Platform` (multi-funnel, real approval
  workflow) and `HTML view · MCP server` are named but deliberately *not*
  built. Scope discipline is itself a demonstrated product decision — do not
  build these unless explicitly asked.
- **Synthetic data is a design choice, not a shortcut.** Every pattern (the
  funnel break, interaction pockets, fraud spike) is intentionally planted so
  the mechanism can be shown end-to-end. Keep the seeded arithmetic consistent
  with the case anchors documented in the module docstrings.

## Commands

```bash
# Run the three demos (each seeded, stdlib-only, finishes in < 5 seconds)
python3 run_v0_engine.py        # → data/funnel.csv, logs/decision_log.jsonl, console verdict
python3 run_v1_product_ops.py   # → reports/day60_experiment_spec.md, reports/day90_readout.md
python3 run_v2_agent.py         # → reports/agent_run.md, logs/agent_journal.jsonl, SHIP verdict

# Optional LLM decide-step for v2 (non-blocking; falls back to heuristic on no key / any error)
python3 run_v2_agent.py --brain claude   # needs ANTHROPIC_API_KEY

# Tests — deterministic smoke checks; assert the pre-committed verdict strings
python3 -m unittest tests/smoke_test.py -v
```

There is **no lint tooling** configured. CI (`.github/workflows/demo.yml`) runs
all three entry points followed by the smoke test, on every push and PR, using
Python 3.11.

## Repository layout

```
run_v0_engine.py        one entry point per maturity level — thin orchestrators
run_v1_product_ops.py     that call into the packages and print the console report
run_v2_agent.py

engine/                 v0 — the payment decision engine (the cage)
  data.py                 synthetic funnel data reconciling to the case arithmetic
  detect.py               naive blended monitor vs joint auth/completion divergence detector
  decide.py               SAFETY_RULES cage · RULES_BASELINE lookup · BanditRanker · FraudGuardrail
  simulate.py             the six-week rollout as a seeded experiment; ground-truth INTERACTIONS

pm_ops/                 v1 — the first 90 days as code
  data.py                 synthetic post-purchase dataset (same disease, one funnel right)
  audit.py                Day 30: funnel audit, cohort divergence, detection-lag
  experiment.py           Day 60: instrumentation gate (fails first) + pre-registration
  readout.py              Day 90: trial sim, z-test vs pre-registered thresholds, roadmap

agent/                  v2 — the rollout as an agentic loop
  world.py                the environment; advances one week under whatever mode the agent set
  memory.py               CONTEXT MANAGEMENT: append-only journal + compacted summary
  brain.py                DECIDE step: HeuristicBrain (default) or ClaudeBrain (opt-in LLM)
  verifier.py             VERIFICATION: preconditions, post-week safety overrides, spin detection
  loop.py                 the loop + AgentRunResult + render_markdown (views over one result)

tests/smoke_test.py     seeded checks: pre-committed verdicts + view/result consistency
docs/                   architecture.svg (v0) · architecture_v2.svg (v2) · maturity_ladder.svg
data/ logs/ reports/    GENERATED on run — gitignored, safe to delete, regenerate on next run
```

## Architecture notes for making changes

**The cage (`engine/decide.py`) is the heart of v0 and v2.**
- `SAFETY_RULES` — hard, deterministic, non-overridable allowed-action set per
  decline context. Every served action is asserted against this; a violation
  crashes the run by design. **Nothing that learns may modify it.**
- `RULES_BASELINE` — the lookup-table competitor. It serves by default; the
  bandit's greedy pick *is* the rules pick unless a challenger clears the
  evidence gate (`MIN_OBS=12` labels AND posterior mean > rules + `MARGIN=0.04`).
- `BanditRanker` — per-context Beta-Bernoulli posteriors; context is
  deliberately coarse (`decline_code × market`) so labels mature in weeks.
  Exploration is Thompson-sampled and capped at 5% **by a counter, not a coin
  flip** — the budget cannot be exceeded by luck.
- `FraudGuardrail` — rolling fraud bps; 16 warn / 18 kill, gated on `MIN_SAMPLE`
  so tripwires never fire on noise. On kill, serving auto-reverts to rules.

**The agent loop (`agent/loop.py`) is one weekly cycle:** decide → verify → act
→ observe → override → remember → terminate?
- The brain (`agent/brain.py`) can only propose from a bounded action space:
  `instrument · start_shadow · ramp{share} · freeze · escalate_human · resume ·
  final_report · wait`. The **verifier owns every precondition** — the brain
  cannot negotiate it, and an LLM brain gets zero extra authority (its JSON is
  validated against the same action space and same verifier).
- Safety overrides (`post_override` in `verifier.py`) fire **regardless of the
  brain** after each week. Resume-after-kill requires a human approval in the
  inbox — the agent cannot approve itself.
- Termination is always explicit (goal / budget / escalation SLA) and never
  silent — every stop ships a handoff report.
- **`AgentRunResult` is the single source of truth.** The console narration, the
  Markdown report (`render_markdown`), and the JSONL journal are all *renderers*
  over it. `test_v2_views_agree_with_result` asserts they cannot drift — keep it
  that way: add renderers, don't let a view carry state the result object lacks.

**The tunables are the product decisions.** `explore_budget`, `MARGIN`,
`INTERACTIONS`, `FRAUD_SPIKE` are the levers the README's "Break it on purpose"
table documents. If you change one and the *lesson* changes, update that table
and the PM decision log in `README.md`.

## Conventions

- **Docstrings carry the reasoning.** Every module opens with a substantial
  docstring explaining *why* it works the way it does, mapped to the case. Match
  this density when adding or editing code — the explanation is part of the
  deliverable, not overhead.
- Entry-point scripts (`run_v*.py`) are thin: they create output dirs, call into
  the packages, and format the console report. Keep logic in the packages.
- Generated output goes only to `data/`, `logs/`, `reports/` (gitignored). Do
  not commit generated artifacts.
- Prefer editing existing files over adding new ones; the module structure maps
  1:1 to the case narrative and should stay legible.

## When contributing

Per `CONTRIBUTING.md`, welcome changes: documentation clarity, bug fixes that
preserve seeded behavior, tests asserting pre-committed outcomes, diagram/README
improvements. **Not** welcome: redesigning core algorithms without strong
rationale, sideways scope expansion (multi-funnel, production integrations),
anything that breaks seeded reproducibility, or claims the code does not support.

After any change, confirm all three demos still run and the smoke test passes.
