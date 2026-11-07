# Task `metric_views` - SUCCESS
- Task run id: `829500589129562`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/metrics/create_metric_views`
- Duration: 26 s

## Cell 1

```markdown
%md
# 07 - Unity Catalog metric views: one governed definition of every success KPI
The same definitions back the AI/BI dashboard, Genie and the readout: forecast error (WAPE, bias),
stockout rate, inventory cover / excess, revenue at risk, and alert precision/recall from the backtest.
```

## Cell 2

```python
dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"

VIEWS = {
"mv_inventory_risk": f"""
version: 1.1
comment: "Current stockout-risk queue KPIs per store/SKU (as-of date). Use for alert counts, revenue at risk, cover and excess."
source: {FQ}.risk_recommendations
dimensions:
  - name: as_of_date
    expr: as_of_date
  - name: region
    expr: region
  - name: store_name
    expr: store_name
  - name: category
    expr: category
  - name: sku_name
    expr: sku_name
  - name: supplier_name
    expr: supplier_name
  - name: risk_tier
    expr: risk_tier
    comment: "Critical >= 70, High >= 45, Medium >= 25, Low"
  - name: primary_driver
    expr: primary_driver
  - name: recommended_action
    expr: recommended_action
measures:
  - name: store_skus
    expr: COUNT(1)
  - name: critical_alerts
    expr: COUNT(1) FILTER (WHERE risk_tier = 'Critical')
  - name: critical_high_alerts
    expr: COUNT(1) FILTER (WHERE risk_tier IN ('Critical', 'High'))
    comment: "Alerts planners are asked to review today"
  - name: revenue_at_risk
    expr: SUM(revenue_at_risk)
    comment: "Expected lost sales (USD) within each item's replenishment window"
  - name: revenue_at_risk_critical_high
    expr: SUM(revenue_at_risk) FILTER (WHERE risk_tier IN ('Critical', 'High'))
  - name: avg_stockout_probability
    expr: AVG(stockout_probability)
  - name: projected_out_within_3_days
    expr: COUNT(1) FILTER (WHERE projected_stockout_in_days <= 3)
  - name: median_days_of_cover
    expr: PERCENTILE_APPROX(days_of_cover, 0.5)
    comment: "Inventory cover: on hand / next-7-day average forecast demand"
  - name: excess_store_skus
    expr: COUNT(1) FILTER (WHERE days_of_cover > 45)
    comment: "Store/SKUs with more than 45 days of cover (excess inventory)"
  - name: excess_rate
    expr: COUNT(1) FILTER (WHERE days_of_cover > 45) / COUNT(1)
""",
"mv_forecast_accuracy": f"""
version: 1.1
comment: "Forecast error on the 28-day holdout: champion model vs. seasonal-naive baseline. Stockout days excluded (censored demand)."
source: {FQ}.forecast_backtest
filter: NOT is_stockout
dimensions:
  - name: category
    expr: category
  - name: region
    expr: region
  - name: horizon_days
    expr: horizon
  - name: horizon_week
    expr: CONCAT('Week ', CAST(CEIL(horizon / 7) AS STRING))
  - name: on_promo
    expr: CASE WHEN on_promo = 1 THEN 'Promotion day' ELSE 'Regular day' END
  - name: target_date
    expr: target_date
measures:
  - name: actual_units
    expr: SUM(units_sold)
  - name: model_wape
    expr: SUM(ABS(units_sold - lgbm_pred)) / SUM(units_sold)
    comment: "Weighted absolute percentage error of the champion model (lower is better)"
  - name: baseline_wape
    expr: SUM(ABS(units_sold - baseline_pred)) / SUM(units_sold)
  - name: wape_improvement_pct
    expr: (SUM(ABS(units_sold - baseline_pred)) - SUM(ABS(units_sold - lgbm_pred))) / SUM(ABS(units_sold - baseline_pred)) * 100
  - name: model_bias
    expr: (SUM(lgbm_pred) - SUM(units_sold)) / SUM(units_sold)
  - name: baseline_bias
    expr: (SUM(baseline_pred) - SUM(units_sold)) / SUM(units_sold)
""",
"mv_stockout_history": f"""
version: 1.1
comment: "Historical on-shelf availability: stockout rate = share of store/SKU/days ending with zero on hand."
source: {FQ}.gold_daily_store_sku_sales
dimensions:
  - name: sale_date
    expr: sale_date
  - name: sale_month
    expr: DATE_TRUNC('MONTH', sale_date)
  - name: sale_week
    expr: DATE_TRUNC('WEEK', sale_date)
  - name: region
    expr: region
  - name: category
    expr: category
  - name: on_promo
    expr: on_promo
measures:
  - name: store_sku_days
    expr: COUNT(1)
  - name: stockout_days
    expr: COUNT(1) FILTER (WHERE is_stockout)
  - name: stockout_rate
    expr: COUNT(1) FILTER (WHERE is_stockout) / COUNT(1)
  - name: units_sold
    expr: SUM(units_sold)
  - name: net_sales
    expr: SUM(net_sales)
""",
"mv_alert_backtest": f"""
version: 1.1
comment: "Alert quality on a 4-week-old backtest (items that still had stock at the origin; empty shelves are known, not predicted): did items flagged Critical/High actually stock out within their replenishment window? Compared with today's rule of thumb (days of cover < contract lead time)."
source: {FQ}.risk_backtest
filter: on_hand_units > 0
dimensions:
  - name: region
    expr: region
  - name: category
    expr: category
  - name: risk_tier
    expr: risk_tier
  - name: primary_driver
    expr: primary_driver
measures:
  - name: radar_alerts
    expr: COUNT(1) FILTER (WHERE radar_alert)
  - name: radar_alert_precision
    expr: COUNT(1) FILTER (WHERE radar_alert AND actual_stockout_in_window) / COUNT(1) FILTER (WHERE radar_alert)
    comment: "Share of radar alerts (Critical/High) that were real stockouts"
  - name: radar_alert_recall
    expr: COUNT(1) FILTER (WHERE radar_alert AND actual_stockout_in_window) / COUNT(1) FILTER (WHERE actual_stockout_in_window)
  - name: rule_alerts
    expr: COUNT(1) FILTER (WHERE rule_of_thumb_alert)
  - name: rule_alert_precision
    expr: COUNT(1) FILTER (WHERE rule_of_thumb_alert AND actual_stockout_in_window) / COUNT(1) FILTER (WHERE rule_of_thumb_alert)
  - name: rule_alert_recall
    expr: COUNT(1) FILTER (WHERE rule_of_thumb_alert AND actual_stockout_in_window) / COUNT(1) FILTER (WHERE actual_stockout_in_window)
  - name: actual_stockouts
    expr: COUNT(1) FILTER (WHERE actual_stockout_in_window)
""",
}
```

## Cell 3

```python
import json
results = {}
for name, yml in VIEWS.items():
    spark.sql(f"CREATE OR REPLACE VIEW {FQ}.{name} WITH METRICS LANGUAGE YAML AS $$\n{yml}\n$$")
    spark.sql(f"ALTER VIEW {FQ}.{name} SET TAGS ('domain' = 'supply_chain', 'layer' = 'gold', 'product_stage' = 'semantic', 'solution' = 'inventory_risk_radar')")
    print("created", name)

