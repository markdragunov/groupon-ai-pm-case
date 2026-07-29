"""Recovery simulator: the six-week rollout as an experiment.

Ground truth: per-(decline_code, market) recovery probabilities.
Deliberately constructed so that:
  - the RULES_BASELINE table is right for MOST contexts (it captures the bulk
    of the value - the honest premise), but
  - a few contexts contain INTERACTIONS the table cannot represent (e.g.
    do_not_honor in ES recovers better with retry_later than switch_tender).
    Those pockets are the entire economic case for the ranker.

Phases (mirror the case roadmap):
  W1-2  OBSERVE          rules serve 100%; engine only accumulates labels.
                         Note what this implies: with zero exploration, only
                         the default action gets labels - you learn nothing
                         about alternatives. Exploration is not optional.
  W3-4  SHADOW+EXPLORE   rules serve 95%; a budgeted 5% exploration slice IS
                         served (the price of learning, paid consciously,
                         guardrails armed on it). Engine logs its greedy pick
                         on every decision; the disagreement cohort is scored.
  W5-6  LIVE 10%         engine serves 10% of traffic (greedy + 5% exploration
                         inside), fraud guardrail armed: 16 bps warn / 18 bps
                         kill -> auto-revert to rules.

Pre-committed success criterion: engine earns ramp beyond 10% only if
  (a) recovered-rate lift over rules on the engine cohort is positive, AND
  (b) guardrails stayed clean.
If lift ~ 0: ship the table; the instrumentation was needed anyway.
"""

import math
import random
from collections import defaultdict

from .decide import (BanditRanker, DecisionLog, FraudGuardrail, allowed,
                     rules_pick)

MARKETS = ["ES", "DE", "FR"]
CODES_WEIGHTED = [
    ("insufficient_funds", 0.26), ("do_not_honor", 0.22),
    ("soft_decline_3ds", 0.18), ("network_timeout", 0.12),
    ("charged_no_order", 0.10), ("generic_error", 0.08),
    ("fraud_suspected", 0.04),
]

# base recovery odds per (code, action)
BASE = {
    ("insufficient_funds", "switch_tender"): 0.34,
    ("insufficient_funds", "retry_later"): 0.22,
    ("insufficient_funds", "self_serve_status"): 0.10,
    ("do_not_honor", "switch_tender"): 0.30,
    ("do_not_honor", "retry_later"): 0.24,
    ("do_not_honor", "self_serve_status"): 0.09,
    ("soft_decline_3ds", "step_up_3ds"): 0.55,   # SCA step-up: highest-odds recovery in EU
    ("soft_decline_3ds", "switch_tender"): 0.28,
    ("soft_decline_3ds", "self_serve_status"): 0.08,
    ("network_timeout", "wait_check_status"): 0.62,
    ("network_timeout", "self_serve_status"): 0.40,
    ("charged_no_order", "auto_refund"): 0.0,     # not a re-conversion; a trust save
    ("charged_no_order", "self_serve_status"): 0.15,
    ("fraud_suspected", "escalate_support"): 0.05,
    ("generic_error", "retry_same"): 0.25,
    ("generic_error", "switch_tender"): 0.21,
    ("generic_error", "self_serve_status"): 0.08,
}

# interaction pockets the lookup table cannot see: same code, different best action
INTERACTIONS = {
    ("do_not_honor", "ES", "retry_later"): +0.14,        # 0.24 -> 0.38 beats switch (0.30)
    ("insufficient_funds", "DE", "retry_later"): +0.16,  # payday effect: 0.22 -> 0.38
    ("generic_error", "FR", "switch_tender"): +0.10,     # 0.21 -> 0.31 beats retry_same (0.25)
}

FRAUD_ODDS = {"retry_same": 0.0014, "retry_later": 0.0010, "switch_tender": 0.0008}
DEFAULT_FRAUD = 0.0004


def true_p(code, market, action):
    p = BASE.get((code, action), 0.02)
    p += INTERACTIONS.get((code, market, action), 0.0)
    return min(p, 0.95)


def draw_context(rng):
    r, acc = rng.random(), 0.0
    for code, w in CODES_WEIGHTED:
        acc += w
        if r <= acc:
            break
    return code, rng.choice(MARKETS)


