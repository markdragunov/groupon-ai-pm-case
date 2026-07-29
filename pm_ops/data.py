"""Synthetic POST-PURCHASE dataset: purchase -> voucher delivery -> redemption
-> refund? -> repeat purchase (90d).

Built to contain the same disease as the checkout case, one funnel to the
right, hidden the same way:

  * BLENDED 30-day redemption looks stable month-over-month (~76%),
  * while one cohort - Beauty & Spa x DE - collapses 78% -> 57% in M1
    (a partner-side booking integration break), masked by mix shift.

  * Refund reason "paid_never_redeemed" concentrates in that cohort, and the
    refund request arrives at a median of ~day 18 - while the non-redemption
    signal (no redemption by day 10) was visible in telemetry ~8 days earlier.
    Today the company learns a redemption went bad when the refund arrives.

  * Repeat purchase is causally downstream of fast redemption: customers who
    redeem within 14 days repeat at ~3x the rate of those who never redeem.
    That makes redemption-by-14d the leading indicator of the metric this
    role owns.

Every record: month, market, category, price, delivered, days_to_redeem
(None = never), refund / refund_reason / refund_day, repeat_90d.
"""

import csv
import random

MARKETS = ["DE", "FR", "ES"]
CATEGORIES = ["beauty_spa", "restaurants", "activities", "goods"]
MONTHLY_VOLUME = {"M0": 40000, "M1": 42000}   # M0 = two months ago, M1 = last month

# base 30d redemption rate per category
BASE_REDEMPTION = {"beauty_spa": 0.78, "restaurants": 0.82, "activities": 0.74, "goods": 0.88}
# the hidden break: cohort -> redemption rate override in M1
BREAK_COHORT = ("beauty_spa", "DE")
BREAK_RATE_M1 = 0.57

REPEAT_IF_REDEEMED_FAST = 0.34   # redeemed <= 14d
REPEAT_IF_REDEEMED_SLOW = 0.22   # redeemed 15-30d
REPEAT_IF_NOT_REDEEMED = 0.11
REPEAT_IF_REFUNDED = 0.07

AVG_PRICE = {"beauty_spa": 49, "restaurants": 38, "activities": 55, "goods": 42}
CONTRIBUTION_MARGIN_RATE = 0.11   # assumed; flagged as assumption in the audit


def generate(path: str, seed: int = 21) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for month, vol in MONTHLY_VOLUME.items():
        for _ in range(vol):
            market = rng.choice(MARKETS)
            # mix shift that masks the break: goods share grows in M1
            cat = rng.choices(CATEGORIES, weights=[0.20, 0.28, 0.22, 0.30]
                              if month == "M1" else [0.24, 0.28, 0.24, 0.24])[0]
            price = max(12, rng.gauss(AVG_PRICE[cat], AVG_PRICE[cat] * 0.35))

            delivered = rng.random() < 0.995
            red_rate = BASE_REDEMPTION[cat]
            if month == "M1" and (cat, market) == BREAK_COHORT:
                red_rate = BREAK_RATE_M1
            redeemed = delivered and rng.random() < red_rate
            days_to_redeem = min(30, max(1, int(rng.expovariate(1 / 9)) + 1)) if redeemed else None

            refund, reason, refund_day = False, "", None
            if not redeemed:
                p_refund = 0.30 if (month == "M1" and (cat, market) == BREAK_COHORT) else 0.12
                if rng.random() < p_refund:
                    refund, reason = True, "paid_never_redeemed"
                    refund_day = max(8, int(rng.gauss(18, 5)))
            elif rng.random() < 0.02:
                refund, reason = True, rng.choice(["bad_experience", "merchant_refused", "other"])
                refund_day = (days_to_redeem or 5) + rng.randint(0, 4)

            if refund:
                p_rep = REPEAT_IF_REFUNDED
            elif redeemed and days_to_redeem <= 14:
                p_rep = REPEAT_IF_REDEEMED_FAST
            elif redeemed:
                p_rep = REPEAT_IF_REDEEMED_SLOW
            else:
                p_rep = REPEAT_IF_NOT_REDEEMED
            repeat = rng.random() < p_rep

            rows.append({
                "month": month, "market": market, "category": cat,
                "price": round(price, 2), "delivered": int(delivered),
                "days_to_redeem": days_to_redeem if days_to_redeem else "",
                "redeemed_30d": int(redeemed), "refund": int(refund),
                "refund_reason": reason, "refund_day": refund_day or "",
                "repeat_90d": int(repeat),
            })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    return rows
