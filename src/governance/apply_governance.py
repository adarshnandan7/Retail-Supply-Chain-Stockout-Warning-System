# Databricks notebook source
# MAGIC %md
# MAGIC # 06 - Unity Catalog governance
# MAGIC * Business-friendly table and column comments (they also ground Genie and the AI/BI dashboard).
# MAGIC * Governance tags on every table (domain, layer, owner, sensitivity).
# MAGIC * A governed consumption view with row-level security (planners see only their region) and a column
# MAGIC   mask (financial exposure visible only to supply-chain finance and admins).
# MAGIC * Least-privilege grants: consumers get `SELECT` on the governed view, not on base tables.
# MAGIC Lineage from landing files to the planner app is captured automatically by Unity Catalog.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
log = []

def run(sql):
    try:
        spark.sql(sql)
        log.append({"ok": True, "sql": " ".join(sql.split())[:160]})
    except Exception as e:  # keep going; report every failure in the evidence file
        log.append({"ok": False, "sql": " ".join(sql.split())[:160], "error": str(e).splitlines()[0][:200]})

# COMMAND ----------

# MAGIC %md ## Column comments on the published tables

# COMMAND ----------

col_comments = {
    "risk_recommendations": {
        "recommendation_id": "Store/SKU key (store_id-sku_id); primary key synced to Lakebase",
        "as_of_date": "Business date the risk was scored for (last closed sales day)",
        "risk_score": "0-100. 100 x stockout probability x (0.6 + 0.4 x value weight). Higher = act sooner",
        "risk_tier": "Critical (>=70), High (>=45), Medium (>=25), Low",
        "risk_rank": "Rank across all store/SKUs by risk score then revenue at risk (1 = most urgent)",
        "stockout_probability": "Probability that demand exceeds on-hand + projected inbound at some day within the replenishment window",
        "lead_time_window_days": "Replenishment window: p90 actual supplier lead time (last 90 days) + 1 review day",
        "forecast_demand_window": "Forecast units over the replenishment window from the @champion model",
        "baseline_demand_window": "Seasonal-naive 'usual' demand over the same window, for comparison",
        "on_hand_units": "End-of-day on-hand units on the as-of date",
        "inbound_units_in_window": "Open PO units projected to arrive inside the window (adjusted for recent supplier lateness)",
        "days_of_cover": "On-hand units divided by average forecast daily demand for the next 7 days",
        "projected_stockout_in_days": "First day (1-28) on which cumulative forecast demand exceeds projected availability",
        "expected_lost_units": "Expected unmet demand at the end of the window (normal loss function)",
        "revenue_at_risk": "Expected lost units x unit price (USD)",
        "primary_driver": "Largest quantified driver: Upcoming promotion, Holiday demand ramp, Late supplier delivery, Recent demand surge, Insufficient stock cover, No open purchase order",
        "driver_details": "All quantified drivers in plain language",
        "recommended_action": "EXPEDITE, TRANSFER, REORDER or MONITOR. Decision support only; nothing is ordered automatically",
        "recommended_qty": "Suggested units for the action (case-pack rounded for reorders)",
        "action_source_id": "Supplier to expedite/reorder from, or donor store for a transfer",
        "planner_explanation": "Two-sentence planner note (LLM for Critical/High, deterministic template otherwise)",
    },
    "gold_daily_store_sku_sales": {
        "is_stockout": "True when end-of-day on hand = 0 (sales that day are censored demand)",
        "units_sold": "Units sold (0 when no POS record)",
        "on_promo": "SKU was on promotion at this store that day",
        "days_to_next_holiday": "Calendar days until the next holiday (99 if none)",
    },
}
for t, cols in col_comments.items():
    for c, txt in cols.items():
        kind = "TABLE" if t.startswith("risk") else "MATERIALIZED VIEW"
        run(f"COMMENT ON COLUMN {FQ}.{t}.{c} IS '{txt}'") if kind == "TABLE" else run(f"ALTER MATERIALIZED VIEW {FQ}.{t} ALTER COLUMN {c} COMMENT '{txt}'")

# COMMAND ----------

# MAGIC %md ## Governance tags

# COMMAND ----------

