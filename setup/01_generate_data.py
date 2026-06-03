"""Generate synthetic manufacturing test data for the TPS memory agent demo.

Produces five governed Delta tables in <catalog>.tps and a set of SOP markdown
docs in the sop_docs volume (used by the Agent Bricks Knowledge Assistant lane):

    product_families        ~12 rows
    test_blocks             ~25 rows
    historical_test_limits  ~3,000 rows   (carries authored_by -> institutional knowledge)
    yield_by_test_block     ~6,000 rows   (a few injected low-yield families/blocks)
    equipment_catalog       ~150 rows

Data is generated locally with Polars + NumPy (deterministic seed) and written to
Unity Catalog through Databricks Connect (serverless). Run two ways:

    # Local, against the target workspace via a CLI profile:
    DATABRICKS_CONFIG_PROFILE=fevm-digital-twin python setup/01_generate_data.py --catalog tps_demo

    # Or inside a Databricks notebook/Serverless V5: a `spark` session already
    # exists, so it is reused automatically.

Target workspace: fevm-digital-twin-generic.cloud.databricks.com (org 7474657725221208)
"""

from __future__ import annotations

import argparse
import textwrap

import numpy as np
import polars as pl

SEED = 42
rng = np.random.default_rng(SEED)

# --------------------------------------------------------------------------- #
# Reference vocabularies
# --------------------------------------------------------------------------- #
ENGINEERS = [
    "amelia.cho", "ravi.patel", "sofia.reyes", "liam.osborne",
    "noor.haddad", "kenji.tan", "greta.muller", "diego.santos",
]

PRODUCT_FAMILIES = [
    # (family_name, process_node_nm, package_type, target_market, nominal_voltage_v)
    ("PMIC-Buck-A",    28, "QFN-32",   "automotive",  3.3),
    ("PMIC-Buck-B",    40, "QFN-24",   "industrial",  5.0),
    ("PMIC-LDO-C",     65, "DFN-8",    "consumer",    1.8),
    ("MCU-Cortex-M4",  28, "LQFP-64",  "industrial",  3.3),
    ("MCU-Cortex-M0",  90, "QFN-48",   "consumer",    3.3),
    ("RF-Frontend-X",  16, "WLCSP-36", "mobile",      1.2),
    ("RF-Frontend-Y",  22, "WLCSP-49", "mobile",      1.2),
    ("SENSOR-IMU-D",   65, "LGA-16",   "consumer",    1.8),
    ("SENSOR-TEMP-E",  90, "SOT-23",   "industrial",  3.3),
    ("PWR-GaN-F",     150, "PQFN-56",  "automotive", 12.0),
    ("ADC-16b-G",      28, "TQFP-48",  "industrial",  3.3),
    ("DAC-12b-H",      40, "TSSOP-20", "consumer",    3.3),
]

TEST_BLOCKS = [
    # (block_name, block_category, typical_duration_ms, description)
    ("Continuity",        "DC",          120,  "Open/short detection on all pins."),
    ("IDDQ",              "DC",          340,  "Quiescent supply current screen for defects."),
    ("Leakage",           "DC",          210,  "Pin leakage current under bias."),
    ("Vmin Shmoo",        "Functional",  900,  "Minimum operating voltage characterization."),
    ("Fmax",              "AC",          780,  "Maximum operating frequency search."),
    ("Trim/Calibration",  "Functional",  650,  "Bandgap and oscillator trim."),
    ("ADC Linearity",     "AC",          540,  "INL/DNL across input range."),
    ("RF S-Parameter",    "RF",          1100, "S11/S21 across band."),
    ("RF Power",          "RF",          820,  "Output power and efficiency."),
    ("Burn-In Screen",    "Reliability", 4200, "Accelerated stress for early-life failures."),
    ("Thermal Cycle",     "Reliability", 3600, "Temperature cycling stress."),
    ("ESD Verify",        "Reliability", 480,  "HBM/CDM verification."),
]

PARAMETERS = [
    # (parameter_name, unit, nominal, spread, block_category)
    ("Iddq_quiescent_uA",  "uA",   30.0,  12.0, "DC"),
    ("Pin_leakage_nA",     "nA",   50.0,  20.0, "DC"),
    ("Vout_accuracy_pct",  "%",    0.0,    1.2, "Functional"),
    ("Vmin_V",             "V",    1.05,   0.15, "Functional"),
    ("Fmax_MHz",           "MHz",  180.0,  25.0, "AC"),
    ("INL_LSB",            "LSB",  0.0,    0.8, "AC"),
    ("S21_dB",             "dB",   18.0,   2.0, "RF"),
    ("Pout_dBm",           "dBm",  24.0,   1.5, "RF"),
    ("ESD_HBM_kV",         "kV",   2.0,    0.4, "Reliability"),
]

