"""The loop itself: decide -> verify -> act -> observe -> remember -> repeat,
until a TERMINATION rule fires.

Termination (all three kinds, explicit):
  * goal      - final_report issued with live evidence -> DONE
  * budget    - MAX_WEEKS spent -> stop with a handoff report (never silent)
  * escalation- open human escalation past the review SLA with no approval
                -> stop and hand off (the agent does not wait forever, and it
                does not proceed without the human either)

Human-in-the-loop is a first-class node: escalations go to an inbox; in this
demo the human review is SIMULATED with a 2-week latency and an approval to
resume at a reduced share. The agent cannot approve itself - verifier-enforced.

Every run terminates into an `AgentRunResult`. The console narration, the
Markdown report and any later view are RENDERERS over that object, while the
append-only journal stays the audit trail. No single rendering is the agent's
interface - which is why adding one cannot change what the agent decided.
"""

from dataclasses import dataclass, field

from .brain import make_brain
from .memory import Memory
from .verifier import SpinDetector, post_override, precheck
from .world import World

MAX_WEEKS = 14
REVIEW_LATENCY = 2   # weeks until the simulated human answers an escalation
REPORT_PATH = "reports/agent_run.md"


@dataclass
class AgentRunResult:
    """One run's terminal state, structured.

    Holds the verdict plus the evidence it rests on, the weekly history and
    the journal events. Views read this; none of them owns it.
    """

    verdict: str
    weeks: int
    budget_exhausted: bool
    lift_pts: float | None
    engine: tuple[int, int]
    rules: tuple[int, int]
    gate_contexts: list[str]
    incidents: list[dict]
    events: list[dict]
    history: list[dict]
    journal_path: str
    handoff: str | None = None
    report_path: str = REPORT_PATH


def render_markdown(result: AgentRunResult) -> str:
    """The Markdown view of a run - one representation, not the interface."""
    weeks = f"{result.weeks}{' (budget exhausted)' if result.budget_exhausted else ''}"
    lines = ["# Agent run - final recommendation", "", f"- Weeks: {weeks}"]
    if result.lift_pts is not None:
        er, en = result.engine
        rr, rn = result.rules
        lines.append(f"- Evidence (live, ex-incident weeks): engine {er}/{en} vs "
                     f"rules {rr}/{rn} -> lift {result.lift_pts:+.1f} pts")
    else:
        lines.append("- Evidence: no clean live weeks")
    lines.append(f"- Gated contexts: {', '.join(result.gate_contexts) or 'none'}")
    if result.incidents:
        detail = "; ".join(f"week {i['week']} - {i['what']}" for i in result.incidents)
        lines.append(f"- Incidents: {detail} "
                     "(kill switch fired, human approved resume)")
    else:
        lines.append("- Incidents: none")
    if result.handoff:
        lines.append(f"- Handoff: {result.handoff}")
    lines += [f"- Recommendation: **{result.verdict}**", "",
              "Every decision, rejection, override and approval: "
              f"{result.journal_path}"]
    return "\n".join(lines)