tables = spark.sql(f"SELECT table_name, table_type FROM {CATALOG}.information_schema.tables WHERE table_schema = '{SCHEMA}'").collect()
for r in tables:
    name = r.table_name
    layer = name.split("_")[0] if name.split("_")[0] in ("bronze", "silver", "gold") else ("ml" if name in ("demand_forecast", "forecast_backtest") else "serving")
    sens = "commercial_confidential" if name.startswith(("risk", "gold_supplier", "silver_suppliers", "silver_products")) else "internal"
    kw = {"MATERIALIZED_VIEW": "MATERIALIZED VIEW", "STREAMING_TABLE": "STREAMING TABLE", "VIEW": "VIEW"}.get(r.table_type, "TABLE")
    run(f"ALTER {kw} {FQ}.{name} SET TAGS ('domain' = 'supply_chain', 'layer' = '{layer}', 'data_owner' = 'replenishment_planning', 'sensitivity' = '{sens}', 'contains_pii' = 'false')")

# COMMAND ----------

# MAGIC %md ## Row-level security + column masking for consumers (dynamic view)

# COMMAND ----------

run(f"""
CREATE OR REPLACE FUNCTION {FQ}.can_see_region(region STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: admins and chain-wide planners see all regions; regional planners (account group planners_<region>) see their own region.'
RETURN is_member('admins') OR is_account_group_member('inventory_planners_all')
       OR is_account_group_member(concat('planners_', lower(replace(region, ' ', '_'))))
""")
run(f"""
CREATE OR REPLACE FUNCTION {FQ}.can_see_financials()
RETURNS BOOLEAN
COMMENT 'Column mask helper: revenue exposure is visible to admins and supply-chain finance only.'
RETURN is_member('admins') OR is_account_group_member('supply_chain_finance')
""")
run(f"""
CREATE OR REPLACE VIEW {FQ}.v_planner_risk_queue
COMMENT 'Governed planner risk queue: region-filtered rows, revenue at risk masked for non-finance users. Grant this, not the base table.'
AS SELECT recommendation_id, as_of_date, risk_rank, risk_score, risk_tier, store_id, store_name, region, sku_id, sku_name, category,
          supplier_name, on_hand_units, inbound_units_in_window, forecast_demand_window, lead_time_window_days, days_of_cover,
          projected_stockout_in_days, stockout_probability,
          CASE WHEN {FQ}.can_see_financials() THEN revenue_at_risk END AS revenue_at_risk,
          primary_driver, driver_details, recommended_action, recommended_qty, action_source_id, planner_explanation
FROM {FQ}.risk_recommendations
WHERE {FQ}.can_see_region(region)
""")
run(f"ALTER VIEW {FQ}.v_planner_risk_queue SET TAGS ('domain' = 'supply_chain', 'layer' = 'serving', 'governance' = 'row_filter_and_mask')")

# COMMAND ----------

# MAGIC %md ## Least-privilege grants

# COMMAND ----------

run(f"GRANT USE SCHEMA ON SCHEMA {FQ} TO `account users`")
run(f"GRANT SELECT ON VIEW {FQ}.v_planner_risk_queue TO `account users`")
run(f"GRANT EXECUTE ON FUNCTION {FQ}.can_see_region TO `account users`")
run(f"GRANT EXECUTE ON FUNCTION {FQ}.can_see_financials TO `account users`")

# COMMAND ----------

import json, pandas as pd
df = pd.DataFrame(log)
print(df.ok.value_counts().to_dict())
print(df[~df.ok].to_string() if (~df.ok).any() else "all governance statements succeeded")
tags = spark.sql(f"SELECT table_name, tag_name, tag_value FROM {CATALOG}.information_schema.table_tags WHERE schema_name = '{SCHEMA}' AND tag_name IN ('layer','sensitivity') ORDER BY 1,2").toPandas()
print(tags.pivot(index="table_name", columns="tag_name", values="tag_value").to_string())
masked = spark.sql(f"SELECT count(*) AS visible_rows, count(revenue_at_risk) AS rows_with_revenue_visible FROM {FQ}.v_planner_risk_queue").toPandas()
print(masked.to_string(index=False))
with open(f"{EVIDENCE}/06_governance.json", "w") as fh:
    json.dump({"statements": log, "tags": tags.to_dict(orient="records"), "view_check_as_admin": masked.to_dict(orient="records")}, fh, indent=2, default=str)
