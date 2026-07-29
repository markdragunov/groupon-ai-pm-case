#!/usr/bin/env python3
"""AI Recovery Engine v2 - the rollout as an AGENTIC LOOP.

    python3 run_v2_agent.py                 # heuristic brain (default, no deps)
    python3 run_v2_agent.py --brain claude  # LLM decide-step (needs ANTHROPIC_API_KEY)

v0 executed a hardcoded six-week script. v2 removes the script: an agent
observes the world weekly, decides the next move from a bounded action space,
a verifier gates every move, safety overrides fire regardless of the brain,
memory stays compacted, and the run terminates on goal / budget / escalation.

The unit of work is no longer a phase plan. It is a loop.
"""

import sys

from agent.loop import run

if __name__ == "__main__":
    import os
    for _d in ['logs', 'reports']:
        os.makedirs(_d, exist_ok=True)
    brain = "claude" if "--brain" in sys.argv and "claude" in sys.argv else "heuristic"
    print("=" * 76)
    print("v2 · AGENTIC ROLLOUT LOOP  (decide > verify > act > observe > remember)")
    print("=" * 76)
    run(brain_kind=brain)
    print("=" * 76)
