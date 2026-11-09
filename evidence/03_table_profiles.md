# Table profiles across bronze / silver / gold / ML / serving

_Captured 2026-11-09 13:27 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

### Row counts by layer

```sql
SELECT 'bronze_pos_sales' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.bronze_pos_sales
UNION ALL SELECT 'silver_pos_sales' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.silver_pos_sales
UNION ALL SELECT 'bronze_inventory_snapshots' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.bronze_inventory_snapshots
UNION ALL SELECT 'silver_inventory_snapshots' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.silver_inventory_snapshots
UNION ALL SELECT 'bronze_po_events' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.bronze_po_events
UNION ALL SELECT 'silver_po_events' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.silver_po_events
UNION ALL SELECT 'gold_daily_store_sku_sales' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.gold_daily_store_sku_sales
UNION ALL SELECT 'gold_po_lines' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.gold_po_lines
UNION ALL SELECT 'gold_inbound_po_pipeline' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.gold_inbound_po_pipeline
UNION ALL SELECT 'gold_supplier_lead_time_stats' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.gold_supplier_lead_time_stats
UNION ALL SELECT 'gold_current_inventory_position' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.gold_current_inventory_position
UNION ALL SELECT 'gold_promo_store_sku_daily' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.gold_promo_store_sku_daily
UNION ALL SELECT 'forecast_backtest' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.forecast_backtest
UNION ALL SELECT 'demand_forecast' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.demand_forecast
UNION ALL SELECT 'risk_scores' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.risk_scores
UNION ALL SELECT 'risk_backtest' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.risk_backtest
UNION ALL SELECT 'risk_explanations' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.risk_explanations
UNION ALL SELECT 'risk_recommendations' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations
UNION ALL SELECT 'planner_action_history' AS table_name, count(*) AS row_count FROM serverless_stable_3vku19_catalog.inventory_risk.planner_action_history
```

| table_name | row_count |
|---|---|
| bronze_pos_sales | 12688631 |
| silver_pos_sales | 12666996 |
| bronze_inventory_snapshots | 14600000 |
| silver_inventory_snapshots | 14597084 |
| bronze_po_events | 4225358 |
| silver_po_events | 4224712 |
| gold_daily_store_sku_sales | 14597084 |
| gold_po_lines | 2119307 |
| gold_inbound_po_pipeline | 14543 |
| gold_supplier_lead_time_stats | 24 |
| gold_current_inventory_position | 19996 |
| gold_promo_store_sku_daily | 738010 |
| forecast_backtest | 559762 |
| demand_forecast | 559888 |
| risk_scores | 19996 |
| risk_backtest | 19997 |
| risk_explanations | 400 |
| risk_recommendations | 19996 |
| planner_action_history | 3 |

### Sample: gold_daily_store_sku_sales

```sql
SELECT * FROM serverless_stable_3vku19_catalog.inventory_risk.gold_daily_store_sku_sales WHERE store_id = 'S001' AND sku_id = 'P00043' ORDER BY sale_date DESC LIMIT 8
```

| sale_date | store_id | region | sku_id | category | units_sold | net_sales | unit_price | on_promo | discount_pct | eod_on_hand_units | is_stockout | days_to_next_holiday |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 57 | 308.94 | 5.42 | false | 0.0 | 170 | false | 20 |
| 2026-11-05 | S001 | Metro North | P00043 | Fresh Produce | 36 | 195.12 | 5.42 | false | 0.0 | 232 | false | 21 |
| 2026-11-04 | S001 | Metro North | P00043 | Fresh Produce | 26 | 140.92 | 5.42 | false | 0.0 | 275 | false | 22 |
| 2026-11-03 | S001 | Metro North | P00043 | Fresh Produce | 35 | 189.70 | 5.42 | false | 0.0 | 93 | false | 23 |
| 2026-11-02 | S001 | Metro North | P00043 | Fresh Produce | 96 | 520.32 | 5.42 | false | 0.0 | 130 | false | 24 |
| 2026-11-01 | S001 | Metro North | P00043 | Fresh Produce | 38 | 205.96 | 5.42 | false | 0.0 | 229 | false | 25 |
| 2026-10-31 | S001 | Metro North | P00043 | Fresh Produce | 54 | 292.68 | 5.42 | false | 0.0 | 88 | false | 26 |
| 2026-10-30 | S001 | Metro North | P00043 | Fresh Produce | 38 | 205.96 | 5.42 | false | 0.0 | 144 | false | 27 |

### Sample: gold_supplier_lead_time_stats (worst on-time first)

```sql
SELECT * FROM serverless_stable_3vku19_catalog.inventory_risk.gold_supplier_lead_time_stats ORDER BY on_time_rate_last_30d LIMIT 8
```

