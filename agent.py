"""TestForge — a collaborative Test Program Specification (TPS) authoring agent
with both short-term and long-term memory, backed entirely by Databricks.

Memory architecture
-------------------
- Short-term  : AsyncCheckpointSaver -> Lakebase `checkpoint*` tables, keyed by
                thread_id. Holds the full conversational state of ONE editing
                session so a spec draft stays coherent across turns.
- Long-term   : AsyncDatabricksStore (pgvector) -> Lakebase `store` /
                `store_vectors` tables. Semantically recalled facts that survive
                across sessions AND across engineers. Two namespaces:
                  ("project", project_id) -> shared team decisions/rationale
                  ("user",    user_id)    -> a single engineer's preferences
                This dual namespace is what turns the agent into an
                institutional-knowledge accumulator for a project team.

Grounding
---------
UC Function tools (recommend_test_limits, yield_risk_by_block,
lookup_equipment_for_test) ground every limit/equipment recommendation in
governed lakehouse data via Unity Catalog.

Model layer
-----------
Foundation Models API via ChatDatabricks. (Agent Bricks is shown as a low-code
alternative in the README; this file is the full-control LangGraph path.)

Config is read from environment variables when deployed on Databricks Apps, and
falls back to config/agent_config.yaml for local development.

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Annotated, Any, Optional, Sequence, TypedDict

import mlflow
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    AsyncCheckpointSaver,
    AsyncDatabricksStore,
    ChatDatabricks,
    UCFunctionToolkit,
)
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import InjectedStore
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.store.base import BaseStore

logger = logging.getLogger("tps_agent")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


# --------------------------------------------------------------------------- #
# Configuration: env vars (deployed) with local YAML fallback.
# --------------------------------------------------------------------------- #
def _load_config() -> dict[str, Any]:
    """Read config from env, falling back to config/agent_config.yaml locally."""
    cfg: dict[str, Any] = {}
    try:
        from mlflow.models import ModelConfig

        local = ModelConfig(development_config="config/agent_config.yaml").to_dict()
    except Exception:
        local = {}

    def pick(*keys: str, default: Optional[str] = None) -> Optional[str]:
        for k in keys:
            if os.getenv(k):
                return os.getenv(k)
        for k in keys:
            if local.get(k) not in (None, ""):
                return str(local[k])
        return default

    cfg["LLM_ENDPOINT_NAME"] = pick("SERVING_ENDPOINT_NAME", "LLM_ENDPOINT_NAME",
                                    default="databricks-claude-sonnet-4-6")
    cfg["SYSTEM_PROMPT"] = pick("SYSTEM_PROMPT", default="You are a helpful assistant.")
    cfg["CATALOG_NAME"] = pick("CATALOG_NAME")
    cfg["SCHEMA_NAME"] = pick("SCHEMA_NAME", default="tps")
    cfg["TOOLS"] = [
        t for t in [
            pick("FUNCTION_1_NAME", "TOOL1"),
            pick("FUNCTION_2_NAME", "TOOL2"),
            pick("FUNCTION_3_NAME", "TOOL3"),
        ] if t
    ]
    cfg["LAKEBASE_INSTANCE_NAME"] = pick("LAKEBASE_INSTANCE_NAME")
    cfg["LAKEBASE_AUTOSCALING_PROJECT"] = pick("LAKEBASE_AUTOSCALING_PROJECT")
    cfg["LAKEBASE_AUTOSCALING_BRANCH"] = pick("LAKEBASE_AUTOSCALING_BRANCH", default="production")
    cfg["EMBEDDING_ENDPOINT"] = pick("EMBEDDING_ENDPOINT", default="databricks-gte-large-en")
    cfg["EMBEDDING_DIMS"] = int(pick("EMBEDDING_DIMS", default="1024"))
    cfg["MLFLOW_EXPERIMENT_ID"] = pick("MLFLOW_EXPERIMENT_ID")
    return cfg


CONFIG = _load_config()

# --------------------------------------------------------------------------- #
# MLflow tracing (one experiment, one lineage graph with the rest of the stack).
# --------------------------------------------------------------------------- #
try:
    mlflow.set_tracking_uri("databricks")
    mlflow.langchain.autolog()
    if CONFIG["MLFLOW_EXPERIMENT_ID"]:
        mlflow.set_experiment(experiment_id=CONFIG["MLFLOW_EXPERIMENT_ID"])
except Exception as exc:  # never block the app on tracing setup
    logger.warning("MLflow setup skipped: %s", exc)


# --------------------------------------------------------------------------- #
# Lakebase connection kwargs (shared by checkpointer + store).
# --------------------------------------------------------------------------- #
def _get_lakebase_kwargs() -> dict[str, Any]:
    if CONFIG["LAKEBASE_INSTANCE_NAME"]:
        return {"instance_name": CONFIG["LAKEBASE_INSTANCE_NAME"]}
    if CONFIG["LAKEBASE_AUTOSCALING_PROJECT"]:
        return {
            "project": CONFIG["LAKEBASE_AUTOSCALING_PROJECT"],
            "branch": CONFIG["LAKEBASE_AUTOSCALING_BRANCH"],
        }
    raise ValueError(
        "Lakebase not configured. Set LAKEBASE_INSTANCE_NAME, or "
        "LAKEBASE_AUTOSCALING_PROJECT + LAKEBASE_AUTOSCALING_BRANCH."
    )


def _get_store_kwargs() -> dict[str, Any]:
    """Store needs the embedding endpoint for semantic recall (pgvector)."""
    return {
        **_get_lakebase_kwargs(),
        "embedding_endpoint": CONFIG["EMBEDDING_ENDPOINT"],
        "embedding_dims": CONFIG["EMBEDDING_DIMS"],
        "workspace_client": WorkspaceClient(),
    }


# --------------------------------------------------------------------------- #
# Long-term memory tools — dual namespace (team + personal).
#
# The store is injected by LangGraph (store=store at compile time) into any tool
# annotated with InjectedStore. user_id and project_id arrive on the runtime
# config and scope the namespaces.
# --------------------------------------------------------------------------- #
def _ns_team(config: RunnableConfig) -> tuple[str, str]:
    return ("project", config["configurable"].get("project_id", "default"))


def _ns_personal(config: RunnableConfig) -> tuple[str, str]:
    return ("user", config["configurable"].get("user_id", "anonymous"))


@tool
async def save_team_memory(
    key: str,
    value: str,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Save a SHARED project decision or rationale that every engineer on this
    project should inherit (e.g. a chosen limit and why). Use a structured key
    like 'decision::<spec-or-family>::<topic>' so teammates' saves don't clobber
    each other.

    Args:
        key:   Structured label, e.g. 'decision::PMIC-Buck-A::iddq_usl'.
        value: The decision and its rationale, e.g. 'IDDQ USL = 50 uA after Q2 field returns'.
    """
    await store.aput(_ns_team(config), key, {"content": value})
    return f"✅ Saved TEAM memory '{key}'."


