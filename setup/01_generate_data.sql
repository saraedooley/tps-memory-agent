-- Server-side synthetic data generation for the TPS memory agent demo.
-- Pure Spark SQL (no local deps) — run with setup/run_sql.py against a SQL
-- warehouse. Statements are separated by a line containing only `-- @@`.
-- ${catalog} is substituted by the runner (default: tps_demo).
--
-- Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)

CREATE SCHEMA IF NOT EXISTS ${catalog}.tps
-- @@
CREATE VOLUME IF NOT EXISTS ${catalog}.tps.sop_docs
-- @@
CREATE OR REPLACE TABLE ${catalog}.tps.product_families AS
SELECT * FROM VALUES
  (1 ,'PMIC-Buck-A'  ,28 ,'QFN-32'  ,'automotive',3.3),
  (2 ,'PMIC-Buck-B'  ,40 ,'QFN-24'  ,'industrial',5.0),
  (3 ,'PMIC-LDO-C'   ,65 ,'DFN-8'   ,'consumer'  ,1.8),
  (4 ,'MCU-Cortex-M4',28 ,'LQFP-64' ,'industrial',3.3),
  (5 ,'MCU-Cortex-M0',90 ,'QFN-48'  ,'consumer'  ,3.3),
  (6 ,'RF-Frontend-X',16 ,'WLCSP-36','mobile'    ,1.2),
  (7 ,'RF-Frontend-Y',22 ,'WLCSP-49','mobile'    ,1.2),
  (8 ,'SENSOR-IMU-D' ,65 ,'LGA-16'  ,'consumer'  ,1.8),
  (9 ,'SENSOR-TEMP-E',90 ,'SOT-23'  ,'industrial',3.3),
  (10,'PWR-GaN-F'    ,150,'PQFN-56' ,'automotive',12.0),
  (11,'ADC-16b-G'    ,28 ,'TQFP-48' ,'industrial',3.3),
  (12,'DAC-12b-H'    ,40 ,'TSSOP-20','consumer'  ,3.3)
  AS t(product_family_id, family_name, process_node_nm, package_type, target_market, nominal_voltage_v)
-- @@
CREATE OR REPLACE TABLE ${catalog}.tps.test_blocks AS
SELECT * FROM VALUES
  (1 ,'Continuity'      ,'DC'         ,120 ,'Open/short detection on all pins.'),
  (2 ,'IDDQ'            ,'DC'         ,340 ,'Quiescent supply current screen for defects.'),
  (3 ,'Leakage'        ,'DC'         ,210 ,'Pin leakage current under bias.'),
  (4 ,'Vmin Shmoo'     ,'Functional' ,900 ,'Minimum operating voltage characterization.'),
  (5 ,'Fmax'           ,'AC'         ,780 ,'Maximum operating frequency search.'),
  (6 ,'Trim/Calibration','Functional',650 ,'Bandgap and oscillator trim.'),
  (7 ,'ADC Linearity'  ,'AC'         ,540 ,'INL/DNL across input range.'),
  (8 ,'RF S-Parameter' ,'RF'         ,1100,'S11/S21 across band.'),
  (9 ,'RF Power'       ,'RF'         ,820 ,'Output power and efficiency.'),
  (10,'Burn-In Screen' ,'Reliability',4200,'Accelerated stress for early-life failures.'),
  (11,'Thermal Cycle'  ,'Reliability',3600,'Temperature cycling stress.'),
  (12,'ESD Verify'     ,'Reliability',480 ,'HBM/CDM verification.')
  AS t(test_block_id, block_name, block_category, typical_duration_ms, description)
-- @@
CREATE OR REPLACE TABLE ${catalog}.tps.historical_test_limits AS
WITH params AS (
  SELECT * FROM VALUES
    ('Iddq_quiescent_uA','uA' ,30.0 ,12.0,'DC'),
    ('Pin_leakage_nA'   ,'nA' ,50.0 ,20.0,'DC'),
    ('Vout_accuracy_pct','%'  ,0.0  ,1.2 ,'Functional'),
    ('Vmin_V'           ,'V'  ,1.05 ,0.15,'Functional'),
    ('Fmax_MHz'         ,'MHz',180.0,25.0,'AC'),
    ('INL_LSB'          ,'LSB',0.0  ,0.8 ,'AC'),
    ('S21_dB'           ,'dB' ,18.0 ,2.0 ,'RF'),
    ('Pout_dBm'         ,'dBm',24.0 ,1.5 ,'RF'),
    ('ESD_HBM_kV'       ,'kV' ,2.0  ,0.4 ,'Reliability')
    AS p(parameter_name, unit, nominal, spread, pcat)
),
revs AS (SELECT explode(sequence(1,4)) AS rev),
fam AS (
  SELECT product_family_id, greatest(0.4, least(1.2, process_node_nm/90.0)) AS node_factor
  FROM ${catalog}.tps.product_families
),
xj AS (
  SELECT f.product_family_id, p.parameter_name, p.unit, p.nominal, r.rev,
         p.spread * f.node_factor * (1 - 0.06*(r.rev-1)) AS width
  FROM fam f CROSS JOIN params p CROSS JOIN revs r
)
SELECT
  row_number() OVER (ORDER BY product_family_id, parameter_name, rev) AS limit_id,
  product_family_id,
  parameter_name,
  unit,
  round(nominal - width, 3) AS lsl,
  round(nominal + width, 3) AS usl,
  round(nominal, 3)         AS typical_value,
  round(1.0 + rand()*0.9, 2) AS cpk,
  concat('R', rev, '.0')    AS revision,
  date_add(DATE'2023-01-15', (rev-1)*150) AS effective_date,
  element_at(array('amelia.cho','ravi.patel','sofia.reyes','liam.osborne',
                   'noor.haddad','kenji.tan','greta.muller','diego.santos'),
             cast(1 + floor(rand()*8) AS INT)) AS authored_by