def run(brain_kind="heuristic", journal_path="logs/agent_journal.jsonl", quiet=False):
    world, mem = World(), Memory(journal_path)
    brain, spin = make_brain(brain_kind), SpinDetector()
    say = (lambda *a: None) if quiet else print
    pending_review = None   # (week_escalated, approval_dict)
    outcome = None

    say(f"    brain: {brain.name} | action space is bounded; verifier is not optional\n")

    while world.week < MAX_WEEKS and outcome is None:
        s = mem.summary
        decision = brain.decide(s)
        action, params = decision["action"], decision.get("params", {})
        if decision.get("fallback"):
            mem.log("brain_fallback", note=decision["fallback"])

        ok, reason = precheck(action, params, s)
        if ok:
            spin.accepted()
        mem.log("decision", week=world.week + 1, action=action, params=params,
                why=decision.get("why", ""), accepted=ok, reject_reason=reason)

        share_suffix = f" {s['share']:.0%}" if s['share'] else ''
        line = f"W{world.week+1:02d} [{s['mode']}{share_suffix}] brain→{action}"
        if not ok:
            say(f"{line}  ✗ verifier: {reason}")
            mem.note_rejection(action, reason)
            if spin.rejected(action, reason):
                say(f"     spin detected (same rejection twice) → escalate_human")
                action, params, ok = "escalate_human", {"reason": f"stuck on {action}: {reason}"}, True
            else:
                action, decision, ok = "wait", {"why": "fallback after rejection"}, True
                say(f"     → falling back to wait, re-deciding next week")
                line = ""

        # ------------------------------------------------------------- ACT
        mode_changed = share_changed = False
        if action == "instrument":
            world.instrumented = True
            mem.summary["instrumented"] = True
            say(f"{line if ok else ''}  ✓ telemetry + label pipeline live")
        elif action == "start_shadow":
            world.set_mode("shadow")
            mode_changed = True
            say(f"{line}  ✓ shadow + 5% budgeted exploration")
        elif action == "ramp":
            world.set_mode("live", share=params["share"])
            mode_changed, share_changed = s["mode"] != "live", True
            say(f"{line}({params['share']:.0%})  ✓ {decision.get('why','')}")
        elif action == "freeze":
            world.set_mode("frozen", share=0.0)
            mode_changed = True
            say(f"{line}  ✓ engine frozen, serving = rules")
        elif action == "escalate_human":
            mem.summary["open_escalation"] = params.get("reason", "review requested")
            pending_review = (world.week, {"share": 0.10,
                                           "note": "resume at 10% once fraud normalizes (simulated review)"})
            mem.log("escalation", reason=mem.summary["open_escalation"])
            say(f"     ⇪ escalated to human: {mem.summary['open_escalation']}")
        elif action == "resume":
            world.set_mode("live", share=params.get("share", 0.10))
            mode_changed, share_changed = True, True
            mem.summary["open_escalation"], mem.summary["inbox"] = None, []
            pending_review = None
            say(f"{line}({params.get('share', 0.10):.0%})  ✓ resumed per human approval")
        elif action == "final_report":
            outcome = _final(world, mem, say)
            break
        elif action == "wait" and line:
            say(f"{line}  → wait ({decision.get('why','gathering data')})")

        # --------------------------------------------------------- OBSERVE
        report = world.step()
        mem.absorb_report(report, world, mode_changed, share_changed)
        if report["engine_n"]:
            say(f"     week ran: engine {report['engine_rec_rate']:.1%} vs rules "
                f"{report['rules_rec_rate']:.1%} | fraud {report['fraud_bps']:.0f} bps "
                f"(n={report['fraud_n']}) | gates: {len(report['gate_contexts'])}")

        # safety override - fires regardless of the brain
        forced = post_override(report, mem.summary)
        if forced:
            world.set_mode("frozen", share=0.0)
            mem.summary["mode"], mem.summary["share"] = "frozen", 0.0
            mem.summary["open_escalation"] = forced[1]
            mem.summary["incidents"].append({"week": report["week"], "what": forced[1]})
            pending_review = (world.week, {"share": 0.10,
                                           "note": "resume at 10% once fraud normalizes (simulated review)"})
            mem.log("safety_override", reason=forced[1])
            say(f"     ⚠ SAFETY OVERRIDE: {forced[1]} → frozen + escalated (brain not consulted)")

        # simulated human review arrives
        if pending_review and world.week - pending_review[0] >= REVIEW_LATENCY \
                and not mem.summary["inbox"]:
            mem.summary["inbox"] = [pending_review[1]]
            mem.log("human_approval", **pending_review[1])
            say(f"     ✉ human approval in inbox: {pending_review[1]['note']}")

        # escalation SLA: do not wait forever
        if mem.summary["open_escalation"] and pending_review \
                and world.week - pending_review[0] > REVIEW_LATENCY + 3:
            say("    HANDOFF: escalation unanswered past SLA - stopping, "
                "journal attached")
            outcome = _final(world, mem, say,
                             handoff="escalation unanswered past SLA")

    if outcome is None:
        outcome = _final(world, mem, say, budget_exhausted=True)
    mem.close()
    return outcome


def _final(world, mem, say, budget_exhausted=False, handoff=None):
    s = mem.summary
    cum = world.cumulative_live(exclude_weeks=[i["week"] for i in s["incidents"]])
    _, en = cum["engine"]
    verdict = ("SHIP for gated contexts, continue ramp under guardrails"
               if (cum["lift_pts"] or 0) > 0 and s["gate_contexts"]
               else "SHIP THE TABLE - engine did not buy its way in")
    result = AgentRunResult(
        verdict=verdict, weeks=world.week, budget_exhausted=budget_exhausted,
        lift_pts=cum["lift_pts"], engine=cum["engine"], rules=cum["rules"],
        gate_contexts=list(s["gate_contexts"]), incidents=list(s["incidents"]),
        events=mem.events, history=world.history,
        journal_path=mem.journal_path, handoff=handoff,
    )
    with open(result.report_path, "w") as f:
        f.write(render_markdown(result))
    lift = f"{cum['lift_pts']:+.1f} pts" if cum["lift_pts"] is not None else "n/a"
    say(f"\n[FINAL] {verdict}")
    say(f"    evidence ex-incident: lift {lift} on n={en} | "
        f"gates: {len(s['gate_contexts'])} | incidents: {len(s['incidents'])}")
    say(f"    full report: {result.report_path}")
    return result
