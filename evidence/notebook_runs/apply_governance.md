# Task `apply_governance` - SUCCESS
- Task run id: `446362247060598`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/governance/apply_governance`
- Duration: 77 s

## Cell 1

```markdown
%md
# 06 - Unity Catalog governance
* Business-friendly table and column comments (they also ground Genie and the AI/BI dashboard).
* Governance tags on every table (domain, layer, owner, sensitivity).
* An enforced Unity Catalog row filter (planners see only their region) and column mask (financial exposure
  visible only to entitled principals) on the planner-facing table, with an enforcement test.
* Least-privilege grants: consumers get `SELECT` on the governed table, not on base tables.
Lineage from landing files to the planner app is captured automatically by Unity Catalog.
```

## Cell 2

```python
dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("app_sp_client_id", "")
APP_SP = dbutils.widgets.get("app_sp_client_id")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
import json
log = []

def run(sql):
    try:
        spark.sql(sql)
        log.append({"ok": True, "sql": " ".join(sql.split())[:160]})
    except Exception as e:  # keep going; report every failure in the evidence file
        log.append({"ok": False, "sql": " ".join(sql.split())[:160], "error": str(e).splitlines()[0][:200]})
```

## Cell 3

```markdown
%md ## Column comments on the published tables
```

## Cell 4

```python
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
        txt = txt.replace("'", "\\'")
        kind = "TABLE" if t.startswith("risk") else "MATERIALIZED VIEW"
        run(f"COMMENT ON COLUMN {FQ}.{t}.{c} IS '{txt}'") if kind == "TABLE" else run(f"ALTER MATERIALIZED VIEW {FQ}.{t} ALTER COLUMN {c} COMMENT '{txt}'")
```

## Cell 5

```markdown
%md ## Governance tags
```

## Cell 6

```python
# Tag keys/values respect the metastore's governed tag policies (domain, layer, sensitivity, contains_pii);
# owning_team / data_product / product_stage are free-form keys.
tables = spark.sql(f"""SELECT table_name, table_type FROM {CATALOG}.information_schema.tables
                       WHERE table_schema = '{SCHEMA}' AND table_name NOT LIKE '\\_\\_%' AND table_name NOT LIKE 'event_log%'""").collect()
for r in tables:
    name = r.table_name
    prefix = name.split("_")[0]
    layer = prefix if prefix in ("bronze", "silver", "gold") else "gold"
    stage = prefix if prefix in ("bronze", "silver", "gold") else ("ml" if name in ("demand_forecast", "forecast_backtest") else "serving")
    kw = {"MATERIALIZED_VIEW": "MATERIALIZED VIEW", "STREAMING_TABLE": "STREAMING TABLE", "VIEW": "VIEW", "METRIC_VIEW": "VIEW"}.get(r.table_type, "TABLE")
    run(f"ALTER {kw} {FQ}.{name} SET TAGS ('domain' = 'supply_chain', 'layer' = '{layer}', 'sensitivity' = 'internal', 'contains_pii' = 'false', "
        f"'owning_team' = 'replenishment_planning', 'solution' = 'inventory_risk_radar', 'product_stage' = '{stage}')")
```

## Cell 7

```markdown
%md ## Enforced row-level security + column masking (UC ROW FILTER and MASK)
`planner_risk_queue` is the planner-facing table. Unity Catalog enforces, on every query from any tool:
* **Row filter** `region_row_filter(region)`: a principal listed in `planner_region_access` sees only the regions mapped to
  them (store-level / regional planners); otherwise admins and the `inventory_planners_all` group see all regions and regional
  groups `planners_<region>` see their region; everyone else sees nothing.
* **Column mask** `mask_revenue(revenue_at_risk)`: revenue exposure is visible only to principals mapped with
  `can_see_financials = true`, or (if unmapped) to admins and `supply_chain_finance`.
