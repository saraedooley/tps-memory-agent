# TestForge — a dual-memory TPS authoring agent on Databricks

A small, deployable demo showing how to build an AI agent with **short-term and
long-term memory end-to-end on Databricks** — the Lakehouse (Delta + Unity
Catalog), **Lakebase** (serverless Postgres + pgvector) for memory, **Databricks
Apps** for the UI, the **Foundation Models API** for the model, and **MLflow**
for tracing and evaluation.

The scenario is from manufacturing: test engineers author **Test Program
Specifications (TPS)** — the parameters, limits, guard-bands, equipment, and test
sequences for a new product. Today that judgment lives as **institutional
knowledge** in people's heads and scattered spreadsheets; when someone moves on,
the next engineer re-derives it from scratch. TestForge helps draft specs, and
it *accumulates* the team's testing know-how so the org keeps it.

> The same patterns power the Databricks enablement labs (an Airbnb / Bakehouse
> assistant); here they are re-skinned to manufacturing and extended with a
> **dual-namespace** long-term memory design for cross-engineer collaboration.

---

## Why memory, and why on one platform

| Failure mode | What fixes it |
|---|---|
| The agent loses track mid-draft | **Short-term memory** — LangGraph `AsyncCheckpointSaver` writes full session state to Lakebase, keyed by `thread_id`. |
| Decisions and preferences vanish between sessions and engineers | **Long-term memory** — `AsyncDatabricksStore` (pgvector) stores curated facts, semantically recalled across sessions and across the team. |

The point of doing this on Databricks is that **one governance plane** (Unity
Catalog) covers the data the agent reasons over, the tools it calls, the model it
runs on, *and* its memory — and the operational memory store (Lakebase) sits next
to the analytical lakehouse instead of being a separate, opaque service you stitch
in. Concretely, instead of gluing together a standalone vector database + a
separate transactional Postgres + a warehouse + a model gateway + app hosting + an
eval tool (each with its own security model and its own copies of your data), you
get:

- **Memory as a governed, queryable asset.** The long-term store is a real
  Postgres table under Unity Catalog. You can `SELECT` it, audit who-decided-what,
  and run analytics on accumulated decisions (see `scripts/inspect_lakebase.py`).
- **No data movement.** The agent grounds answers in governed Delta tables via UC
  Function tools — no copies leave the boundary.
- **Serverless economics.** Lakebase Autoscaling scales to zero when idle.
- **One lineage graph.** Data → tools → model → memory, traced in MLflow.

---

## Architecture

```
                ┌───────────────────────── Unity Catalog (one governance plane) ─────────────────────────┐
  Browser  ──►  Databricks App (FastAPI + chat.html)                                                       │
 (engineers)        │                                                                                      │
                    ▼                                                                                       │
              LangGraph agent (agent.py)                                                                    │
                    │  model: Foundation Models API (ChatDatabricks)                                        │
                    ├── UC Function tools  ──►  Delta tables (test limits, yield, equipment)  ◄─ governed ──┤
                    ├── short-term memory  ──►  Lakebase: checkpoint* tables                                │
                    └── long-term memory   ──►  Lakebase: store / store_vectors (pgvector)                  │
                    │                                                                                       │
              MLflow tracing (every run, tool call, recall)                                                 │
                └───────────────────────────────────────────────────────────────────────────────────────┘
```

### Long-term memory: dual namespace (the collaboration angle)

| Tool | Namespace | What it stores | Who recalls it |
|---|---|---|---|
| `save_team_memory` | `("project", project_id)` | shared decisions + rationale (limits, equipment standards, yield-excursion lessons) | every engineer on the project |
| `save_personal_memory` | `("user", user_id)` | one engineer's authoring preferences (guard-band style, default blocks) | that engineer only |
| `recall_memory` | both | — (reads) | merged + tagged `[team]` / `[personal]` |

Use structured keys like `decision::PMIC-Buck-A::iddq_usl` so concurrent
teammates' saves don't clobber each other (the `store` primary key is `(prefix, key)`).

---

## Repo layout

```
agent.py                 dual-memory LangGraph agent (short + long term, UC tools, MLflow)
server.py                FastAPI: GET / , POST /invocations , GET /memory , GET /healthz
chat.html                chat UI with Engineer + Project selectors (switch identity live)
config/agent_config.yaml local-dev config (mlflow ModelConfig)
sql/00_schema.sql        catalog / schema / volume
sql/tools/*.sql          three UC Function tools (descriptions are load-bearing)
setup/01_generate_data.py   synthetic test/yield/equipment data + SOP docs
setup/02_create_uc_tools.py create + smoke-test the UC functions
setup/03_provision_lakebase.sh  create the Lakebase Autoscaling project
eval/eval_dataset.jsonl  recall + grounding eval cases
eval/run_eval.py         mlflow.genai.evaluate harness
scripts/verify_memory.py reproduce the demo moments end-to-end
scripts/inspect_lakebase.py raw SQL over store / store_vectors / checkpoint
app.yaml , databricks.yml deployment manifests
```