FROM xj
-- @@
CREATE OR REPLACE TABLE ${catalog}.tps.yield_by_test_block AS
WITH lots AS (SELECT explode(sequence(1,10)) AS lot_n),
base AS (
  SELECT f.product_family_id, f.family_name, b.test_block_id, b.block_name, b.block_category, l.lot_n,
    98.5
      - CASE WHEN f.family_name IN ('PMIC-Buck-A','RF-Frontend-X') THEN 4.0 ELSE 0 END
      - CASE WHEN b.block_name  IN ('IDDQ','RF S-Parameter')       THEN 6.0 ELSE 0 END AS base_yield
  FROM ${catalog}.tps.product_families f
  CROSS JOIN ${catalog}.tps.test_blocks b
  CROSS JOIN lots l
),
calc AS (
  SELECT *,
    cast(2000 + floor(rand()*6000) AS INT) AS tested_units,
    greatest(70.0, least(99.99, base_yield + (rand()-0.5)*5)) AS y
  FROM base
)
SELECT
  row_number() OVER (ORDER BY product_family_id, test_block_id, lot_n) AS record_id,
  product_family_id,
  test_block_id,
  concat('LOT-', lpad(product_family_id,2,'0'), lpad(test_block_id,2,'0'), '-',
         cast(1000 + floor(rand()*9000) AS INT)) AS lot_id,
  tested_units,
  cast(round(tested_units * y/100.0) AS INT) AS passed_units,
  round(y, 2) AS yield_pct,
  CASE block_category
    WHEN 'DC'         THEN element_at(array('Iddq_quiescent_uA','Pin_leakage_nA'), cast(1+floor(rand()*2) AS INT))
    WHEN 'AC'         THEN element_at(array('Fmax_MHz','INL_LSB'), cast(1+floor(rand()*2) AS INT))
    WHEN 'RF'         THEN element_at(array('S21_dB','Pout_dBm'), cast(1+floor(rand()*2) AS INT))
    WHEN 'Functional' THEN element_at(array('Vout_accuracy_pct','Vmin_V'), cast(1+floor(rand()*2) AS INT))
    ELSE 'ESD_HBM_kV'
  END AS top_failing_parameter,
  date_add(DATE'2024-01-01', cast(floor(rand()*330) AS INT)) AS test_date,
  element_at(array('fab-A line1','fab-A line2','fab-B line1','fab-B line2','OSAT-1'),
             cast(1+floor(rand()*5) AS INT)) AS fab_site
FROM calc
-- @@
CREATE OR REPLACE TABLE ${catalog}.tps.equipment_catalog AS
WITH seq AS (SELECT explode(sequence(1,150)) AS n)
SELECT
  concat('EQ-', lpad(n,4,'0')) AS equipment_id,
  element_at(array('Advantest V93000','Teradyne UltraFLEX','Teradyne J750',
                   'Advantest T2000','Cohu Diamondx','Chroma 3680'),
             cast(1+floor(rand()*6) AS INT)) AS tester_model,
  element_at(array('Cohu MATRiX','Advantest HA1000','Aetrium 5000','Multitest MT9928'),
             cast(1+floor(rand()*4) AS INT)) AS handler_model,
  CASE n % 5
    WHEN 0 THEN array('DC')
    WHEN 1 THEN array('AC')
    WHEN 2 THEN array('RF')
    WHEN 3 THEN array('Functional')
    ELSE        array('Reliability')
  END AS supported_block_categories,
  element_at(array(1,2,4,8,16,32), cast(1+floor(rand()*6) AS INT)) AS max_parallel_sites,
  element_at(array('-40..125','-20..85','0..70','-55..150'), cast(1+floor(rand()*4) AS INT)) AS temperature_range_c,
  element_at(array('fab-A line1','fab-A line2','fab-B line1','fab-B line2','OSAT-1'),
             cast(1+floor(rand()*5) AS INT)) AS location_zone,
  CASE WHEN rand() > 0.12 THEN 'available' ELSE 'maintenance' END AS status,
  round(40 + rand()*280, 2) AS hourly_cost_usd
FROM seq
