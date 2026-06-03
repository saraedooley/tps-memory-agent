-- UC Function tool #1: ground a limit recommendation in historical spec limits.
-- The per-function and per-argument COMMENTs are load-bearing: UCFunctionToolkit
-- surfaces them to the LLM as the tool/argument descriptions, so the model knows
-- when and how to call this tool. Keep them descriptive.

CREATE OR REPLACE FUNCTION ${catalog}.tps.recommend_test_limits(
  product_family STRING COMMENT 'Product family name, e.g. "PMIC-Buck-A", "MCU-Cortex-M4", "RF-Frontend-X".',
  parameter_name STRING COMMENT 'Test parameter to look up, e.g. "Iddq_quiescent_uA", "Vout_accuracy_pct", "Fmax_MHz".'
)
RETURNS TABLE (
  parameter_name STRING,
  unit           STRING,
  lsl            DOUBLE,
  usl            DOUBLE,
  typical_value  DOUBLE,
  cpk            DOUBLE,
  revision       STRING,
  effective_date DATE,
  authored_by    STRING
)
READS SQL DATA
COMMENT 'Returns the historical lower/upper spec limits (LSL/USL), typical value, process capability (Cpk), revision, and author for a given product family and test parameter, most recent revision first. Use this to ground any test-limit or guard-band recommendation in real prior decisions.'
RETURN
  SELECT
    l.parameter_name,
    l.unit,
    l.lsl,
    l.usl,
    l.typical_value,
    l.cpk,
    l.revision,
    l.effective_date,
    l.authored_by
  FROM ${catalog}.tps.historical_test_limits AS l
  JOIN ${catalog}.tps.product_families AS f
    ON f.product_family_id = l.product_family_id
  WHERE f.family_name = recommend_test_limits.product_family
    AND l.parameter_name = recommend_test_limits.parameter_name
  ORDER BY l.effective_date DESC;
