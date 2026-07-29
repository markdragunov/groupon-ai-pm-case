#!/usr/bin/env python3
"""AI Recovery Engine - runnable v0 on the case data.

    python3 run_v0_engine.py

Produces: data/funnel.csv, logs/decision_log.jsonl, console report.
Stdlib only. Seeded - fully reproducible.
"""

import os

from engine.data import generate
from engine.detect import run_detection
from engine.simulate import run_simulation

BAR = "=" * 76


def main():
    for _d in ['data', 'logs']:
        os.makedirs(_d, exist_ok=True)
    print(BAR)
    print("v0 · RECOVERY ENGINE   (Observe > Detect > Predict > Decide > Learn)")
    print(BAR)

    # ---------------------------------------------------------------- DETECT
    rows = generate("data/funnel.csv")
    naive, joint = run_detection(rows)

    m2 = [r for r in rows if r["month"] == "M2" and r["segment"] == "INTL"]
    auth = sum(r["authorized"] for r in m2)
    comp = sum(r["completed"] for r in m2)
    print("\n[1] DETECT - two monitors, same 60 days of data")
    print(f"    Naive monitor (threshold on BLENDED auth): {len(naive)} alerts in 60 days.")
    print("      -> stays green: blended auth 'improved' 95.3% -> 95.6% (the decoy).")
    for a in joint:
        if a["segment"] == "INTL":
            print(f"    Joint divergence detector: ALARM on day {a['day']} "
                  f"(day {a['day']-30} of M2), segment INTL:")
            print(f"      auth {a['auth_delta_pts']:+.1f} pts vs baseline, "
                  f"post-auth completion {a['post_auth_delta_pts']:+.1f} pts, "
                  f"divergence {a['divergence_pts']:.1f} pts.")
    print(f"    Ground truth in this dataset: {auth - comp:,} authorized Intl orders "
          f"died post-auth in M2 (case: 7,650).")
    print("    Cost of this detector: one analyst, zero eng-weeks. It turns")
    print("    quarter-end discovery into day-2 discovery.")

    # ------------------------------------------------------- DECIDE + LEARN
    print("\n[2] DECIDE - rules baseline vs learning ranker, six simulated weeks")
    res = run_simulation()

    sh = res["shadow"]
    dis_rate = sh["disagree"] / max(sh["n"], 1)
    print("    W1-2 OBSERVE       : rules serve 100%. Zero exploration => only the")
    print("                         default action earns labels. Learning has not started.")
    print("    W3-4 SHADOW+EXPLORE: rules serve 95%; a budgeted 5% exploration slice")
    print("                         is served (the conscious price of learning).")
    print(f"      engine greedy disagreed with rules on {dis_rate:.1%} of decisions "
          f"({sh['disagree']:,}/{sh['n']:,})")
    if sh["disagree"]:
        print(f"      disagreement cohort, recovered rate: rules {sh['rules_rec']/sh['disagree']:.1%}"
              f" vs engine(counterfactual) {sh['engine_cf_rec']/sh['disagree']:.1%}")
    lr, le = res["live"]["rules"], res["live"]["engine"]
    r_rate, e_rate = lr["rec"] / max(lr["n"], 1), le["rec"] / max(le["n"], 1)
    print("    W5-6 LIVE 10%      : engine serves 10% (greedy + capped exploration)")
    print(f"      rules cohort : {lr['rec']:,}/{lr['n']:,} recovered = {r_rate:.1%}")
    print(f"      engine cohort: {le['rec']:,}/{le['n']:,} recovered = {e_rate:.1%}"
          f"   (lift {(e_rate - r_rate)*100:+.1f} pts)")
    ld = res["live_disagree"]
    if ld["n"]:
        print(f"      where engine disagreed with rules (n={ld['n']}): engine "
              f"{ld['rec']/ld['n']:.1%} vs rules(counterfactual) "
              f"{ld['rules_cf_rec']/ld['n']:.1%} - the lift lives exactly here")
    print(f"      exploration spent: {res['explored_share']:.1%} of engine traffic (cap 5%)")

    print("\n    Interaction pockets (same decline code, different best action -")
    print("    the thing a lookup table cannot represent):")
    for p in res["learned"]:
        got_it = "LEARNED" if p["engine_pick"] == p["challenger"] else "needs more labels"
        print(f"      {p['context']:<26} rules: {p['rules_pick']:<13} engine: {p['engine_pick']:<13}"
              f" [{got_it}, n={p['n_labels']}, post {p['posterior_challenger']:.2f} vs {p['posterior_rules']:.2f}]")

    print("\n    DS honesty: a confirmatory +2pt read at this base rate needs "
          f"~{res['n_needed_per_arm_2pt']:,}/arm;")
    print("    the 10% ramp continues to gather it only because guardrails stay clean.")

    # ---------------------------------------------------------- GUARDRAILS
    g = res["guard"]
    print("\n[3] GUARDRAILS - deterministic cage around the model")
    print("    Safety rules: every pick asserted against the state machine's allowed")
    print("    set in code - a violation crashes the demo. Do-not-retry list enforced;")
    print("    timeout never retried before state resolution; money-state from ledger.")
    print(f"    Fraud on engine-served cohort: {g['bps']} bps "
          f"({g['events']} events / {g['n']:,} attempts)")
    print(f"      warn @16 bps: {'FIRED' if g['warned'] else 'clean'} | "
          f"kill @18 bps: {'FIRED -> auto-reverted to rules' if g['killed'] else 'armed, clean'} "
          f"| tripwires gate on n>=800 to avoid firing on noise")

    # ------------------------------------------------------------- VERDICT
    print("\n[4] PRE-COMMITTED DECISION RULE")
    ok = e_rate > r_rate and not g["killed"]
    verdict = ("engine earns the next ramp step" if ok
               else "SHIP THE TABLE - model did not buy its way in")
    print(f"    lift > 0 AND guardrails clean?  ->  {verdict}")
    print("    Either result is cheap: instrumentation and labels were needed for the")
    print("    deterministic fix anyway. Full decision trail: logs/decision_log.jsonl")
    print(BAR)


if __name__ == "__main__":
    main()
