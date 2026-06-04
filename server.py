"""FastAPI server for the TestForge TPS memory agent (Databricks Apps entrypoint).

Routes
------
GET  /                 -> serves chat.html (the collaborative chat UI)
POST /invocations      -> runs the dual-memory agent (run_agent in agent.py)
GET  /memory           -> inspects long-term memory for a project/engineer
                          (proves "memory as a governed, queryable asset")
GET  /healthz          -> liveness probe

The agent (agent.py) opens its own Lakebase connections per invocation via async
context managers, so the server stays thin.

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import agent as agent_mod
from agent import CONFIG, run_agent

HERE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="TestForge — TPS Memory Agent")


class ChatRequest(BaseModel):
    input: list[dict[str, Any]]            # [{"role","content"}, ...]
    thread_id: Optional[str] = None        # short-term memory scope (session)
    user_id: Optional[str] = None          # personal long-term memory scope
    project_id: Optional[str] = None       # shared team long-term memory scope


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (HERE / "chat.html").read_text()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invocations")
async def invocations(req: ChatRequest):
    # Always return JSON -- even on failure -- so the chat UI (which calls
    # res.json()) shows a clean error instead of choking on FastAPI's
    # plain-text "Internal Server Error" body ("Unexpected token 'I'...").
    try:
        return await run_agent(
            input_messages=req.input,
            thread_id=req.thread_id,
            user_id=req.user_id,
            project_id=req.project_id,
        )
    except Exception as exc:  # noqa: BLE001 -- surface the reason to the client
        logging.getLogger("tps_server").exception("invocation failed")
        return JSONResponse(
            status_code=500,
            content={"output": None, "thread_id": req.thread_id, "error": str(exc)},
        )


@app.get("/memory")
async def memory(project_id: str = "default", user_id: str = "anonymous", query: str = "") -> JSONResponse:
    """Dump long-term memory for a project (team) and engineer (personal).

    Demonstrates that the agent's accumulated institutional knowledge is a real,
    inspectable asset. (For the raw-SQL view over the Postgres `store` /
    `store_vectors` tables, see scripts/inspect_lakebase.py.)
    """
    from databricks_langchain import AsyncDatabricksStore

    q = query or "project decisions, limits, equipment standards, preferences"
    # Normalize ids to the same namespace labels the agent writes under
    # (store labels can't contain '.'), so inspection matches stored data.
    team_ns = ("project", agent_mod._safe_label(project_id))
    user_ns = ("user", agent_mod._safe_label(user_id))
    out: dict[str, list[dict[str, str]]] = {"team": [], "personal": []}
    async with AsyncDatabricksStore(**agent_mod._get_store_kwargs()) as store:
        await store.setup()
        for item in await store.asearch(team_ns, query=q, limit=50):
            out["team"].append({"key": item.key, "value": item.value.get("content", "")})
        for item in await store.asearch(user_ns, query=q, limit=50):
            out["personal"].append({"key": item.key, "value": item.value.get("content", "")})
    return JSONResponse(out)


def main() -> None:
    import uvicorn

    # Databricks Apps injects the port via DATABRICKS_APP_PORT; default to 8000 locally.
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", "8000")))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
