"""Run a .sql file against a Databricks SQL warehouse, statement by statement.

Pure stdlib (urllib + subprocess) — no pip installs needed. Splits the file on
lines containing only `-- @@`, substitutes ${catalog}, and executes each
statement via the SQL Statement Execution API, polling to completion. Uses the
Databricks CLI for the access token + host so it honors your CLI profile.

    python setup/run_sql.py --file setup/01_generate_data.sql \
        --catalog tps_demo --warehouse 997f7006caea2454 --profile fevm-digital-twin

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request


def _cli_json(args: list[str]) -> dict:
    out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _token_and_host(profile: str) -> tuple[str, str]:
    tok = _cli_json(["databricks", "auth", "token", "-p", profile])["access_token"]
    # host from the profile's config
    env = subprocess.run(
        ["databricks", "auth", "env", "--profile", profile],
        capture_output=True, text=True,
    )
    host = ""
    if env.returncode == 0:
        try:
            host = json.loads(env.stdout).get("env", {}).get("DATABRICKS_HOST", "")
        except Exception:
            host = ""
    if not host:
        # fall back: read ~/.databrickscfg
        import configparser, os
        cfg = configparser.ConfigParser()
        cfg.read(os.path.expanduser("~/.databrickscfg"))
        host = cfg[profile]["host"]
    return tok, host.rstrip("/")


def _api(host: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{host}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def run_statement(host: str, token: str, warehouse: str, stmt: str) -> None:
    resp = _api(host, token, "POST", "/api/2.0/sql/statements", {
        "warehouse_id": warehouse, "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE", "statement": stmt,
    })
    sid = resp["statement_id"]
    state = resp["status"]["state"]
    while state in ("PENDING", "RUNNING"):
        time.sleep(2)
        resp = _api(host, token, "GET", f"/api/2.0/sql/statements/{sid}")
        state = resp["status"]["state"]
    if state != "SUCCEEDED":
        err = resp["status"].get("error", {})
        raise SystemExit(f"FAILED ({state}): {err.get('message','')}\n--- statement ---\n{stmt[:400]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--warehouse", required=True)
    ap.add_argument("--profile", required=True)
    args = ap.parse_args()

    token, host = _token_and_host(args.profile)
    raw = open(args.file).read().replace("${catalog}", args.catalog)
    statements = [s.strip() for s in raw.split("\n-- @@\n") if s.strip() and not s.strip().startswith("--\n")]
    # drop pure-comment leading block / comment-only chunks
    statements = [s for s in statements if any(not ln.strip().startswith("--") and ln.strip() for ln in s.splitlines())]

    print(f"Running {len(statements)} statements against {host} (catalog={args.catalog})")
    for i, stmt in enumerate(statements, 1):
        first = next((ln for ln in stmt.splitlines() if not ln.strip().startswith("--")), "")
        print(f"  [{i}/{len(statements)}] {first[:70]} ...")
        run_statement(host, token, args.warehouse, stmt)
    print("✅ All statements succeeded.")


if __name__ == "__main__":
    main()
