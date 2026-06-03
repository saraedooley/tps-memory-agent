"""Inspect the agent's memory directly in Lakebase Postgres — the "memory as a
governed, queryable data asset" proof.

Connects to the Lakebase Autoscaling endpoint and runs raw SQL over the tables
LangGraph created:
  - store          (prefix, key, value jsonb)         <- long-term facts
  - store_vectors  (prefix, key, embedding vector)    <- semantic index
  - checkpoint*                                        <- short-term session state

Connection details come from env vars (read them off the Lakebase endpoint page,
Compute > Lakebase > your project > Connection details):
    LAKEBASE_HOST, LAKEBASE_PORT (5432), LAKEBASE_DATABASE (databricks_postgres),
    LAKEBASE_USER (your email or the app SP)
The password is a short-lived OAuth token generated per connection via the SDK.

    DATABRICKS_CONFIG_PROFILE=fevm-digital-twin \
    LAKEBASE_HOST=... LAKEBASE_USER=you@databricks.com \
    python scripts/inspect_lakebase.py

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import os

import psycopg
from databricks.sdk import WorkspaceClient

HOST = os.environ.get("LAKEBASE_HOST", "")
PORT = os.environ.get("LAKEBASE_PORT", "5432")
DATABASE = os.environ.get("LAKEBASE_DATABASE", "databricks_postgres")
USER = os.environ.get("LAKEBASE_USER", "")
PROJECT = os.environ.get("LAKEBASE_AUTOSCALING_PROJECT", "tps-memory-agent")
BRANCH = os.environ.get("LAKEBASE_AUTOSCALING_BRANCH", "production")


def _token() -> str:
    """Generate a short-lived Lakebase OAuth token for the primary endpoint."""
    w = WorkspaceClient()
    endpoint = f"projects/{PROJECT}/branches/{BRANCH}/endpoints/primary"
    cred = w.postgres.generate_database_credential(endpoint=endpoint)
    return cred.token


def main() -> None:
    if not (HOST and USER):
        raise SystemExit("Set LAKEBASE_HOST and LAKEBASE_USER (see Lakebase connection details).")

    conn = psycopg.connect(
        host=HOST, port=PORT, dbname=DATABASE, user=USER,
        password=_token(), sslmode="require",
    )
    with conn, conn.cursor() as cur:
        print("\n--- Long-term TEAM + PERSONAL memory (store) ---")
        cur.execute(
            "SELECT prefix, key, value->>'content' AS content, updated_at "
            "FROM store ORDER BY updated_at DESC LIMIT 40;"
        )
        for prefix, key, content, ts in cur.fetchall():
            print(f"  [{prefix}] {key} = {content}  ({ts:%Y-%m-%d %H:%M})")

        print("\n--- Semantic index rows (store_vectors) ---")
        cur.execute("SELECT prefix, key, field_name FROM store_vectors LIMIT 20;")
        for prefix, key, field in cur.fetchall():
            print(f"  [{prefix}] {key} :: {field}")

        print("\n--- Short-term sessions (checkpoint rows per thread) ---")
        cur.execute(
            "SELECT thread_id, COUNT(*) AS n FROM checkpoint "
            "GROUP BY thread_id ORDER BY n DESC LIMIT 20;"
        )
        for thread_id, n in cur.fetchall():
            print(f"  thread {thread_id}: {n} checkpoints")

    print("\n✅ Memory is a real, queryable Postgres asset — governed by Unity Catalog,")
    print("   sitting next to the test/yield data the agent reasons over.")


if __name__ == "__main__":
    main()