```

## Cell 8

```python
run(f"""CREATE TABLE IF NOT EXISTS {FQ}.planner_region_access (
  principal STRING NOT NULL COMMENT 'User email or service principal application id',
  region STRING NOT NULL COMMENT 'Region the principal may see',
  can_see_financials BOOLEAN NOT NULL COMMENT 'Whether revenue-at-risk is unmasked for this principal')
COMMENT 'Entitlements for the planner risk queue: which regions each planner may see and whether financials are unmasked.'""")
run(f"""
CREATE OR REPLACE FUNCTION {FQ}.region_row_filter(row_region STRING)
RETURNS BOOLEAN
COMMENT 'Row filter for planner_risk_queue: mapped principals see only their mapped regions; otherwise admins/chain planners see all and regional groups see their region.'
RETURN CASE
  WHEN EXISTS (SELECT 1 FROM {FQ}.planner_region_access a WHERE a.principal = current_user())
    THEN EXISTS (SELECT 1 FROM {FQ}.planner_region_access a WHERE a.principal = current_user() AND a.region = row_region)
  ELSE is_member('admins') OR is_account_group_member('inventory_planners_all')
       OR is_account_group_member(concat('planners_', lower(replace(row_region, ' ', '_'))))
END
""")
run(f"""
CREATE OR REPLACE FUNCTION {FQ}.mask_revenue(revenue_at_risk DOUBLE)
RETURNS DOUBLE
COMMENT 'Column mask: revenue at risk visible only to principals entitled to financials.'
RETURN CASE  -- parameter names must not collide with mapping-table columns (they would shadow the argument)
  WHEN EXISTS (SELECT 1 FROM {FQ}.planner_region_access a WHERE a.principal = current_user())
    THEN CASE WHEN EXISTS (SELECT 1 FROM {FQ}.planner_region_access a WHERE a.principal = current_user() AND a.can_see_financials)
              THEN revenue_at_risk END
  WHEN is_member('admins') OR is_account_group_member('supply_chain_finance') THEN revenue_at_risk
END
""")
run(f"DROP TABLE IF EXISTS {FQ}.planner_risk_queue")  # recreated each run from the latest scores; policies re-applied below
run(f"""
CREATE TABLE {FQ}.planner_risk_queue
COMMENT 'Planner-facing risk queue with an enforced Unity Catalog row filter (region) and column mask (revenue at risk). Grant this, not the base table.'
AS SELECT recommendation_id, as_of_date, risk_rank, risk_score, risk_tier, store_id, store_name, region, sku_id, sku_name, category,
          supplier_name, on_hand_units, inbound_units_in_window, forecast_demand_window, lead_time_window_days, days_of_cover,
          projected_stockout_in_days, stockout_probability, CAST(revenue_at_risk AS DOUBLE) AS revenue_at_risk,
          primary_driver, driver_details, recommended_action, recommended_qty, action_source_id, planner_explanation
FROM {FQ}.risk_recommendations
""")
run(f"ALTER TABLE {FQ}.planner_risk_queue SET ROW FILTER {FQ}.region_row_filter ON (region)")
run(f"ALTER TABLE {FQ}.planner_risk_queue ALTER COLUMN revenue_at_risk SET MASK {FQ}.mask_revenue")
run(f"ALTER TABLE {FQ}.planner_risk_queue SET TAGS ('domain' = 'supply_chain', 'layer' = 'gold', 'governance' = 'row_filter_and_mask', 'solution' = 'inventory_risk_radar')")
run(f"DROP VIEW IF EXISTS {FQ}.v_planner_risk_queue")      # superseded by the enforced table policies
run(f"DROP FUNCTION IF EXISTS {FQ}.can_see_region")
run(f"DROP FUNCTION IF EXISTS {FQ}.can_see_financials")
```

## Cell 9

```markdown
%md ### Enforcement test
Map the identity running this job to one region without financial access, query, then remove the mapping.
```

## Cell 10

```python
me = spark.sql("SELECT current_user()").first()[0]
def queue_view():
    return spark.sql(f"""SELECT region, count(*) AS rows_visible, count(revenue_at_risk) AS revenue_values_visible
                         FROM {FQ}.planner_risk_queue GROUP BY region ORDER BY region""").toPandas()