| supplier_id | supplier_name | primary_category | contract_lead_time_days | received_lines | avg_actual_lead_time_days | p90_actual_lead_time_days | on_time_rate | on_time_rate_last_30d | avg_days_late_when_late_last_30d | avg_days_late_last_30d | open_lines | overdue_open_lines |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V004 | Summit Dairy Wholesale | Dairy & Eggs | 2 | 127258 | 2.6 | 5 | 0.8337 | 0.5816 | 5.93 | 2.48 | 871 | 517 |
| V007 | Heartland Bakery Wholesale | Bakery | 1 | 115659 | 1.66 | 4 | 0.7253 | 0.7261 | 2.38 | 0.65 | 280 | 51 |
| V024 | Riverbend Personal Wholesale | Personal Care | 10 | 26314 | 10.71 | 13 | 0.7551 | 0.7352 | 2.92 | 0.77 | 394 | 25 |
| V021 | Heartland Household Distributors | Household | 10 | 33718 | 10.53 | 12 | 0.7777 | 0.7692 | 2.37 | 0.55 | 531 | 8 |
| V006 | Keystone Dairy Foods | Dairy & Eggs | 3 | 86809 | 3.69 | 6 | 0.7911 | 0.7708 | 3.25 | 0.74 | 437 | 57 |
| V017 | Northern Beverages Wholesale | Beverages | 10 | 59331 | 10.5 | 12 | 0.7874 | 0.785 | 2.34 | 0.5 | 682 | 13 |
| V003 | Riverbend Fresh Supply Co. | Fresh Produce | 2 | 190903 | 2.94 | 7 | 0.8077 | 0.8102 | 4.87 | 0.92 | 758 | 188 |
| V011 | Heartland Meat Wholesale | Meat & Seafood | 3 | 29346 | 3.55 | 6 | 0.8134 | 0.8283 | 3.09 | 0.53 | 140 | 11 |

### Sample: demand_forecast

```sql
SELECT * FROM serverless_stable_3vku19_catalog.inventory_risk.demand_forecast WHERE store_id = 'S001' AND sku_id = 'P00043' ORDER BY horizon LIMIT 10
```

| forecast_origin | store_id | region | sku_id | category | target_date | horizon | on_promo | discount_pct | days_to_next_holiday | forecast_units | baseline_units | model_name | model_version | scored_at |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-07 | 1 | 0 | 0.0 | 19 | 52.252 | 48.667 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-08 | 2 | 0 | 0.0 | 18 | 47.89 | 40.75 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-09 | 3 | 0 | 0.0 | 17 | 39.541 | 64.25 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-10 | 4 | 0 | 0.0 | 16 | 36.046 | 33.25 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-11 | 5 | 0 | 0.0 | 15 | 37.186 | 38.75 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-12 | 6 | 0 | 0.0 | 14 | 41.352 | 37.75 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-13 | 7 | 0 | 0.0 | 13 | 46.447 | 60.0 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-14 | 8 | 0 | 0.0 | 12 | 52.993 | 48.667 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-15 | 9 | 0 | 0.0 | 11 | 47.861 | 40.75 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |
| 2026-11-06 | S001 | Metro North | P00043 | Fresh Produce | 2026-11-16 | 10 | 0 | 0.0 | 10 | 39.778 | 64.25 | serverless_stable_3vku19_catalog.inventory_risk.demand_forecast | 2 | 2026-11-09T13:25:49.537Z |

### Unity Catalog tags on published objects

```sql
SELECT table_name, collect_list(concat(tag_name, '=', tag_value)) AS tags
FROM serverless_stable_3vku19_catalog.information_schema.table_tags WHERE schema_name = 'inventory_risk' AND table_name IN ('risk_recommendations','planner_risk_queue','mv_inventory_risk','gold_daily_store_sku_sales','demand_forecast')
GROUP BY table_name ORDER BY table_name
```

| table_name | tags |
|---|---|
| demand_forecast | ["owning_team=replenishment_planning","product_stage=ml","contains_pii=false","sensitivity=internal","domain=supply_chain","layer=gold","solution=inventory_risk_radar"] |
| gold_daily_store_sku_sales | ["owning_team=replenishment_planning","product_stage=gold","solution=inventory_risk_radar","contains_pii=false","layer=gold","sensitivity=internal","domain=supply_chain"] |
| mv_inventory_risk | ["domain=supply_chain","layer=gold","product_stage=semantic","solution=inventory_risk_radar"] |
| planner_risk_queue | ["solution=inventory_risk_radar","domain=supply_chain","layer=gold","governance=row_filter_and_mask"] |
| risk_recommendations | ["product_stage=serving","contains_pii=false","sensitivity=internal","domain=supply_chain","owning_team=replenishment_planning","layer=gold","solution=inventory_risk_radar"] |
