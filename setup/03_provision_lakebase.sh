#!/usr/bin/env bash
# Provision the Lakebase Autoscaling project that backs the agent's memory.
#
# Creates a project (with a default `production` branch + primary read-write
# endpoint). The same instance holds BOTH memory layers:
#   - short-term: checkpoint* tables  (AsyncCheckpointSaver)
#   - long-term:  store / store_vectors tables (AsyncDatabricksStore + pgvector)
# These tables are created lazily by LangGraph on first agent run / store.setup().
#
# Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
#
# Usage:
#   PROFILE=fevm-digital-twin PROJECT=tps-memory-agent ./setup/03_provision_lakebase.sh
#
# Lakebase project names may not contain underscores — use hyphens.
set -euo pipefail

PROFILE="${PROFILE:-fevm-digital-twin}"
PROJECT="${PROJECT:-tps-memory-agent}"
BRANCH="${BRANCH:-production}"

echo "Profile : ${PROFILE}"
echo "Project : ${PROJECT}"
echo "Branch  : ${BRANCH}"
echo

echo "==> Creating Lakebase Autoscaling project '${PROJECT}' ..."
databricks postgres create-project "${PROJECT}" \
  --json "{\"spec\": {\"display_name\": \"TestForge TPS memory agent\"}}" \
  --no-wait -p "${PROFILE}" || echo "(project may already exist — continuing)"

echo
echo "==> Waiting briefly for provisioning, then listing endpoints ..."
sleep 8
databricks postgres list-endpoints "projects/${PROJECT}/branches/${BRANCH}" -p "${PROFILE}" || true

cat <<EOF

✅ Lakebase project requested.

Next steps:
  1. Confirm the project is Available:  Compute > Lakebase > Autoscaling.
  2. Put these into config/agent_config.yaml and app.yaml:
        LAKEBASE_AUTOSCALING_PROJECT: ${PROJECT}
        LAKEBASE_AUTOSCALING_BRANCH:  ${BRANCH}
  3. After deploying the app, grant its service principal a Lakebase role
     (Compute > Lakebase > <instance> > Roles and Databases > Add Role).
     For a quick demo use 'databricks_superuser'; for production use a custom
     role scoped to the checkpoint + store tables only.
EOF