EQUIPMENT_TESTERS = [
    "Advantest V93000", "Teradyne UltraFLEX", "Teradyne J750",
    "Advantest T2000", "Cohu Diamondx", "Chroma 3680",
]
EQUIPMENT_HANDLERS = [
    "Cohu MATRiX", "Advantest HA1000", "Aetrium 5000", "Multitest MT9928",
]
ZONES = ["fab-A line1", "fab-A line2", "fab-B line1", "fab-B line2", "OSAT-1"]

# Families/blocks we deliberately depress to power the "grounded recommendation" demo.
LOW_YIELD_FAMILIES = {"PMIC-Buck-A", "RF-Frontend-X"}
LOW_YIELD_BLOCKS = {"IDDQ", "RF S-Parameter"}


def build_frames() -> dict[str, pl.DataFrame]:
    # ---- product_families ----
    families = pl.DataFrame(
        {
            "product_family_id": list(range(1, len(PRODUCT_FAMILIES) + 1)),
            "family_name":       [r[0] for r in PRODUCT_FAMILIES],
            "process_node_nm":   [r[1] for r in PRODUCT_FAMILIES],
            "package_type":      [r[2] for r in PRODUCT_FAMILIES],
            "target_market":     [r[3] for r in PRODUCT_FAMILIES],
            "nominal_voltage_v": [r[4] for r in PRODUCT_FAMILIES],
        }
    )

    # ---- test_blocks ----
    blocks = pl.DataFrame(
        {
            "test_block_id":       list(range(1, len(TEST_BLOCKS) + 1)),
            "block_name":          [r[0] for r in TEST_BLOCKS],
            "block_category":      [r[1] for r in TEST_BLOCKS],
            "typical_duration_ms": [r[2] for r in TEST_BLOCKS],
            "description":         [r[3] for r in TEST_BLOCKS],
        }
    )
    cat_by_block = {r[0]: r[1] for r in TEST_BLOCKS}

    # ---- historical_test_limits ----
    # Several revisions per (family, parameter) over time, with tighter limits at
    # smaller process nodes and a believable Cpk. authored_by ties a decision to
    # an engineer -> the institutional-knowledge story.
    limit_rows = []
    limit_id = 1
    node_by_family = {r[0]: r[1] for r in PRODUCT_FAMILIES}
    for fid, (fname, *_rest) in enumerate(PRODUCT_FAMILIES, start=1):
        node = node_by_family[fname]
        node_factor = float(np.clip(node / 90.0, 0.4, 1.2))  # smaller node -> tighter
        for (pname, unit, nominal, spread, _pcat) in PARAMETERS:
            n_rev = int(rng.integers(2, 6))
            base_typ = nominal + rng.normal(0, spread * 0.1)
            for rev in range(1, n_rev + 1):
                width = spread * node_factor * (1.0 - 0.06 * (rev - 1))  # tightens over revs
                lsl = round(base_typ - width, 3)
                usl = round(base_typ + width, 3)
                cpk = round(float(np.clip(rng.normal(1.45, 0.25), 0.7, 2.4)), 2)
                year = 2023 + (rev - 1) // 2
                month = 1 + ((rev - 1) * 5) % 12
                limit_rows.append(
                    {
                        "limit_id": limit_id,
                        "product_family_id": fid,
                        "parameter_name": pname,
                        "unit": unit,
                        "lsl": lsl,
                        "usl": usl,
                        "typical_value": round(base_typ, 3),
                        "cpk": cpk,
                        "revision": f"R{rev}.0",
                        "effective_date": f"{year}-{month:02d}-15",
                        "authored_by": ENGINEERS[rng.integers(0, len(ENGINEERS))],
                    }
                )
                limit_id += 1
    limits = pl.DataFrame(limit_rows).with_columns(
        pl.col("effective_date").str.to_date()
    )

    # ---- yield_by_test_block ----
    yield_rows = []
    record_id = 1
    params_by_cat: dict[str, list[str]] = {}
    for (pname, _u, _n, _s, pcat) in PARAMETERS:
        params_by_cat.setdefault(pcat, []).append(pname)
    for fid, (fname, *_rest) in enumerate(PRODUCT_FAMILIES, start=1):
        for bid, (bname, bcat, *_b) in enumerate(TEST_BLOCKS, start=1):
            base_yield = 98.5
            if fname in LOW_YIELD_FAMILIES:
                base_yield -= 4.0
            if bname in LOW_YIELD_BLOCKS:
                base_yield -= 6.0
            n_lots = int(rng.integers(8, 16))
            for _ in range(n_lots):
                tested = int(rng.integers(2000, 8000))
                y = float(np.clip(rng.normal(base_yield, 1.6), 70.0, 99.99))
                passed = int(round(tested * y / 100.0))
                fail_params = params_by_cat.get(bcat) or [p[0] for p in PARAMETERS]
                yield_rows.append(
                    {
                        "record_id": record_id,
                        "product_family_id": fid,
                        "test_block_id": bid,
                        "lot_id": f"LOT-{fid:02d}{bid:02d}-{rng.integers(1000,9999)}",
                        "tested_units": tested,
                        "passed_units": passed,
                        "yield_pct": round(100.0 * passed / tested, 2),
                        "top_failing_parameter": fail_params[rng.integers(0, len(fail_params))],
                        "test_date": f"2024-{1 + rng.integers(0,12):02d}-{1 + rng.integers(0,28):02d}",
                        "fab_site": ZONES[rng.integers(0, len(ZONES))],
                    }
                )
                record_id += 1
    yields = pl.DataFrame(yield_rows).with_columns(pl.col("test_date").str.to_date())

    # ---- equipment_catalog ----
    all_categories = ["DC", "AC", "RF", "Functional", "Reliability"]
    eq_rows = []
    for eid in range(1, 151):
        n_cat = int(rng.integers(1, 4))
        cats = sorted(rng.choice(all_categories, size=n_cat, replace=False).tolist())
        eq_rows.append(
            {
                "equipment_id": f"EQ-{eid:04d}",
                "tester_model": EQUIPMENT_TESTERS[rng.integers(0, len(EQUIPMENT_TESTERS))],
                "handler_model": EQUIPMENT_HANDLERS[rng.integers(0, len(EQUIPMENT_HANDLERS))],
                "supported_block_categories": cats,
                "max_parallel_sites": int(rng.choice([1, 2, 4, 8, 16, 32])),
                "temperature_range_c": rng.choice(["-40..125", "-20..85", "0..70", "-55..150"]),
                "location_zone": ZONES[rng.integers(0, len(ZONES))],
                "status": "available" if rng.random() > 0.12 else "maintenance",
                "hourly_cost_usd": round(float(rng.uniform(40, 320)), 2),
            }
        )
    equipment = pl.DataFrame(eq_rows)

    return {
        "product_families": families,
        "test_blocks": blocks,
        "historical_test_limits": limits,
        "yield_by_test_block": yields,
        "equipment_catalog": equipment,
    }


