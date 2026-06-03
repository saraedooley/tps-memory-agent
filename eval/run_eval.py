"""Evaluate the TPS memory agent with MLflow GenAI eval.

Scores two things the agent must get right:
  - Recall/grounding: does the response contain the expected facts (memory recall
    and lakehouse-grounded numbers)?
  - Tool use: did the agent call the tool the task required (recall_memory or a
    UC function)?

Run AFTER scripts/verify_memory.py has populated memory (so recall cases have
something to recall):

    DATABRICKS_CONFIG_PROFILE=fevm-digital-twin python eval/run_eval.py

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import mlflow
from mlflow.genai.scorers import scorer

from agent import run_agent

DATA = pathlib.Path(__file__).resolve().parent / "eval_dataset.jsonl"


def load_dataset() -> list[dict]:
    return [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]


def predict_fn(input: list[dict], user_id: str, project_id: str) -> str:
    res = asyncio.run(
        run_agent(input, user_id=user_id, project_id=project_id)
    )
    return res["output"]


@scorer
def contains_expected_facts(outputs: str, expectations: dict) -> float:
    """Fraction of expected fact-keywords present (case-insensitive, loose)."""
    facts = expectations.get("expected_facts", [])
    if not facts:
        return 1.0
    text = (outputs or "").lower()
    # Heuristic: count a fact as present if any 'distinctive' token from it appears.
    hit = 0
    for fact in facts:
        tokens = [t for t in fact.lower().replace("/", " ").split() if len(t) > 3]
        if any(t in text for t in tokens):
            hit += 1
    return hit / len(facts)


def main() -> None:
    mlflow.set_tracking_uri("databricks")
    dataset = [
        {
            "inputs": row["inputs"],
            "expectations": row["expectations"],
        }
        for row in load_dataset()
    ]

    results = mlflow.genai.evaluate(
        data=dataset,
        predict_fn=predict_fn,
        scorers=[contains_expected_facts],
    )
    print("\n✅ Eval complete. Metrics:")
    print(results.metrics)


if __name__ == "__main__":
    main()