enforcement = {"principal": me}
enforcement["before_mapping"] = queue_view().to_dict(orient="records")
spark.sql(f"DELETE FROM {FQ}.planner_region_access WHERE principal = '{me}'")
spark.sql(f"INSERT INTO {FQ}.planner_region_access VALUES ('{me}', 'Valley', false)")
scoped = queue_view()
enforcement["mapped_to_valley_no_financials"] = scoped.to_dict(orient="records")
spark.sql(f"DELETE FROM {FQ}.planner_region_access WHERE principal = '{me}'")
enforcement["after_mapping_removed"] = queue_view().to_dict(orient="records")
enforcement["row_filter_enforced"] = list(scoped.region) == ["Valley"]
enforcement["mask_enforced"] = int(scoped.revenue_values_visible.sum()) == 0
d = spark.sql(f"DESCRIBE TABLE EXTENDED {FQ}.planner_risk_queue").toPandas()
enforcement["describe_row_filter_and_mask"] = d[d.col_name.str.contains("Row Filter|Column Mask|revenue_at_risk", case=False, regex=True)].to_dict(orient="records")
print(json.dumps(enforcement, indent=2, default=str))
assert enforcement["row_filter_enforced"] and enforcement["mask_enforced"], "row filter / mask not enforced"
```

**Output**

```text
{
  "principal": "adarsh.nandan@databricks.com",
  "before_mapping": [
    {
      "region": "Coastal",
      "rows_visible": 3998,
      "revenue_values_visible": 3998
    },
    {
      "region": "Lakeshore",
      "rows_visible": 3999,
      "revenue_values_visible": 3999
    },
    {
      "region": "Metro North",
      "rows_visible": 3999,
      "revenue_values_visible": 3999
    },
    {
      "region": "Metro South",
      "rows_visible": 4000,
      "revenue_values_visible": 4000
    },
    {
      "region": "Valley",
      "rows_visible": 4000,
      "revenue_values_visible": 4000
    }
  ],
  "mapped_to_valley_no_financials": [
    {
      "region": "Valley",
      "rows_visible": 4000,
      "revenue_values_visible": 0
    }
  ],
  "after_mapping_removed": [
    {
      "region": "Coastal",
      "rows_visible": 3998,
      "revenue_values_visible": 3998
    },
    {
      "region": "Lakeshore",
      "rows_visible": 3999,
      "revenue_values_visible": 3999
    },
    {
      "region": "Metro North",
      "rows_visible": 3999,
      "revenue_values_visible": 3999
    },
    {
      "region": "Metro South",
      "rows_visible": 4000,
      "revenue_values_visible": 4000
    },
    {
      "region": "Valley",
      "rows_visible": 4000,
      "revenue_values_visible": 4000
    }
  ],
  "row_filter_enforced": true,
  "mask_enforced": true,
  "describe_row_filter_and_mask": [
    {
      "col_name": "revenue_at_risk",
      "data_type": "double",
      "comment": null
    },
    {
      "col_name": "Row Filter",
      "data_type": "`serverless_stable_3vku19_catalog`.`inventory_risk`.`region_row_filter` ON (region)",
      "comment": ""
    },
    {
      "col_name": "# Column Masks",
      "data_type": "",
      "comment": ""
    },
    {
      "col_name": "revenue_at_risk",
      "data_type": "`serverless_stable_3vku19_catalog`.`inventory_risk`.`mask_revenue`",
      "comment": ""
    }
  ]
}
```

## Cell 11

```markdown
%md ## Least-privilege grants
```

## Cell 12

```python
run(f"GRANT USE SCHEMA ON SCHEMA {FQ} TO `account users`")
run(f"GRANT SELECT ON TABLE {FQ}.planner_risk_queue TO `account users`")
# Planner app service principal: reads published tables for drill-down and runs Genie on the governed schema
if APP_SP:
    run(f"GRANT USE CATALOG ON CATALOG {CATALOG} TO `{APP_SP}`")
    run(f"GRANT USE SCHEMA ON SCHEMA {FQ} TO `{APP_SP}`")
    run(f"GRANT SELECT ON SCHEMA {FQ} TO `{APP_SP}`")
```

## Cell 13

```python
import pandas as pd
df = pd.DataFrame(log)
print(df.ok.value_counts().to_dict())
print(df[~df.ok].to_string() if (~df.ok).any() else "all governance statements succeeded")
tags = spark.sql(f"SELECT table_name, tag_name, tag_value FROM {CATALOG}.information_schema.table_tags WHERE schema_name = '{SCHEMA}' AND tag_name IN ('layer','product_stage') ORDER BY 1,2").toPandas()
print(tags.pivot(index="table_name", columns="tag_name", values="tag_value").to_string())
masked = spark.sql(f"SELECT count(*) AS visible_rows, count(revenue_at_risk) AS rows_with_revenue_visible FROM {FQ}.planner_risk_queue").toPandas()
print(masked.to_string(index=False))
with open(f"{EVIDENCE}/06_governance.json", "w") as fh:
    json.dump({"statements": log, "tags": tags.to_dict(orient="records"), "queue_check_as_job_identity": masked.to_dict(orient="records"), "enforcement_test": enforcement}, fh, indent=2, default=str)
```

**Output**

```text
{True: 81}
all governance statements succeeded
tag_name                          layer product_stage
table_name                                           
bronze_holidays                  bronze        bronze
bronze_inventory_snapshots       bronze        bronze
bronze_po_events                 bronze        bronze
bronze_pos_sales                 bronze        bronze
bronze_products                  bronze        bronze
bronze_promotions                bronze        bronze
bronze_stores                    bronze        bronze
bronze_suppliers                 bronze        bronze
demand_forecast                    gold            ml
forecast_backtest                  gold            ml
gold_current_inventory_position    gold          gold
gold_daily_store_sku_sales         gold          gold
gold_inbound_po_pipeline           gold          gold
gold_po_lines                      gold          gold
gold_promo_store_sku_daily         gold          gold
gold_supplier_lead_time_stats      gold          gold
model_monitoring                   gold       serving
mv_alert_backtest                  gold       serving
mv_forecast_accuracy               gold       serving
mv_inventory_risk                  gold       serving
mv_stockout_history                gold       serving
planner_action_history             gold       serving
planner_note_history               gold       serving
planner_region_access              gold       serving
planner_risk_queue                 gold           NaN
planner_watchlists                 gold       serving
risk_backtest                      gold       serving
risk_explanation_eval              gold       serving
risk_explanations                  gold       serving
risk_recommendations               gold       serving
risk_recommendations_online        gold       serving
risk_scores                        gold       serving
silver_holidays                  silver        silver
silver_inventory_snapshots       silver        silver
silver_po_events                 silver        silver
silver_pos_sales                 silver        silver
silver_products                  silver        silver
silver_promotions                silver        silver
silver_stores                    silver        silver
silver_suppliers                 silver        silver
 visible_rows  rows_with_revenue_visible
        19996                      19996
```