checks = {
    "mv_inventory_risk": "SELECT region, MEASURE(critical_high_alerts) AS critical_high_alerts, ROUND(MEASURE(revenue_at_risk_critical_high), 0) AS revenue_at_risk_critical_high, MEASURE(median_days_of_cover) AS median_days_of_cover, ROUND(MEASURE(excess_rate), 4) AS excess_rate FROM {v} GROUP BY ALL ORDER BY 2 DESC",
    "mv_forecast_accuracy": "SELECT on_promo, ROUND(MEASURE(model_wape), 4) AS model_wape, ROUND(MEASURE(baseline_wape), 4) AS baseline_wape, ROUND(MEASURE(wape_improvement_pct), 1) AS wape_improvement_pct FROM {v} GROUP BY ALL",
    "mv_stockout_history": "SELECT sale_month, ROUND(MEASURE(stockout_rate), 4) AS stockout_rate FROM {v} WHERE sale_month >= '2026-06-01' GROUP BY ALL ORDER BY 1",
    "mv_alert_backtest": "SELECT MEASURE(radar_alerts) AS radar_alerts, ROUND(MEASURE(radar_alert_precision), 4) AS radar_precision, ROUND(MEASURE(radar_alert_recall), 4) AS radar_recall, MEASURE(rule_alerts) AS rule_alerts, ROUND(MEASURE(rule_alert_precision), 4) AS rule_precision, ROUND(MEASURE(rule_alert_recall), 4) AS rule_recall FROM {v}",
}
for name, q in checks.items():
    pdf = spark.sql(q.format(v=f"{FQ}.{name}")).toPandas()
    print(f"\n== {name}\n{pdf.to_string(index=False)}")
    results[name] = pdf.to_dict(orient="records")
with open(f"{EVIDENCE}/07_metric_views.json", "w") as fh:
    json.dump(results, fh, indent=2, default=str)
```

**Output**

```text
created mv_inventory_risk
created mv_forecast_accuracy
created mv_stockout_history
created mv_alert_backtest

== mv_inventory_risk
     region  critical_high_alerts  revenue_at_risk_critical_high  median_days_of_cover  excess_rate
     Valley                   506                        15128.0                   6.1       0.0015
  Lakeshore                   495                        12337.0                   6.0       0.0013
    Coastal                   474                         9498.0                   6.5       0.0033
Metro North                   438                         8423.0                   6.4       0.0030
Metro South                   425                         7633.0                   6.4       0.0023

== mv_forecast_accuracy
     on_promo  model_wape  baseline_wape  wape_improvement_pct
Promotion day      0.4011         0.5487                  26.9
  Regular day      0.4583         0.5278                  13.2

== mv_stockout_history
sale_month  stockout_rate
2026-06-01         0.0419
2026-07-01         0.0422
2026-08-01         0.0385
2026-09-01         0.0405
2026-10-01         0.0395
2026-11-01         0.0588

== mv_alert_backtest
 radar_alerts  radar_precision  radar_recall  rule_alerts  rule_precision  rule_recall
         1172           0.6246        0.3834         5372          0.2042       0.5746
```
