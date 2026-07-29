#!/usr/bin/env python3
"""Deterministic smoke checks for seeded demo outputs."""

import json
import os
import subprocess
import sys
import unittest


def run_script(name: str) -> str:
    proc = subprocess.run(
        [sys.executable, name],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout + proc.stderr


class SmokeTest(unittest.TestCase):
    def test_v0_engine_verdict(self):
        out = run_script("run_v0_engine.py")
        self.assertIn("engine earns the next ramp step", out)
        self.assertIn("logs/decision_log.jsonl", out)

    def test_v1_product_ops_readout(self):
        out = run_script("run_v1_product_ops.py")
        self.assertIn("SHIP - ramp to all at-risk cohorts", out)
        self.assertIn("reports/day90_readout.md", out)

    def test_v2_agent_final_report(self):
        out = run_script("run_v2_agent.py")
        self.assertIn("SHIP for gated contexts", out)
        self.assertIn("reports/agent_run.md", out)

    def test_v2_views_agree_with_result(self):
        """Markdown and journal are views over one AgentRunResult, not separate
        truths: both must report what the result object says."""
        from agent.loop import render_markdown, run

        for d in ("logs", "reports"):
            os.makedirs(d, exist_ok=True)
        result = run(quiet=True)

        self.assertIn(result.verdict, render_markdown(result))
        with open(result.report_path) as f:
            self.assertIn(result.verdict, f.read())
        with open(result.journal_path) as f:
            journal = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(journal, result.events)
        self.assertEqual(len(result.history), result.weeks)


if __name__ == "__main__":
    unittest.main()
