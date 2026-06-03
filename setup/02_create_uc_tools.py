"""Create the three UC Function tools from sql/tools/*.sql and smoke-test them.

    DATABRICKS_CONFIG_PROFILE=fevm-digital-twin python setup/02_create_uc_tools.py --catalog tps_demo

Each .sql file uses a ${catalog} placeholder; we substitute the real catalog,
execute the DDL, then confirm the functions load as LangChain tools via
UCFunctionToolkit (the same path agent.py uses).

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import argparse
import pathlib

SQL_DIR = pathlib.Path(__file__).resolve().parent.parent / "sql" / "tools"
FUNCTIONS = ["recommend_test_limits", "yield_risk_by_block", "lookup_equipment_for_test"]


def get_spark():
    try:
        return spark  # type: ignore[name-defined]
    except NameError:
        from databricks.connect import DatabricksSession

        return DatabricksSession.builder.serverless().getOrCreate()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", default="tps")
    args = ap.parse_args()

    spark_session = get_spark()

    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        ddl = sql_file.read_text().replace("${catalog}", args.catalog)
        # A file may contain a single CREATE FUNCTION statement.
        spark_session.sql(ddl)
        print(f"  created function from {sql_file.name}")

    # Smoke-test: confirm the toolkit can load them (this is what the agent does).
    from databricks_langchain import UCFunctionToolkit

    names = [f"{args.catalog}.{args.schema}.{fn}" for fn in FUNCTIONS]
    toolkit = UCFunctionToolkit(function_names=names)
    print("\n✅ UC tools loaded as LangChain tools:")
    for t in toolkit.tools:
        print(f"   • {t.name}")


if __name__ == "__main__":
    main()