@tool
async def save_personal_memory(
    key: str,
    value: str,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Save the CURRENT engineer's personal authoring preference (only recalled
    for this engineer), e.g. guard-band style or default test blocks.

    Args:
        key:   A short label, e.g. 'guardband_preference', 'default_blocks'.
        value: The preference, e.g. 'prefers 10% tighter guard-bands'.
    """
    await store.aput(_ns_personal(config), key, {"content": value})
    return f"✅ Saved PERSONAL memory '{key}'."


@tool
async def recall_memory(
    query: str,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """Recall relevant facts from long-term memory. Searches BOTH the shared
    project (team) memory and this engineer's personal memory, and labels each
    hit with its provenance. Call this at the start of every task.

    Args:
        query: Natural-language description of what you need, e.g.
               'IDDQ limit decisions for PMIC-Buck-A and my guard-band preference'.
    """
    team = await store.asearch(_ns_team(config), query=query, limit=5)
    personal = await store.asearch(_ns_personal(config), query=query, limit=5)

    lines: list[str] = []
    for item in team:
        lines.append(f"  [team] {item.key}: {item.value['content']}")
    for item in personal:
        lines.append(f"  [personal] {item.key}: {item.value['content']}")

    if not lines:
        return "No memories found yet for this project or engineer."
    return "Recalled memories:\n" + "\n".join(lines)


MEMORY_TOOLS = [save_team_memory, save_personal_memory, recall_memory]


# --------------------------------------------------------------------------- #
# UC Function tools (grounding in governed lakehouse data).
# --------------------------------------------------------------------------- #
def _load_uc_tools() -> list[Any]:
    catalog, schema, fns = CONFIG["CATALOG_NAME"], CONFIG["SCHEMA_NAME"], CONFIG["TOOLS"]
    if not (catalog and fns):
        logger.warning("No UC tools configured (CATALOG_NAME / TOOLn). Running memory-only.")
        return []
    names = [f"{catalog}.{schema}.{fn}" for fn in fns]
    try:
        return UCFunctionToolkit(function_names=names).tools
    except Exception as exc:
        logger.warning("UC tool load failed (%s). Running memory-only.", exc)
        return []


UC_TOOLS = _load_uc_tools()


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
class AgentState(TypedDict):
    messages: Annotated[Sequence[AnyMessage], add_messages]


def _build_graph(checkpointer, store, model_with_tools, tools):
    def call_model(state: AgentState, config: RunnableConfig):
        messages = [SystemMessage(content=CONFIG["SYSTEM_PROMPT"])] + list(state["messages"])
        return {"messages": [model_with_tools.invoke(messages, config)]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.set_entry_point("agent")
    if tools:
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_conditional_edges("agent", should_continue)
        workflow.add_edge("tools", "agent")
    else:
        workflow.add_edge("agent", END)
    # store=store activates long-term memory (InjectedStore); checkpointer is short-term.
    return workflow.compile(checkpointer=checkpointer, store=store)


async def _run_async(lc_messages: list[dict], config: RunnableConfig):
    all_tools = MEMORY_TOOLS + UC_TOOLS
    model = ChatDatabricks(endpoint=CONFIG["LLM_ENDPOINT_NAME"])
    model_with_tools = model.bind_tools(all_tools)

    # Both memory layers opened per-invocation as nested async context managers,
    # so the Lakebase connection pools are cleanly closed even on error.
    async with AsyncDatabricksStore(**_get_store_kwargs()) as store:
        await store.setup()  # idempotent: creates store / store_vectors if absent
        async with AsyncCheckpointSaver(**_get_lakebase_kwargs()) as checkpointer:
            graph = _build_graph(checkpointer, store, model_with_tools, all_tools)
            result = await graph.ainvoke({"messages": lc_messages}, config)
    return result["messages"][-1].content


@mlflow.trace(
    name="tps_memory_agent_run",
    span_type="AGENT",
    attributes={"agent_name": "TestForge TPS Authoring Agent"},
)
async def run_agent(
    input_messages: list[dict],
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """Public entrypoint called by server.py.

    Args:
        input_messages: full chat history as [{"role","content"}, ...].
        thread_id:  short-term memory scope (one editing session). Auto-UUID if None.
        user_id:    personal long-term memory scope (engineer).
        project_id: shared team long-term memory scope (project).
    """
    thread_id = thread_id or str(uuid.uuid4())

    mlflow.update_current_trace(
        metadata={
            "mlflow.trace.session": thread_id,
            "user_id": user_id or "anonymous",
            "project_id": project_id or "default",
            "component": "tps_dual_memory_agent",
        }
    )

    config: RunnableConfig = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id or "anonymous",
            "project_id": project_id or "default",
        }
    }
    output = await _run_async(input_messages, config)
    return {"output": output, "thread_id": thread_id}
