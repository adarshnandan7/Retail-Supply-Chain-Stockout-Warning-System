"""Build the Genie space definition (serialized_space v2) from readable source files.

Writes src/genie/inventory_risk.geniespace.json, which resources/genie.yml deploys as a bundle resource.
Run: python src/genie/build_space.py [catalog] [schema]
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
CATALOG = sys.argv[1] if len(sys.argv) > 1 else "serverless_stable_3vku19_catalog"
SCHEMA = sys.argv[2] if len(sys.argv) > 2 else "inventory_risk"
FQ = f"{CATALOG}.{SCHEMA}"


def gid(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()  # deterministic 32-hex ids keep diffs stable


TABLES = {
    "risk_recommendations": "Current ranked stockout risks per store/SKU with drivers, suggested action and planner note. One row per store/SKU for the latest as_of_date.",
    "demand_forecast": "Next-28-day daily forecast per store/SKU (forecast_units) with the seasonal-naive baseline (baseline_units).",
    "gold_current_inventory_position": "As-of on hand, inbound units, trailing 28-day demand and days of cover per store/SKU.",
    "gold_inbound_po_pipeline": "Open purchase-order lines with expected and projected arrival dates and supplier lateness.",
    "gold_supplier_lead_time_stats": "Supplier delivery performance: contract vs actual lead time, on-time rate overall and last 30 days.",
    "gold_daily_store_sku_sales": "Two years of daily store/SKU sales, on hand and stockout flags.",
    "forecast_backtest": "Holdout forecasts vs actuals for the model (lgbm_pred) and baseline (baseline_pred).",
    "risk_backtest": "Risk scores computed 4 weeks ago with the actual outcome (actual_stockout_in_window) for alert-precision analysis.",
    "mv_inventory_risk": "Metric view: alert counts, revenue at risk, cover and excess. Query with MEASURE().",
    "mv_forecast_accuracy": "Metric view: model vs baseline WAPE and bias. Query with MEASURE().",
    "mv_stockout_history": "Metric view: historical stockout rate. Query with MEASURE().",
    "mv_alert_backtest": "Metric view: alert precision and recall for the radar vs the rule of thumb. Query with MEASURE().",
}

instructions = (HERE / "instructions.md").read_text()
examples = json.loads((HERE / "example_sqls.json").read_text())
questions = [
    "Which 10 store-SKUs have the highest revenue at risk right now?",
    "How many Critical and High risks are there by region and primary driver?",
    "Which suppliers are causing the most late-delivery risks?",
    "What is the forecast WAPE of the model vs the baseline by category?",
    "What was the alert precision of the radar compared with the rule of thumb?",
    "Which items are projected to stock out within 3 days in Metro North?",
]

space = {
    "version": 2,
    "config": {"sample_questions": sorted([{"id": gid(q), "question": [q]} for q in questions], key=lambda x: x["id"])},
    "data_sources": {"tables": sorted([{"identifier": f"{FQ}.{t}", "description": [d]} for t, d in TABLES.items()], key=lambda x: x["identifier"])},
    "instructions": {
        "text_instructions": [{"id": gid("main"), "content": [instructions]}],
        "example_question_sqls": sorted([{"id": gid(e["question"]), "question": [e["question"]], "sql": [e["sql"].replace("{FQ}", FQ)]}
                                         for e in examples], key=lambda x: x["id"]),
    },
}
(HERE / "inventory_risk.geniespace.json").write_text(json.dumps(space, indent=2))
print(f"wrote {HERE / 'inventory_risk.geniespace.json'}: {len(TABLES)} tables, {len(examples)} example SQLs, {len(questions)} sample questions")