def sample_size_per_arm(p_base, mde, alpha_z=1.96, power_z=0.84):
    """Two-proportion sample size, per arm."""
    p2 = p_base + mde
    pbar = (p_base + p2) / 2
    num = (alpha_z * math.sqrt(2 * pbar * (1 - pbar)) +
           power_z * math.sqrt(p_base * (1 - p_base) + p2 * (1 - p2))) ** 2
    return int(num / mde ** 2) + 1


def run_simulation(n_per_week=2400, seed=5, log_path="logs/decision_log.jsonl"):
    rng = random.Random(seed)
    ranker = BanditRanker(explore_budget=0.05)
    guard = FraudGuardrail()
    log = DecisionLog(log_path)

    shadow = {"n": 0, "disagree": 0, "rules_rec": 0, "engine_cf_rec": 0}
    live = {"rules": {"n": 0, "rec": 0}, "engine": {"n": 0, "rec": 0}}
    live_disagree = {"n": 0, "rec": 0, "rules_cf_rec": 0}

    for week in range(1, 7):
        phase = "observe" if week <= 2 else "shadow" if week <= 4 else "live10"
        for _ in range(n_per_week):
            ctx = draw_context(rng)
            code, market = ctx
            r_pick = rules_pick(code)
            engine_served = False

            if phase == "observe":
                served, by = r_pick, "rules"

            elif phase == "shadow":
                g_pick = ranker.greedy(ctx)
                shadow["n"] += 1
                if g_pick != r_pick:
                    shadow["disagree"] += 1
                    # simulation can score the counterfactual directly; in
                    # production this is what the exploration slice estimates
                    shadow["engine_cf_rec"] += int(rng.random() < true_p(code, market, g_pick))
                    shadow["rules_rec"] += int(rng.random() < true_p(code, market, r_pick))
                if rng.random() < 0.05:                      # budgeted exploration slice
                    served, by, engine_served = ranker.explore_pick(ctx), "explore", True
                else:
                    served, by = r_pick, "rules"

            else:  # live10
                if guard.killed:
                    served, by = r_pick, "rules(kill)"
                elif rng.random() < 0.10:
                    served, _ = ranker.serve(ctx)
                    by, engine_served = "engine", True
                else:
                    served, by = r_pick, "rules"

            recovered = rng.random() < true_p(code, market, served)
            assert served in allowed(code), "safety violation - impossible by construction"

            # labels update from every served outcome, whoever served it
            ranker.update(ctx, served, recovered)
            if engine_served:
                guard.record(rng.random() < FRAUD_ODDS.get(served, DEFAULT_FRAUD))

            if phase == "live10":
                bucket = "engine" if by == "engine" else "rules"
                live[bucket]["n"] += 1
                live[bucket]["rec"] += int(recovered)
                if by == "engine" and served != r_pick:
                    live_disagree["n"] += 1
                    live_disagree["rec"] += int(recovered)
                    live_disagree["rules_cf_rec"] += int(
                        rng.random() < true_p(code, market, r_pick))

            log.write(week=week, phase=phase, code=code, market=market,
                      allowed=sorted(allowed(code)), rules_pick=r_pick,
                      served=served, served_by=by, recovered=recovered)

    log.close()

    # what did the ranker actually learn? report the interaction pockets
    learned = []
    for (code, market, action) in INTERACTIONS:
        ctx = (code, market)
        learned.append({
            "context": f"{code} x {market}",
            "rules_pick": rules_pick(code),
            "engine_pick": ranker.greedy(ctx),
            "challenger": action,
            "n_labels": ranker.n_obs(ctx, action),
            "posterior_challenger": round(ranker.posterior_mean(ctx, action), 2),
            "posterior_rules": round(ranker.posterior_mean(ctx, rules_pick(code)), 2),
        })

    # DS honesty: what would a confirmatory read require?
    base_rate = live["rules"]["rec"] / max(live["rules"]["n"], 1)
    n_needed = sample_size_per_arm(base_rate, 0.02)

    return {"shadow": shadow, "live": live, "live_disagree": live_disagree,
            "learned": learned, "n_needed_per_arm_2pt": n_needed,
            "guard": guard.summary(),
            "explored_share": round(ranker.explored / max(ranker.served, 1), 3)}
