"""Detect layer: the auth->completion gap alert.

Two monitors run side by side on the same data:

  1. NaiveThresholdMonitor - what Groupon effectively has today: a threshold on
     BLENDED auth success. It stays green for all 60 days because blended auth
     *improves* while the Intl funnel bleeds. This is the decoy metric.

  2. JointDivergenceDetector - the engine's Detect objective: per-segment,
     it watches the JOINT behaviour of stages (auth trend vs post-auth
     completion trend) against a trailing baseline. Auth up + completion down
     is precisely the signature a single-metric threshold cannot see.

The point the demo makes: the signal existed in the data from day 1 of M2.
Detection is an analytics artifact (zero eng-weeks), not a model.
"""

from collections import defaultdict
from statistics import mean


class NaiveThresholdMonitor:
    """Alert iff blended auth success drops below a floor. (It never does.)"""

    def __init__(self, floor: float = 0.94):
        self.floor = floor
        self.alerts = []

    def run(self, rows):
        by_day = defaultdict(lambda: {"starts": 0, "auth": 0})
        for r in rows:
            by_day[r["day"]]["starts"] += r["starts"]
            by_day[r["day"]]["auth"] += r["authorized"]
        for day in sorted(by_day):
            rate = by_day[day]["auth"] / by_day[day]["starts"]
            if rate < self.floor:
                self.alerts.append((day, rate))
        return self.alerts


class JointDivergenceDetector:
    """Alarm when, within a segment, auth trend and post-auth completion trend
    diverge beyond `min_gap_pts` vs a trailing baseline window.

    post_auth_rate = completed / authorized  (the stage that actually broke:
    85->78 completion on rising auth means post-auth loss 8pt -> 17pt).
    """

    def __init__(self, baseline_days: int = 21, window: int = 5, min_gap_pts: float = 3.0):
        self.baseline_days = baseline_days
        self.window = window
        self.min_gap_pts = min_gap_pts
        self.alarms = []

    def run(self, rows):
        segs = defaultdict(dict)
        for r in rows:
            segs[r["segment"]][r["day"]] = r
        for seg, days in segs.items():
            ordered = [days[d] for d in sorted(days)]
            base = ordered[: self.baseline_days]
            base_auth = mean(r["authorized"] / r["starts"] for r in base)
            base_post = mean(r["completed"] / r["authorized"] for r in base)
            for i in range(self.baseline_days, len(ordered)):
                win = ordered[max(0, i - self.window + 1): i + 1]
                auth = mean(r["authorized"] / r["starts"] for r in win)
                post = mean(r["completed"] / r["authorized"] for r in win)
                d_auth = (auth - base_auth) * 100
                d_post = (post - base_post) * 100
                divergence = d_auth - d_post  # auth up AND post-auth down widens this
                if d_auth >= -0.5 and -d_post >= self.min_gap_pts:
                    self.alarms.append({
                        "segment": seg, "day": ordered[i]["day"],
                        "auth_delta_pts": round(d_auth, 1),
                        "post_auth_delta_pts": round(d_post, 1),
                        "divergence_pts": round(divergence, 1),
                    })
                    break  # first alarm per segment is the finding
        return self.alarms


def run_detection(rows):
    naive = NaiveThresholdMonitor().run(rows)
    joint = JointDivergenceDetector().run(rows)
    return naive, joint
