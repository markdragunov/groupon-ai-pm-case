"""Brains - pluggable DECIDE step of the agent loop.

Two implementations behind one interface, because the loop is the product and
the brain is a component:

  HeuristicBrain  - default; deterministic policy over the memory summary.
                    Deliberately EAGER (proposes ramps as early as plausible)
                    so that the verifier's rejections are exercised in every
                    run: brain proposes, verifier disposes.

  ClaudeBrain     - optional; sends the compacted summary + the action space
                    to the Anthropic API (needs ANTHROPIC_API_KEY) and expects
                    strict JSON back. Whatever comes back is validated against
                    the SAME action space and the SAME verifier - an LLM brain
                    gets zero extra authority. On any error it falls back to
                    the heuristic, and the fallback is journaled.

Bounded agent action space (the cage, one level up):
  instrument · start_shadow · ramp{share} · freeze · escalate_human ·
  resume · final_report · wait
"""

import json
import os
import urllib.request

ACTION_SPACE = ["instrument", "start_shadow", "ramp", "freeze",
                "escalate_human", "resume", "final_report", "wait"]


class HeuristicBrain:
    name = "heuristic"

    def decide(self, s):
        if not s["instrumented"]:
            return {"action": "instrument", "why": "no labels without telemetry"}
        if s["mode"] == "baseline":
            return {"action": "start_shadow", "why": "start paying for labels (5% exploration)"}
        if s["mode"] == "shadow":
            if s["gate_contexts"]:
                return {"action": "ramp", "params": {"share": 0.10},
                        "why": f"gate cleared in {len(s['gate_contexts'])} context(s)"}
            return {"action": "wait", "why": "accumulating exploration labels"}
        if s["mode"] == "live":
            if s["week"] >= 11 and s["cum_lift_pts"] is not None:
                return {"action": "final_report", "why": "evidence sufficient for a decision"}
            if s["share"] < 0.25 and (s["cum_lift_pts"] or 0) > 0:
                return {"action": "ramp", "params": {"share": 0.25},
                        "why": f"lift {s['cum_lift_pts']:+.1f} pts, guardrails clean"}
            return {"action": "wait", "why": "holding share, gathering evidence"}
        if s["mode"] == "frozen":
            if s["inbox"]:
                return {"action": "resume", "params": {"share": s["inbox"][0]["share"]},
                        "why": "human approval received"}
            if s["week"] >= 13:
                return {"action": "final_report", "why": "budget nearly spent; report with incident"}
            return {"action": "wait", "why": "frozen - awaiting human review (cannot self-approve)"}
        return {"action": "wait", "why": "default"}


class ClaudeBrain:
    """LLM decide-step. Same contract, same cage. Requires ANTHROPIC_API_KEY."""
    name = "claude"
    MODEL = "claude-sonnet-4-6"

    def __init__(self):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        self.fallback = HeuristicBrain()

    def decide(self, s):
        if not self.key:
            return {**self.fallback.decide(s), "fallback": "no ANTHROPIC_API_KEY"}
        prompt = (
            "You are the operator of a payment-recovery rollout. State summary:\n"
            + json.dumps(s, default=str)
            + "\nAllowed actions: " + ", ".join(ACTION_SPACE)
            + "\nRules you cannot override: ramps need evidence; a frozen system "
              "resumes only with human approval; when unsure, wait.\n"
            "Reply with STRICT JSON only: "
            '{"action": str, "params": {"share": float (ramp/resume only)}, "why": str}'
        )
        body = json.dumps({"model": self.MODEL, "max_tokens": 300,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"content-type": "application/json", "x-api-key": self.key,
                     "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            text = "".join(b.get("text", "") for b in data.get("content", []))
            out = json.loads(text.strip().removeprefix("```json").removesuffix("```"))
            if out.get("action") not in ACTION_SPACE:
                raise ValueError(f"action outside the space: {out.get('action')}")
            return out
        except Exception as e:                          # any failure -> safe fallback
            return {**self.fallback.decide(s), "fallback": f"claude error: {e}"}


def make_brain(kind):
    return ClaudeBrain() if kind == "claude" else HeuristicBrain()
