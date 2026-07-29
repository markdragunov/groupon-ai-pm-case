"""The environment the agent acts on: the recovery world, advanced week by week.

v0 ran a HARDCODED six-week script (observe -> shadow -> live) baked into
simulate.py. v2 removes the script: the world only knows how to advance one
week under whatever mode the AGENT has set. When to instrument, when to start
shadow, when to ramp, when to freeze - those are now the agent's decisions,
gated by the verifier.

The world also injects reality: a fraud spike in configured weeks, so the run
tests the loop's behaviour under adverse feedback, not just the happy path.

Payment execution stays deterministic inside the world (engine.decide's cage);
the agent can only change the SERVING MODE, never the safety rules.
"""

import random

from engine.decide import BanditRanker, rules_pick
from engine.simulate import DEFAULT_FRAUD, FRAUD_ODDS, INTERACTIONS, draw_context, true_p

WEEKLY_VOLUME = 4000
FRAUD_SPIKE = {7: 22.0, 8: 22.0}   # week -> fraud-odds multiplier on served retries


class World:
    def __init__(self, seed=17):
        self.rng = random.Random(seed)
        self.ranker = BanditRanker(explore_budget=0.05)
        self.week = 0
        self.mode = "baseline"          # baseline | shadow | live | frozen
        self.share = 0.0                # live traffic share served by the engine
        self.instrumented = False
        self.history = []               # weekly reports

    # ------------------------------------------------- agent-visible controls
    def set_mode(self, mode, share=None):
        self.mode = mode
        if share is not None:
            self.share = share

    # ------------------------------------------------------------- one week
    def step(self):
        self.week += 1
        mult = FRAUD_SPIKE.get(self.week, 1.0)
        eng = {"n": 0, "rec": 0, "fraud": 0}
        rules = {"n": 0, "rec": 0}

        for _ in range(WEEKLY_VOLUME):
            ctx = draw_context(self.rng)
            code, market = ctx
            r_pick = rules_pick(code)
            engine_served = False

            if self.mode == "shadow" and self.rng.random() < 0.05:
                served, engine_served = self.ranker.explore_pick(ctx), True
            elif self.mode == "live" and self.rng.random() < self.share:
                served, engine_served = self.ranker.serve(ctx)[0], True
            else:
                served = r_pick

            recovered = self.rng.random() < true_p(code, market, served)
            if self.instrumented:                       # no telemetry, no labels
                self.ranker.update(ctx, served, recovered)

            if engine_served:
                eng["n"] += 1
                eng["rec"] += int(recovered)
                odds = FRAUD_ODDS.get(served, DEFAULT_FRAUD) * mult
                eng["fraud"] += int(self.rng.random() < odds)
            else:
                rules["n"] += 1
                rules["rec"] += int(recovered)

        report = {
            "week": self.week, "mode": self.mode, "share": self.share,
            "engine_n": eng["n"],
            "engine_rec_rate": eng["rec"] / eng["n"] if eng["n"] else None,
            "rules_rec_rate": rules["rec"] / rules["n"],
            "fraud_bps": 10000 * eng["fraud"] / eng["n"] if eng["n"] else 0.0,
            "fraud_events": eng["fraud"], "fraud_n": eng["n"],
            "gate_contexts": self.gate_contexts(),
            "labels_total": sum(self.ranker.n_obs(c, a)
                                for c in list(self.ranker.a)
                                for a in self.ranker.a[c]),
        }
        self.history.append(report)
        return report

    # -------------------------------------------------------------- evidence
    def gate_contexts(self):
        """Contexts where a challenger has cleared the evidence gate, i.e.
        the engine's greedy pick differs from the rules baseline."""
        out = []
        for ctx in list(self.ranker.a):
            if self.ranker.greedy(ctx) != rules_pick(ctx[0]):
                out.append(f"{ctx[0]} x {ctx[1]}")
        return sorted(set(out))

    def cumulative_live(self, exclude_weeks=()):
        e_n = e_r = r_n = r_r = 0
        for h in self.history:
            if h["mode"] == "live" and h["week"] not in exclude_weeks and h["engine_n"]:
                e_n += h["engine_n"]
                e_r += int(h["engine_rec_rate"] * h["engine_n"])
                r_n += 4000 - h["engine_n"]
                r_r += int(h["rules_rec_rate"] * (4000 - h["engine_n"]))
        return {"engine": (e_r, e_n), "rules": (r_r, r_n),
                "lift_pts": (e_r / e_n - r_r / r_n) * 100 if e_n and r_n else None}
