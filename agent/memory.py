"""Memory - the loop's answer to CONTEXT MANAGEMENT.

Two stores, mirroring how production agents keep context bounded:
  * journal   - append-only JSONL of everything (decisions, rejections,
                reports, escalations). The audit trail; never fed back whole.
  * summary   - a small dict the brain actually reasons over, updated and
                COMPACTED every cycle: current mode, weeks-at-mode, evidence,
                last guardrail reading, open escalations, recent rejections.

The brain never sees raw history - only the summary. That is deliberate: an
agent that re-reads its whole past every turn is a context leak, not a memory.
"""

import json


class Memory:
    def __init__(self, journal_path):
        self.f = open(journal_path, "w")
        self.summary = {
            "week": 0, "mode": "baseline", "share": 0.0,
            "instrumented": False, "weeks_in_mode": 0, "weeks_at_share": 0,
            "gate_contexts": [], "labels_total": 0,
            "last_fraud_bps": 0.0, "last_fraud_n": 0,
            "guardrails_clean": True, "cum_lift_pts": None,
            "open_escalation": None, "inbox": [],
            "recent_rejections": [], "incidents": [],
        }

    def log(self, kind, **kw):
        self.f.write(json.dumps({"kind": kind, **kw}) + "\n")
        self.f.flush()

    def note_rejection(self, action, reason):
        r = self.summary["recent_rejections"]
        r.append({"action": action, "reason": reason})
        del r[:-3]                                   # compaction: keep last 3

    def absorb_report(self, report, world, mode_changed, share_changed):
        s = self.summary
        s["week"] = report["week"]
        s["weeks_in_mode"] = 1 if mode_changed else s["weeks_in_mode"] + 1
        s["weeks_at_share"] = 1 if share_changed else s["weeks_at_share"] + 1
        s["mode"], s["share"] = report["mode"], report["share"]
        s["gate_contexts"] = report["gate_contexts"]
        s["labels_total"] = report["labels_total"]
        s["last_fraud_bps"], s["last_fraud_n"] = report["fraud_bps"], report["fraud_n"]
        s["guardrails_clean"] = not (report["fraud_bps"] >= 16
                                     and report["fraud_n"] >= 300
                                     and report.get("fraud_events", 0) >= 3)
        cum = world.cumulative_live(exclude_weeks=[i["week"] for i in s["incidents"]])
        s["cum_lift_pts"] = round(cum["lift_pts"], 2) if cum["lift_pts"] is not None else None
        self.log("weekly_report", **report)

    def close(self):
        self.f.close()
