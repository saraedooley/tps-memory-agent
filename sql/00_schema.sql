-- Catalog / schema / volume for the TPS demo.
-- Run once before generating data. Edit ${catalog} to your target catalog
-- (the agent config and app.yaml use the same value as CATALOG_NAME).
--
-- Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)

CREATE CATALOG IF NOT EXISTS ${catalog}
  COMMENT 'TestForge demo: collaborative Test Program Specification authoring agent.';

CREATE SCHEMA IF NOT EXISTS ${catalog}.tps
  COMMENT 'Manufacturing test/yield data + UC Function tools for the TPS memory agent.';

-- Volume holds the authoring SOP markdown docs used by the Agent Bricks
-- Knowledge Assistant comparison lane (setup/01_generate_data.py writes them here).
CREATE VOLUME IF NOT EXISTS ${catalog}.tps.sop_docs
  COMMENT 'Standard operating procedure docs for TPS authoring (Agent Bricks KA source).';
