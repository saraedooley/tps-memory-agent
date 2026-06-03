-- UC Function tool #3: choose capable test equipment by block category, with cost.
-- Lets the agent ground equipment selection in the real tester fleet.

CREATE OR REPLACE FUNCTION ${catalog}.tps.lookup_equipment_for_test(
  block_category STRING COMMENT 'Test block category to match, one of: DC, AC, RF, Functional, Reliability.'
)
RETURNS TABLE (
  tester_model       STRING,
  handler_model      STRING,
  max_parallel_sites INT,
  temperature_range_c STRING,
  hourly_cost_usd    DOUBLE,
  location_zone      STRING
)
READS SQL DATA
COMMENT 'Returns test equipment (tester + handler) capable of running a given test block category, with parallel-site count and hourly cost, cheapest-capable first. Use this to recommend equipment for a test block and justify the choice on throughput (parallel sites) and cost.'
RETURN
  SELECT
    e.tester_model,
    e.handler_model,
    e.max_parallel_sites,
    e.temperature_range_c,
    e.hourly_cost_usd,
    e.location_zone
  FROM ${catalog}.tps.equipment_catalog AS e
  WHERE array_contains(e.supported_block_categories, lookup_equipment_for_test.block_category)
    AND e.status = 'available'
  ORDER BY e.hourly_cost_usd ASC, e.max_parallel_sites DESC;