---

## Quickstart

> Target workspace: `https://fevm-digital-twin-generic.cloud.databricks.com` (org `7474657725221208`).
> Set up a CLI profile first: `databricks auth login --host https://fevm-digital-twin-generic.cloud.databricks.com -p fevm-digital-twin`.

```bash
export PROFILE=fevm-digital-twin
export DATABRICKS_CONFIG_PROFILE=$PROFILE
export CATALOG=tps_demo

# 1. Provision the Lakebase Autoscaling project (memory backend)
PROFILE=$PROFILE PROJECT=tps-memory-agent ./setup/03_provision_lakebase.sh

# 2. Generate governed synthetic data + SOP docs
python setup/01_generate_data.py --catalog $CATALOG

# 3. Create + smoke-test the UC Function tools
python setup/02_create_uc_tools.py --catalog $CATALOG

# 4. Fill in config/agent_config.yaml (CATALOG_NAME, LAKEBASE_AUTOSCALING_PROJECT)
#    then verify all memory layers locally:
python scripts/verify_memory.py

# 5. Deploy as a Databricks App (edit app.yaml placeholders first)
databricks bundle deploy -t dev -p $PROFILE
#    then grant the app's service principal a Lakebase role
#    (Compute > Lakebase > tps-memory-agent > Roles and Databases > Add Role)

# 6. Evaluate
python eval/run_eval.py

# 7. Inspect memory as a governed asset
LAKEBASE_HOST=<endpoint-host> LAKEBASE_USER=<you@databricks.com> \
  python scripts/inspect_lakebase.py
```

---

## The demo moments (reproducible)

| # | Moment | Capability it proves |
|---|---|---|
| 1 | Multi-turn drafting in one session | short-term memory (checkpointer) |
| 2 | New session, same engineer recalls their preference | long-term semantic recall |
| 3 | **Engineer B inherits Engineer A's project decision** | **shared, governed institutional memory** |
| 4 | Unknown engineer/project gets nothing back | memory is scoped, not leaked |
| 5 | Limit recommendation cites historical Cpk / low-yield block | lakehouse grounding via UC tools |
| 6 | `GET /memory` + raw `SELECT` over `store` | **memory as a governed, queryable asset** |
| 7 | MLflow trace shows when `recall_memory` fired | on-platform observability |

Moments 1–5 are scripted in `scripts/verify_memory.py`; 6 in `scripts/inspect_lakebase.py`
and the `/memory` route; 7 in the MLflow experiment.

---

## Two authoring paths: Foundation Models API vs Agent Bricks

This repo is the **code-first** path (full control of the graph and the
dual-namespace memory). For grounded Q&A with far less code, **Agent Bricks** can
stand up a Knowledge Assistant over the *same* governed assets — the SOP docs in
`/Volumes/<catalog>/tps/sop_docs` plus a Genie/SQL path over the same tables.

| Dimension | Foundation Models API + LangGraph (this repo) | Agent Bricks (low-code) |
|---|---|---|
| Memory | Full control: dual-namespace short + long term on Lakebase | Built-in conversation memory; no custom cross-user namespace |
| Tooling | Arbitrary UC functions + custom Python tools | Knowledge sources + Genie/UC, declarative |
| Setup | Code + deploy as a Databricks App | Mostly UI/SDK config |
| Observability | MLflow traces you instrument | Managed |
| Best for | Persistent, cross-user institutional memory as the product | Fast, governed grounded answers |

The substrate underneath — Unity Catalog governance, Lakebase, the model
endpoint, and MLflow — is identical. You're choosing an authoring surface, not a
stack. (Agent Bricks does **not** read this repo's `store` tables; its memory is
its own managed conversation memory.)

---

## Notes & caveats

- `databricks-langchain[memory]` — the `[memory]` extra is **required** for
  `AsyncDatabricksStore` / `AsyncCheckpointSaver`.
- `EMBEDDING_DIMS` must match the embedding endpoint (1024 for `databricks-gte-large-en`).
- Concurrent writes to the same team key are last-write-wins on `(prefix, key)` —
  use structured keys to avoid collisions.
- The lab-only Lakebase role `databricks_superuser` is a shortcut; in production
  grant a custom role scoped to the checkpoint + store tables.

Generated for a Databricks blog on agent memory. No competitor is named anywhere;
the argument is made on platform capabilities.
