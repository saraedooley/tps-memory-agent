"""Reproduce the memory demo moments end-to-end against a provisioned workspace.

Run after data + tools + Lakebase are set up (uses config/agent_config.yaml or env):

    DATABRICKS_CONFIG_PROFILE=fevm-digital-twin python scripts/verify_memory.py

Proves, in order:
  1. Short-term memory   — turn 2 uses turn-1 context within one thread.
  2. Cross-session       — engineer A, NEW thread, recalls their own preference.
  3. Cross-user (team)   — engineer B inherits engineer A's project decision.
  4. Grounding           — a limit recommendation cites historical data (UC tool).

Inspect the MLflow traces afterward to see recall_memory / save_* / UC tool spans.

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import asyncio

from agent import run_agent

PROJECT = "proj-pmic-buck-a"
ENG_A = "amelia.cho"
ENG_B = "ravi.patel"


def msgs(*turns: str) -> list[dict]:
    """Build a chat history; odd turns are user messages for this simple driver."""
    return [{"role": "user", "content": t} for t in turns]


async def turn(history: list[dict], thread_id: str, user_id: str) -> str:
    res = await run_agent(history, thread_id=thread_id, user_id=user_id, project_id=PROJECT)
    return res["output"]


async def main() -> None:
    print("\n=== 1. SHORT-TERM (same thread) ===")
    t1 = "sess-shortterm-1"
    h = [{"role": "user", "content":
          "I'm drafting the TPS for PMIC-Buck-A. Let's start with the IDDQ test block."}]
    r = await turn(h, t1, ENG_A); print("A:", r[:400])
    h += [{"role": "assistant", "content": r},
          {"role": "user", "content": "What block did I just say we'd start with?"}]
    r = await turn(h, t1, ENG_A); print("A (follow-up):", r[:300])

    print("\n=== 2. SAVE a personal preference + a team decision (engineer A) ===")
    t2 = "sess-save-1"
    h = [{"role": "user", "content":
          "Remember two things. Personal preference: I always guard-band IDDQ limits 10% tighter "
          "than the historical USL. Team decision for PMIC-Buck-A: we set the IDDQ USL to 50 uA "
          "after the Q2 field returns — please record the rationale for the whole team."}]
    r = await turn(h, t2, ENG_A); print("A:", r[:400])

    print("\n=== 3. CROSS-SESSION (engineer A, NEW thread) ===")
    t3 = "sess-crosssession-1"
    h = [{"role": "user", "content":
          "New session. Before we continue on PMIC-Buck-A, remind me of my guard-band preference."}]
    r = await turn(h, t3, ENG_A); print("A (new session):", r[:400])

    print("\n=== 4. CROSS-USER / TEAM (engineer B, brand-new) ===")
    t4 = "sess-crossuser-1"
    h = [{"role": "user", "content":
          "I'm new to the PMIC-Buck-A project. What has the team already decided about the IDDQ USL, and why?"}]
    r = await turn(h, t4, ENG_B); print("B:", r[:400])

    print("\n=== 5. GROUNDED RECOMMENDATION (UC tool) ===")
    t5 = "sess-ground-1"
    h = [{"role": "user", "content":
          "Recommend an IDDQ USL for PMIC-Buck-A and tell me which test blocks historically lose the most yield."}]
    r = await turn(h, t5, ENG_A); print("A:", r[:600])

    print("\n✅ Done. Open the MLflow experiment to inspect the traces.")


if __name__ == "__main__":
    asyncio.run(main())
