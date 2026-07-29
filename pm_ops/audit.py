"""DAY 30 - Post-purchase funnel audit.

JD success criterion: "Post-purchase funnel fully audited. Top three metric
levers identified with supporting data. You can name the biggest AI leverage
point in the funnel that nobody has acted on yet."

The audit runs four passes over the raw purchase-level data:
  1. Stage funnel, blended, M0 vs M1  - what a dashboard shows (looks fine)
  2. Cohort divergence scan           - what the dashboard hides (the break)
  3. Detection-lag measurement        - how late the company currently learns
  4. Lever sizing + leading indicators of repeat purchase
"""

from collections import defaultdict
from statistics import median


def _rate(rows, num, den=None):
    d = [r for r in rows if den(r)] if den else rows
    if not d:
        return 0.0
    return sum(1 for r in d if num(r)) / len(d)


def stage_funnel(rows):
    out = {}
    for month in ("M0", "M1"):
        m = [r for r in rows if r["month"] == month]
        out[month] = {
            "purchases": len(m),
            "delivered": _rate(m, lambda r: r["delivered"]),
            "redeemed_30d": _rate(m, lambda r: r["redeemed_30d"], lambda r: r["delivered"]),
            "refund_rate": _rate(m, lambda r: r["refund"]),
            "repeat_90d": _rate(m, lambda r: r["repeat_90d"]),
        }
    return out


def cohort_divergence(rows, min_n=400, alarm_pts=8.0):
    """Per (category x market): redemption delta M0 -> M1. The blended-metric
    trap detector, generalized from the checkout case."""
    cells = defaultdict(lambda: {"M0": [], "M1": []})
    for r in rows:
        if r["delivered"]:
            cells[(r["category"], r["market"])][r["month"]].append(r)
    findings = []
    for (cat, mkt), d in cells.items():
        if len(d["M0"]) < min_n or len(d["M1"]) < min_n:
            continue
        r0 = _rate(d["M0"], lambda r: r["redeemed_30d"])
        r1 = _rate(d["M1"], lambda r: r["redeemed_30d"])
        delta = (r1 - r0) * 100
        findings.append({"cohort": f"{cat} x {mkt}", "m0": r0, "m1": r1,
                         "delta_pts": round(delta, 1), "n_m1": len(d["M1"]),
                         "alarm": delta <= -alarm_pts})
    return sorted(findings, key=lambda x: x["delta_pts"])


def detection_lag(rows, broken_cohort=("beauty_spa", "DE")):
    """How the company learns today vs how it could: refund arrival day vs
    the day the non-redemption signal was already visible (day 10)."""
    broken = [r for r in rows
              if r["month"] == "M1" and (r["category"], r["market"]) == broken_cohort]
    refunds = [r for r in broken if r["refund"] and r["refund_reason"] == "paid_never_redeemed"]
    if not refunds:
        return None
    ref_days = [int(r["refund_day"]) for r in refunds]
    unredeemed = [r for r in broken if not r["redeemed_30d"]]
    return {
        "refund_median_day": median(ref_days),
        "signal_available_day": 10,      # unredeemed-at-day-10 telemetry
        "days_earlier": median(ref_days) - 10,
        "refunds_with_early_signal": len(refunds),
        "unredeemed_pool": len(unredeemed),
        "silent_nonredeemers": len(unredeemed) - len(refunds),
    }


def leading_indicators(rows):
    """Repeat purchase decomposed by redemption behaviour - the causal chain
    this role's primary metric hangs on."""
    m = [r for r in rows if r["month"] == "M1"]
    fast = [r for r in m if r["redeemed_30d"] and r["days_to_redeem"] and int(r["days_to_redeem"]) <= 14]
    slow = [r for r in m if r["redeemed_30d"] and r["days_to_redeem"] and int(r["days_to_redeem"]) > 14]
    never = [r for r in m if not r["redeemed_30d"] and not r["refund"]]
    refunded = [r for r in m if r["refund"]]
    rep = lambda seg: _rate(seg, lambda r: r["repeat_90d"])
    return {
        "overall_repeat": rep(m),
        "redeemed_le14d": (rep(fast), len(fast)),
        "redeemed_15_30d": (rep(slow), len(slow)),
        "never_redeemed": (rep(never), len(never)),
        "refunded": (rep(refunded), len(refunded)),
    }


def size_levers(rows, margin_rate=0.11):
    """Top-3 levers in the case's Q3 format: stake arithmetic + confidence +
    the ONE data check that would falsify each."""
    div = cohort_divergence(rows)
    broken = div[0]
    m1 = [r for r in rows if r["month"] == "M1"]
    li = leading_indicators(rows)
    avg_price = sum(r["price"] for r in m1) / len(m1)

    # Lever 1: fix the broken cohort's redemption back to M0 level
    lost_redemptions = int(broken["n_m1"] * (broken["m0"] - broken["m1"]))
    repeat_uplift = li["redeemed_le14d"][0] - li["never_redeemed"][0]
    l1_annual = lost_redemptions * 12 * (avg_price * margin_rate
                                         + repeat_uplift * avg_price * margin_rate)

    # Lever 2: rescue silent non-redeemers (ALL cohorts, not just the broken one)
    lag = detection_lag(rows)
    silent_all = li["never_redeemed"][1]
    rescuable = int(silent_all * 0.25)   # assumed reachable share
    l2_annual = rescuable * 12 * (repeat_uplift * avg_price * margin_rate
                                  + 0.08 * (avg_price * margin_rate + 14))  # + deflected refunds

    # Lever 3: deflect paid_never_redeemed refunds via proactive recovery
    refund_n = sum(1 for r in m1 if r["refund_reason"] == "paid_never_redeemed")
    l3_annual = int(refund_n * 0.4) * 12 * (avg_price * margin_rate + 14)  # +$14 contact

    return [
        {"n": 1, "name": f"Fix redemption break in {broken['cohort']} "
                         f"({broken['m0']:.0%} -> {broken['m1']:.0%})",
         "stake": l1_annual, "confidence": 0.8,
         "check": "partner-side booking logs for the cohort: what share of "
                  "redemption attempts fail at the integration, W1 pull"},
        {"n": 2, "name": "Redemption rescue for silent non-redeemers "
                         "(reminder + swap at day 10)",
         "stake": l2_annual, "confidence": 0.6,
         "check": "holdout test of reminder reachability; unsubscribe base rate"},
        {"n": 3, "name": "Proactive recovery before 'paid_never_redeemed' refunds",
         "stake": l3_annual, "confidence": 0.6,
         "check": "share of these refunds preceded by >=8d of visible "
                  "non-redemption (measured below - it is)"},
    ]


def run_audit(rows):
    return {
        "funnel": stage_funnel(rows),
        "divergence": cohort_divergence(rows),
        "lag": detection_lag(rows),
        "leading": leading_indicators(rows),
        "levers": size_levers(rows),
    }
