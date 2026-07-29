"""DAY 90 - Results in, decision made, roadmap agreed.

JD success criterion: "First experiment results in. If it moved the metric,
you know why. If it didn't, you know why too. Roadmap for the next two
quarters agreed with stakeholders, with AI features as a primary lever."

Three parts:
  1. Trial simulation on the pre-registered design (seeded; effect exists in
     the at-risk cohort because that is where the mechanism lives, and is
     ~zero elsewhere - matching how real treatment effects localize).
  2. Readout: two-proportion z-test against the PRE-REGISTERED thresholds,
     then the 'why' - decomposition showing the lift concentrates exactly
     where the Day-30 mechanism predicted. Knowing why = the effect landing
     where the causal story said it would.
  3. Two-quarter roadmap derived from the audit levers, AI as primary lever,
     each item carrying its label source and guardrail (the engine pattern).
"""

import math
import random


def _z_test(x1, n1, x2, n2):
    """Two-proportion z. Returns (lift, z, p_two_sided)."""
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se if se else 0.0
    p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return p2 - p1, z, p_val


def simulate_trial(spec, seed=13):
    """At-risk pool = 55% broken-cohort-like (true effect +9pts), 45% other
    at-risk (true effect +2pts). Control base 22%."""
    rng = random.Random(seed)
    n = spec["n_per_arm"]
    segments = [("broken_cohort", 0.55, 0.20, 0.09), ("other_at_risk", 0.45, 0.24, 0.02)]
    res = {"control": {}, "treatment": {}}
    for seg, share, base, effect in segments:
        n_seg = int(n * share)
        res["control"][seg] = (sum(rng.random() < base for _ in range(n_seg)), n_seg)
        res["treatment"][seg] = (sum(rng.random() < base + effect for _ in range(n_seg)), n_seg)
    # guardrails
    res["guardrails"] = {
        "refund_rate_delta_pts": round(rng.gauss(-0.1, 0.15), 2),  # slightly down
        "unsubscribe_rate": round(abs(rng.gauss(0.4, 0.1)), 2),
        "contacts_per_1k_delta": round(rng.gauss(-1.5, 0.8), 1),
    }
    return res


def readout(spec, trial):
    xc = sum(v[0] for v in trial["control"].values())
    nc = sum(v[1] for v in trial["control"].values())
    xt = sum(v[0] for v in trial["treatment"].values())
    nt = sum(v[1] for v in trial["treatment"].values())
    lift, z, p = _z_test(xc, nc, xt, nt)

    decomposition = {}
    for seg in trial["control"]:
        sl, sz, sp = _z_test(*trial["control"][seg], *trial["treatment"][seg])
        decomposition[seg] = {"lift_pts": round(sl * 100, 1), "p": round(sp, 4),
                              "n_per_arm": trial["control"][seg][1]}

    g = trial["guardrails"]
    guardrails_clean = (g["refund_rate_delta_pts"] <= 0.5
                        and g["unsubscribe_rate"] < 0.8
                        and g["contacts_per_1k_delta"] <= 0)

    lift_pts = lift * 100
    if lift_pts >= 5 and p < 0.05 and guardrails_clean:
        decision = "SHIP - ramp to all at-risk cohorts (pre-registered rule)"
    elif lift_pts >= 2:
        decision = "ITERATE - rework timing/copy, rerun (pre-registered rule)"
    else:
        decision = "KILL - instrumentation stays (pre-registered rule)"

    return {"control": (xc, nc), "treatment": (xt, nt),
            "lift_pts": round(lift_pts, 1), "z": round(z, 2), "p": round(p, 5),
            "decomposition": decomposition, "guardrails": g,
            "guardrails_clean": guardrails_clean, "decision": decision}


ROADMAP = [
    ("Q+1", "Redemption Rescue -> engine increment",
     "ramp rescue to all at-risk cohorts; every reminder/swap outcome becomes "
     "a label for rescue-action ranking (rules table first, bandit with capped "
     "exploration when labels support it)",
     "guardrail: refund + unsubscribe caps inherited from the trial"),
    ("Q+1", "Cohort divergence alert in production",
     "the Day-30 scan as a daily job: redemption divergence by category x "
     "market pages the team on day 2, not at refund-time (zero eng - analyst "
     "+ scheduler)",
     "guardrail: alert precision reviewed monthly; noisy cells muted by min-n"),
    ("Q+2", "Refund-risk prediction at purchase time",
     "labels are now mature (2 quarters of refund reasons + rescue outcomes); "
     "predict paid_never_redeemed risk per purchase; action space bounded: "
     "reminder cadence, swap offer, proactive credit - never auto-deny",
     "guardrail: false-positive cost on honest customers priced explicitly"),
    ("Q+2", "Repeat-purchase leading-indicator model",
     "redemption-by-14d is the proven leading indicator; model ranks which "
     "post-redemption nudge to send; deterministic execution, ledger owns "
     "money-state",
     "guardrail: holdout always-on; lift reported vs rules baseline only"),
]


def write_readout(spec, ro, audit, path):
    li = audit["leading"]
    lines = [
        f"# Day 90 - Readout: {spec['name']}", "",
        f"**Result:** treatment {ro['treatment'][0]:,}/{ro['treatment'][1]:,} "
        f"vs control {ro['control'][0]:,}/{ro['control'][1]:,} -> "
        f"lift **{ro['lift_pts']:+.1f} pts** (z={ro['z']}, p={ro['p']})",
        f"**Guardrails:** refund {ro['guardrails']['refund_rate_delta_pts']:+.2f}pts, "
        f"unsub {ro['guardrails']['unsubscribe_rate']:.2f}%, "
        f"contacts {ro['guardrails']['contacts_per_1k_delta']:+.1f}/1k -> "
        f"{'clean' if ro['guardrails_clean'] else 'BREACH'}", "",
        f"**Decision (pre-registered):** {ro['decision']}", "",
        "## Why it moved - the effect landed where the mechanism predicted",
    ]
    for seg, d in ro["decomposition"].items():
        lines.append(f"- {seg}: {d['lift_pts']:+.1f} pts (n={d['n_per_arm']:,}/arm, "
                     f"p={d['p']})")
    lines += [
        "",
        "The Day-30 audit said the disease is localized (one cohort's broken "
        "redemption path) and repeat purchase hangs on fast redemption "
        f"({li['redeemed_le14d'][0]:.0%} vs {li['never_redeemed'][0]:.0%}). "
        "The lift concentrating in the broken cohort - and staying near zero "
        "elsewhere - is that causal story confirmed, not just a green p-value.",
        "", "## Next two quarters - AI as primary lever", "",
    ]
    for q, name, what, guard in ROADMAP:
        lines += [f"### {q}: {name}", what, f"*{guard}*", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
