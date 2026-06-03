-- UC Function tool #2: flag test blocks that historically lose yield for a family.
-- Lets the agent warn the engineer which blocks are risky and why.

CREATE OR REPLACE FUNCTION ${catalog}.tps.yield_risk_by_block(
  product_family STRING COMMENT 'Product family name, e.g. "PMIC-Buck-A".'
)
RETURNS TABLE (
  block_name           STRING,
  block_category       STRING,
  avg_yield_pct        DOUBLE,
  lots_observed        BIGINT,
  top_failing_parameter STRING
)
READS SQL DATA
COMMENT 'Returns average historical yield per test block for a product family, with the most common failing parameter, ordered worst-yield first. Use this to flag risky test blocks and justify tighter screening or added test coverage in the spec.'
RETURN
  SELECT
    b.block_name,
    b.block_category,
    ROUND(AVG(y.yield_pct), 2)                 AS avg_yield_pct,
    COUNT(DISTINCT y.lot_id)                    AS lots_observed,
    MAX_BY(y.top_failing_parameter, y.tested_units) AS top_failing_parameter
  FROM ${catalog}.tps.yield_by_test_block AS y
  JOIN ${catalog}.tps.product_families AS f
    ON f.product_family_id = y.product_family_id
  JOIN ${catalog}.tps.test_blocks AS b
    ON b.test_block_id = y.test_block_id
  WHERE f.family_name = yield_risk_by_block.product_family
  GROUP BY b.block_name, b.block_category
  ORDER BY avg_yield_pct ASC;