SOP_DOCS = {
    "guardband_policy.md": """# Guard-Band Policy (TPS Authoring)

Guard-bands protect against measurement uncertainty and drift. Default policy:
- Apply a guard-band of 1x gauge R&R to every DC parametric limit.
- For automotive-grade families, tighten LSL/USL by an additional 10%.
- Never set a limit looser than the most recent released revision without a
  documented rationale saved as a team decision.
""",
    "iddq_screening.md": """# IDDQ Screening Guidance

IDDQ is a defect screen, not a performance test. Author IDDQ limits from the
distribution of known-good die, not the datasheet maximum. Families on smaller
process nodes leak more; scale the USL with process node. If a family shows
recurring IDDQ yield loss, add a per-lot IDDQ trend check before final test.
""",
    "equipment_selection.md": """# Equipment Selection

Pick the cheapest tester that (a) supports the test block category and (b) gives
enough parallel sites to hit the throughput target. RF blocks must run on an RF-
capable tester. Reliability blocks (burn-in, thermal cycle) require ovens; verify
temperature range covers the qualification profile.
""",
    "test_sequence.md": """# Test Sequence Conventions

Order blocks cheapest-and-most-discriminating first: Continuity -> IDDQ ->
Leakage -> Functional -> AC -> RF -> Reliability. Fail-fast on Continuity and
IDDQ to avoid spending tester time on already-bad die.
""",
    "revision_control.md": """# Spec Revision Control

Every limit change is a revision (R1.0, R2.0, ...). Record who made the change
and why. Reuse prior revisions as the starting point for a new product in the
same family; do not re-derive from scratch.
""",
}


def get_spark():
    try:
        return spark  # type: ignore[name-defined]  # in a Databricks notebook
    except NameError:
        from databricks.connect import DatabricksSession

        return DatabricksSession.builder.serverless().getOrCreate()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True, help="Target UC catalog, e.g. tps_demo")
    ap.add_argument("--schema", default="tps")
    args = ap.parse_args()

    spark_session = get_spark()
    fq = f"{args.catalog}.{args.schema}"
    spark_session.sql(f"CREATE CATALOG IF NOT EXISTS {args.catalog}")
    spark_session.sql(f"CREATE SCHEMA IF NOT EXISTS {fq}")
    spark_session.sql(f"CREATE VOLUME IF NOT EXISTS {fq}.sop_docs")

    frames = build_frames()
    for name, df in frames.items():
        (
            spark_session.createDataFrame(df.to_pandas())
            .write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(f"{fq}.{name}")
        )
        print(f"  wrote {fq}.{name:<24} ({df.height} rows)")

    # Upload SOP docs to the volume via the SDK (works locally and in a notebook).
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    vol_path = f"/Volumes/{args.catalog}/{args.schema}/sop_docs"
    for fname, body in SOP_DOCS.items():
        w.files.upload(
            f"{vol_path}/{fname}",
            textwrap.dedent(body).encode("utf-8"),
            overwrite=True,
        )
        print(f"  wrote {vol_path}/{fname}")

    print("\n✅ TPS demo data ready in", fq)


if __name__ == "__main__":
    main()
