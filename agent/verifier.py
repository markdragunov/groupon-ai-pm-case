"""Verifier - the loop's answer to VERIFICATION (and half of TERMINATION).

Same pattern as the payment engine, one level up: the brain PROPOSES an
action; the verifier decides whether it may execute. The brain is allowed to
be eager/wrong - the verifier is not.

Three jobs:
  1. Preconditions  - evidence gates on every state-changing action
                      (you cannot ramp on vibes).
  2. Post-checks    - after each week, safety overrides fire REGARDLESS of
                      what the brain wants: guardrail breach while live =>
                      forced freeze + human escalation. The brain cannot
                      talk its way past this, and cannot un-freeze itself:
                      resuming after a kill is a HUMAN decision by design.
  3. Spin detection - the same rejected action twice in a row => forced
                      escalation. A loop retrying the same move isn't
                      learning, it's spinning.
"""

KILL_BPS, WARN_BPS, MIN_FRAUD_N = 18.0, 16.0, 300
MIN_FRAUD_EVENTS = 3   # a tripwire that fires on one event is noise, not safety


def precheck(action, params, s):
    """(ok, reason). s = memory summary."""
    a = action
    if a == "instrument":
        return (not s["instrumented"], "already instrumented")
    if a == "start_shadow":
        if not s["instrumented"]:
            return False, "no telemetry: instrument first (no labels without it)"
        return (s["mode"] == "baseline", f"mode is {s['mode']}, not baseline")
    if a == "ramp":
        share = params.get("share", 0.10)
        if s["mode"] == "shadow":
            if s["weeks_in_mode"] < 2:
                return False, "shadow needs >=2 weeks of exploration labels before live"
            if not s["gate_contexts"]:
                return False, "no context has cleared the evidence gate yet"
            return (abs(share - 0.10) < 1e-9, "first live step is 10%, no skipping")
        if s["mode"] == "live":
            if share <= s["share"]:
                return False, "ramp must increase share"
            if s["weeks_at_share"] < 2:
                return False, f"only {s['weeks_at_share']}w at {s['share']:.0%}: hold 2w per step"
            if s["cum_lift_pts"] is None or s["cum_lift_pts"] <= 0:
                return False, f"cumulative lift is {s['cum_lift_pts']} - not positive"
            if not s["guardrails_clean"]:
                return False, "guardrails not clean last week"
            return True, ""
        return False, f"cannot ramp from mode {s['mode']}"
    if a == "freeze":
        return (s["mode"] in ("shadow", "live"), "nothing to freeze")
    if a == "escalate_human":
        return (s["open_escalation"] is None, "escalation already open")
    if a == "resume":
        if s["mode"] != "frozen":
            return False, "not frozen"
        if not s["inbox"]:
            return False, "no human approval in inbox - the agent cannot approve itself"
        if s["last_fraud_bps"] >= WARN_BPS and s["last_fraud_n"] >= MIN_FRAUD_N:
            return False, "fraud still above warn level"
        return True, ""
    if a == "final_report":
        cum_ok = s["cum_lift_pts"] is not None
        return (s["week"] >= 10 and cum_ok or s["week"] >= 13,
                "too early: need >=10 weeks and live evidence")
    if a == "wait":
        return True, ""
    return False, f"unknown action {a}"


def post_override(report, s):
    """Safety overrides after the week runs. Returns forced action or None."""
    if report["mode"] == "live" and report["fraud_n"] >= MIN_FRAUD_N \
            and report["fraud_events"] >= MIN_FRAUD_EVENTS \
            and report["fraud_bps"] >= KILL_BPS:
        return ("freeze_and_escalate",
                f"fraud {report['fraud_bps']:.0f} bps >= {KILL_BPS:.0f} "
                f"({report['fraud_events']} events / n={report['fraud_n']}) - kill switch")
    return None


class SpinDetector:
    """Spinning = the SAME action rejected for the SAME reason, back to back.
    Different reasons mean the world moved - that is iteration, not a spin.
    Any accepted action resets the detector."""

    def __init__(self):
        self.last = None
        self.count = 0

    def rejected(self, action, reason):
        key = (action, reason)
        self.count = self.count + 1 if key == self.last else 1
        self.last = key
        return self.count >= 2

    def accepted(self):
        self.last, self.count = None, 0
