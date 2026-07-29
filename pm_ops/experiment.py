"""DAY 60 - First experiment live, instrumentation confirmed BEFORE launch.

JD success criterion: "First AI-driven or A/B experiment live with a clear
hypothesis and instrumentation confirmed before launch."

Two artifacts, in this order:
  1. INSTRUMENTATION GATE - a hard pre-launch check that every event the
     readout will need already exists in telemetry. The gate is expected to
     FAIL on first run (reminder_sent is not instrumented today) - that is
     the point: the experiment does not launch until it passes.
  2. PRE-REGISTRATION - hypothesis, metrics, sample size, duration, and the
     decision rule written down BEFORE data arrives, so Day 90 is a lookup,
     not a negotiation with reality.
"""

import json
import math

from engine.simulate import sample_size_per_arm

REQUIRED_EVENTS = [
    "voucher_delivered", "redemption_completed", "refund_requested",
    "refund_reason_code", "reminder_sent", "reminder_opened", "swap_offered",
]

# what telemetry has today (reminder events are the gap - the experiment's
# own treatment is the thing not yet instrumented)
EXISTING_EVENTS = [
    "voucher_delivered", "redemption_completed", "refund_requested",
    "refund_reason_code",
]


def instrumentation_gate(existing=None):
    existing = EXISTING_EVENTS if existing is None else existing
    missing = [e for e in REQUIRED_EVENTS if e not in existing]
    return {"pass": not missing, "missing": missing}


def build_spec(audit, weekly_eligible):
    """The experiment the audit points to: Redemption Rescue."""
    li = audit["leading"]
    # base: among day-10 non-redeemers, share that redeems by day 30 anyway
    base = 0.22
    mde = 0.05
    n_arm = sample_size_per_arm(base, mde)
    weeks = math.ceil(2 * n_arm / weekly_eligible)
    return {
        "name": "Redemption Rescue v1",
        "population": "vouchers unredeemed at day 10, at-risk cohorts first "
                      "(ranked by the Day-30 divergence scan)",
        "treatment": "reminder at day 10 + one-tap reschedule/swap offer; "
                     "control: status quo (nothing until refund request)",
        "hypothesis": f"treatment lifts redemption-by-30d from {base:.0%} by "
                      f">= {mde:.0%} pts absolute in the at-risk pool, and "
                      "repeat-90d follows via the leading-indicator chain "
                      f"(fast redeemers repeat at {li['redeemed_le14d'][0]:.0%} "
                      f"vs {li['never_redeemed'][0]:.0%} never-redeemers)",
        "primary_metric": "redemption_rate_30d (population above)",
        "guardrails": ["refund_rate not up (one-sided, +0.5pt cap)",
                       "unsubscribe_rate < 0.8%",
                       "support_contacts_per_1k not up"],
        "secondary": ["repeat_90d (directional; underpowered at this n - say so)"],
        "n_per_arm": n_arm, "mde_pts": mde * 100, "base_rate": base,
        "duration_weeks": weeks,
        "assignment": "voucher-level randomization, stratified by cohort",
        "decision_rule": {
            "ship": "lift >= 5pts, p<0.05, guardrails clean -> ramp to all "
                    "at-risk cohorts",
            "iterate": "lift 2-5pts -> rework timing/copy, rerun on same "
                       "pre-registration",
            "kill": "lift < 2pts or any guardrail breach -> stop; the "
                    "instrumentation stays (it was needed anyway)",
        },
    }


def write_spec(spec, gate_before, gate_after, path):
    lines = [
        f"# Day 60 - Pre-registered experiment: {spec['name']}", "",
        f"**Population:** {spec['population']}",
        f"**Treatment:** {spec['treatment']}", "",
        f"**Hypothesis:** {spec['hypothesis']}", "",
        f"**Primary metric:** {spec['primary_metric']}",
        f"**Guardrails:** {'; '.join(spec['guardrails'])}",
        f"**Secondary:** {'; '.join(spec['secondary'])}", "",
        f"**Power:** base {spec['base_rate']:.0%}, MDE {spec['mde_pts']:.0f}pts, "
        f"n = {spec['n_per_arm']:,}/arm, ~{spec['duration_weeks']} weeks at "
        "current eligible volume",
        f"**Assignment:** {spec['assignment']}", "",
        "## Instrumentation gate (must pass BEFORE launch)",
        f"- First run: FAIL - missing events: {', '.join(gate_before['missing'])}",
        f"- After instrumentation sprint: {'PASS' if gate_after['pass'] else 'FAIL'}",
        "", "## Pre-committed decision rule (written before data)",
    ]
    for k, v in spec["decision_rule"].items():
        lines.append(f"- **{k.upper()}**: {v}")
    lines += ["", "```json", json.dumps(
        {k: spec[k] for k in ("n_per_arm", "mde_pts", "base_rate", "duration_weeks")},
        indent=2), "```"]
    with open(path, "w") as f:
        f.write("\n".join(lines))
