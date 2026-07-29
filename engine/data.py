"""Synthetic funnel data that reconciles EXACTLY with the case study arithmetic.

Case anchors (monthly):
  M1: Intl 20,000 starts, auth 93.0%, completion 85.0% | NA 65,000 starts, auth 96.0%, completion 92.0%
  M2: Intl 45,000 starts, auth 95.0%, completion 78.0% | NA 55,000 starts, auth 96.0%, completion 92.0%
  => blended auth  95.3% -> 95.6%  ("improved" - the decoy)
  => blended compl 90.3% -> 85.7%  (the real collapse)
  => Intl post-auth loss: 7,650 authorized orders/month dying in M2.

The generator emits daily rows with small seeded noise so the detector works on a
realistic series, while monthly aggregates still land on the case numbers.
"""

import csv
import random

DAYS_PER_MONTH = 30

SEGMENTS = {
    # segment: (month, daily_starts, auth_rate, completion_rate_of_starts)
    "M1": {"INTL": (667, 0.930, 0.850), "NA": (2167, 0.960, 0.920)},
    "M2": {"INTL": (1500, 0.950, 0.780), "NA": (1833, 0.960, 0.920)},
}


def generate(path: str, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    day_no = 0
    for month in ("M1", "M2"):
        for d in range(DAYS_PER_MONTH):
            day_no += 1
            for seg, (starts, auth, compl) in SEGMENTS[month].items():
                n = int(starts * rng.uniform(0.93, 1.07))
                a = min(n, int(n * (auth + rng.gauss(0, 0.004))))
                c = min(a, int(n * (compl + rng.gauss(0, 0.006))))
                rows.append(
                    {"day": day_no, "month": month, "segment": seg,
                     "starts": n, "authorized": a, "completed": c}
                )
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    return rows
