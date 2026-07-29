#!/usr/bin/env python3
"""AI Product Ops - the first 90 days, executable.

    python3 run_v1_product_ops.py

Maps 1:1 to the role's success criteria:
  Day 30  funnel audited, top-3 levers sized, the unacted AI leverage point named
  Day 60  experiment pre-registered, instrumentation gate passed BEFORE launch
  Day 90  readout vs pre-registered rule, why-it-moved decomposition, 2Q roadmap

Artifacts: data/postpurchase.csv, reports/day60_experiment_spec.md,
reports/day90_readout.md. Stdlib only, seeded, reproducible.
"""

import os

from pm_ops.audit import run_audit
from pm_ops.data import generate
from pm_ops.experiment import build_spec, instrumentation_gate, write_spec
from pm_ops.readout import readout, simulate_trial, write_readout

BAR = "=" * 76


def main():
    for _d in ['data', 'reports']:
        os.makedirs(_d, exist_ok=True)
    print(BAR)
    print("v1 · AI PRODUCT OPS - THE 90-DAY PLAN, EXECUTABLE   (post-purchase funnel)")
    print(BAR)

    rows = generate("data/postpurchase.csv")

    # ------------------------------------------------------------- DAY 30
    audit = run_audit(rows)
    f = audit["funnel"]
    print("\n[DAY 30] FUNNEL AUDIT")
    print("    Blended funnel, M0 -> M1 (what the dashboard shows):")
    print(f"      redemption 30d : {f['M0']['redeemed_30d']:.1%} -> {f['M1']['redeemed_30d']:.1%}"
          "   <- looks stable")
    print(f"      refund rate    : {f['M0']['refund_rate']:.1%} -> {f['M1']['refund_rate']:.1%}")
    print(f"      repeat 90d     : {f['M0']['repeat_90d']:.1%} -> {f['M1']['repeat_90d']:.1%}")
    print("    Cohort divergence scan (what the dashboard hides):")
    for d in audit["divergence"][:3]:
        flag = "  << ALARM" if d["alarm"] else ""
        print(f"      {d['cohort']:<24} {d['m0']:.0%} -> {d['m1']:.0%} "
              f"({d['delta_pts']:+.1f} pts, n={d['n_m1']:,}){flag}")
    lag = audit["lag"]
    print("    Detection lag (how the company learns today):")
    print(f"      refund request arrives at median day {lag['refund_median_day']:.0f}; "
          f"non-redemption was visible by day {lag['signal_available_day']}")
    print(f"      -> the signal exists {lag['days_earlier']:.0f} days before the company "
          "reacts, and only")
    print(f"      {lag['refunds_with_early_signal']:,} of {lag['unredeemed_pool']:,} "
          f"non-redeemers even ask ({lag['silent_nonredeemers']:,} churn silently).")
    li = audit["leading"]
    print("    Repeat purchase and its leading indicator:")
    print(f"      overall {li['overall_repeat']:.1%} | redeemed<=14d "
          f"{li['redeemed_le14d'][0]:.1%} | 15-30d {li['redeemed_15_30d'][0]:.1%} | "
          f"never {li['never_redeemed'][0]:.1%} | refunded {li['refunded'][0]:.1%}")
    print("    Top-3 levers (stake x confidence + the one falsifying check):")
    for l in audit["levers"]:
        print(f"      #{l['n']} {l['name']}")
        print(f"         ~${l['stake']:,.0f}/yr margin, conf {l['confidence']}. "
              f"Check: {l['check']}")
    print("    Week-1 pick: #1 (root cause, highest confidence) - #3 is largely its")
    print("    symptom, and #2 rides on the same instrumentation. Same structure as")
    print("    checkout: fix the cause, let recovery pay for the wait.")
    print("    THE UNACTED AI LEVERAGE POINT: the company learns a redemption went")
    print("    bad when the refund request arrives - detection, prediction and")
    print("    proactive recovery all live in the gap between day 10 and day "
          f"{lag['refund_median_day']:.0f}.")

    # ------------------------------------------------------------- DAY 60
    # eligible pool = at-risk vouchers across ALL cohorts (day-10 non-redeemers),
    # not just the broken one - otherwise the trial cannot read out by day 90
    weekly_eligible = int(audit["leading"]["never_redeemed"][1] / 4.33)
    spec = build_spec(audit, weekly_eligible)
    gate_before = instrumentation_gate()
    # after the instrumentation sprint all required events exist:
    from pm_ops.experiment import REQUIRED_EVENTS
    gate_after = instrumentation_gate(existing=REQUIRED_EVENTS)
    write_spec(spec, gate_before, gate_after, "reports/day60_experiment_spec.md")
    print("\n[DAY 60] FIRST EXPERIMENT - PRE-REGISTERED")
    print(f"    {spec['name']}: {spec['treatment'][:60]}...")
    print(f"    Power: base {spec['base_rate']:.0%}, MDE {spec['mde_pts']:.0f}pts -> "
          f"n={spec['n_per_arm']:,}/arm, ~{spec['duration_weeks']} weeks at "
          f"{weekly_eligible:,} eligible/week")
    print(f"    Instrumentation gate BEFORE launch: FAIL first "
          f"(missing: {', '.join(gate_before['missing'])})")
    print(f"    -> instrumentation sprint -> gate re-run: "
          f"{'PASS - launch unblocked' if gate_after['pass'] else 'FAIL'}")
    print("    Decision rule written before data: ship >=5pts | iterate 2-5 | kill <2")
    print("    Full pre-registration: reports/day60_experiment_spec.md")

    # ------------------------------------------------------------- DAY 90
    trial = simulate_trial(spec)
    ro = readout(spec, trial)
    write_readout(spec, ro, audit, "reports/day90_readout.md")
    print("\n[DAY 90] READOUT AGAINST THE PRE-REGISTERED RULE")
    print(f"    Overall lift: {ro['lift_pts']:+.1f} pts (z={ro['z']}, p={ro['p']}) | "
          f"guardrails {'clean' if ro['guardrails_clean'] else 'BREACH'}")
    print("    Why it moved - decomposition vs the Day-30 mechanism:")
    for seg, d in ro["decomposition"].items():
        print(f"      {seg:<16} {d['lift_pts']:+.1f} pts (n={d['n_per_arm']:,}/arm, "
              f"p={d['p']})")
    print("      -> lift concentrates in the broken cohort, ~zero elsewhere: the")
    print("         causal story from Day 30 confirmed, not just a green p-value.")
    print(f"    DECISION: {ro['decision']}")
    print("    Two-quarter roadmap (AI as primary lever, every item ships labels +")
    print("    guardrails): reports/day90_readout.md")
    print(BAR)


if __name__ == "__main__":
    main()
