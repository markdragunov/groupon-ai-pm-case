"""Decide layer: rules baseline + learning ranker inside a deterministic cage.

Architecture (mirrors the case exactly):

  SAFETY_RULES   - hard, deterministic, non-overridable. The state machine
                   defines the allowed action set per decline context. The
                   model can NEVER act outside it. Includes the card-network
                   do-not-retry list and the "no retry on timeout until state
                   resolves" rule.

  RULES_BASELINE - the lookup table (decline code -> first action). The honest
                   competitor: it captures most of the value, and the model
                   must beat it to earn live traffic.

  BanditRanker   - per-context Beta-Bernoulli posteriors over allowed actions.
                   Context is deliberately COARSE in v0 (decline_code x market)
                   so labels mature within weeks, not quarters; tender is added
                   only when volume supports it.
                   * Greedy pick = rules baseline UNLESS a challenger action
                     clears an evidence gate (>= MIN_OBS labels AND posterior
                     mean > rules + MARGIN). No gate cleared -> the engine IS
                     the table.
                   * Exploration is Thompson-sampled and CAPPED (5% budget).
                     Exploration is the price of learning and it is budgeted,
                     not free.

  FraudGuardrail - rolling fraud bps on every engine-served attempt: 16 bps
                   early warning, 18 bps kill switch that auto-reverts the
                   engine to RULES_BASELINE. The feature turns itself off
                   first; the discussion happens second.

Execution stays deterministic: this module only returns WHICH permitted
action to surface first. It never charges, never refunds above policy,
never invents an action.
"""

import json
import random
from collections import defaultdict, deque

# ---------------------------------------------------------------- action space
ACTIONS = [
    "retry_same", "retry_later", "switch_tender", "step_up_3ds",
    "wait_check_status", "self_serve_status", "auto_refund", "escalate_support",
]

# Hard deterministic constraints (the state machine). Model cannot override.
SAFETY_RULES = {
    # SCA soft decline: issuer requests 3DS - step-up is a first-class recovery
    "soft_decline_3ds": {"step_up_3ds", "switch_tender", "self_serve_status"},
    "insufficient_funds": {"switch_tender", "retry_later", "self_serve_status"},
    "do_not_honor": {"switch_tender", "retry_later", "self_serve_status"},
    "network_timeout": {"wait_check_status", "self_serve_status"},   # NEVER retry unresolved state
    "charged_no_order": {"auto_refund", "self_serve_status"},        # money-state first
    "fraud_suspected": {"escalate_support"},                         # network do-not-retry list
    "generic_error": {"retry_same", "switch_tender", "self_serve_status"},
}

# The lookup-table competitor: one static best action per decline code.
RULES_BASELINE = {
    "soft_decline_3ds": "step_up_3ds",
    "insufficient_funds": "switch_tender",
    "do_not_honor": "switch_tender",
    "network_timeout": "wait_check_status",
    "charged_no_order": "auto_refund",
    "fraud_suspected": "escalate_support",
    "generic_error": "retry_same",
}


def allowed(code: str) -> set[str]:
    return SAFETY_RULES[code]


def rules_pick(code: str) -> str:
    return RULES_BASELINE[code]


# ---------------------------------------------------------------- the ranker
class BanditRanker:
    """Per-context Beta(1,1) posteriors. Context = (decline_code, market)."""

    MIN_OBS = 12      # evidence gate: labels required before a challenger may win
    MARGIN = 0.04     # ...and by how much its posterior mean must beat rules

    def __init__(self, explore_budget: float = 0.05, seed: int = 11):
        self.a = defaultdict(lambda: defaultdict(lambda: 1))  # successes+1
        self.b = defaultdict(lambda: defaultdict(lambda: 1))  # failures+1
        self.explore_budget = explore_budget
        self.rng = random.Random(seed)
        self.explored = 0
        self.served = 0

    # -- posterior helpers
    def n_obs(self, ctx, x):
        return self.a[ctx][x] + self.b[ctx][x] - 2

    def posterior_mean(self, ctx, x):
        return self.a[ctx][x] / (self.a[ctx][x] + self.b[ctx][x])

    # -- picks
    def greedy(self, ctx) -> str:
        """Rules baseline unless a challenger clears the evidence gate."""
        code = ctx[0]
        rp = rules_pick(code)
        best, best_mean = rp, self.posterior_mean(ctx, rp)
        for x in sorted(allowed(code)):
            if x == rp or self.n_obs(ctx, x) < self.MIN_OBS:
                continue
            m = self.posterior_mean(ctx, x)
            if m > self.posterior_mean(ctx, rp) + self.MARGIN and m > best_mean:
                best, best_mean = x, m
        return best

    def explore_pick(self, ctx) -> str:
        """Thompson sample across the allowed set - uncertainty-directed."""
        code = ctx[0]
        return max(sorted(allowed(code)),
                   key=lambda x: self.rng.betavariate(self.a[ctx][x], self.b[ctx][x]))

    def serve(self, ctx) -> tuple[str, bool]:
        """Live serving: greedy, with a capped Thompson exploration slice.
        The budget is enforced by a counter, not a coin flip - exploration can
        never exceed the cap, by construction."""
        self.served += 1
        if (self.explored + 1) <= self.explore_budget * self.served:
            self.explored += 1
            return self.explore_pick(ctx), True
        return self.greedy(ctx), False

    def update(self, ctx, action: str, recovered: bool):
        if recovered:
            self.a[ctx][action] += 1
        else:
            self.b[ctx][action] += 1


# ---------------------------------------------------------------- guardrails
class FraudGuardrail:
    """Rolling fraud bps on the engine-served cohort.
    16 bps -> early warning to both teams. 18 bps -> kill switch:
    engine auto-reverts to RULES_BASELINE. Discussion happens second.
    """

    WARN_BPS = 16.0
    KILL_BPS = 18.0
    MIN_SAMPLE = 800  # don't fire tripwires on noise

    def __init__(self, window: int = 4000):
        self.events = deque(maxlen=window)
        self.warned = False
        self.killed = False

    def record(self, is_fraud: bool):
        self.events.append(1 if is_fraud else 0)
        if len(self.events) < self.MIN_SAMPLE:
            return
        bps = self.bps()
        if bps >= self.KILL_BPS:
            self.killed = True
        elif bps >= self.WARN_BPS:
            self.warned = True

    def bps(self) -> float:
        if not self.events:
            return 0.0
        return 10000.0 * sum(self.events) / len(self.events)

    def summary(self) -> dict:
        return {"bps": round(self.bps(), 1), "events": sum(self.events),
                "n": len(self.events), "warned": self.warned,
                "killed": self.killed}


# ---------------------------------------------------------------- logging
class DecisionLog:
    def __init__(self, path):
        self.f = open(path, "w")

    def write(self, **kw):
        self.f.write(json.dumps(kw) + "\n")

    def close(self):
        self.f.close()
