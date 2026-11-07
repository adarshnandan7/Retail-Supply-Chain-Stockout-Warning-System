# Lakeflow pipeline: data quality and flow progress

_Captured 2026-11-07 14:12 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

Pipeline id `b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1`.

### Expectation results (latest update)

```sql
SELECT origin.flow_name AS flow, e.name AS expectation, sum(e.passed_records) AS passed, sum(e.failed_records) AS failed
FROM event_log('b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1') l
LATERAL VIEW explode(from_json(l.details:flow_progress.data_quality.expectations,
  'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) x AS e
WHERE l.event_type = 'flow_progress' AND l.details:flow_progress.data_quality IS NOT NULL
  AND l.origin.update_id = (SELECT origin.update_id FROM event_log('b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1)
GROUP BY ALL ORDER BY flow, expectation
```

| flow | expectation | passed | failed |
|---|---|---|---|
| serverless_stable_3vku19_catalog.inventory_risk.silver_inventory_snapshots | keys_present | 14600000 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_inventory_snapshots | non_negative_on_hand | 14597084 | 2916 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_po_events | created_has_qty | 4224712 | 646 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_po_events | po_line_present | 4225358 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_po_events | received_has_qty | 4225358 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_pos_sales | non_negative_units | 12669470 | 6409 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_pos_sales | price_positive | 12675879 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_pos_sales | sku_present | 12673400 | 2479 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_pos_sales | store_present | 12675879 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_products | unique_sku | 400 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_promotions | valid_window | 4433 | 0 |
| serverless_stable_3vku19_catalog.inventory_risk.silver_suppliers | lead_time_positive | 24 | 0 |

### Flow completion (latest update)

```sql
SELECT origin.flow_name AS flow, details:flow_progress.status AS status, details:flow_progress.metrics.num_output_rows AS output_rows, timestamp
FROM event_log('b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1')
WHERE event_type = 'flow_progress' AND details:flow_progress.status IN ('COMPLETED', 'FAILED')
  AND origin.update_id = (SELECT origin.update_id FROM event_log('b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1)
ORDER BY timestamp
```

| flow | status | output_rows | timestamp |
|---|---|---|---|
| serverless_stable_3vku19_catalog.inventory_risk.bronze_products | COMPLETED |  | 2026-11-07T13:56:01.809Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_stores | COMPLETED |  | 2026-11-07T13:56:01.817Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_holidays | COMPLETED |  | 2026-11-07T13:56:01.824Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_promotions | COMPLETED |  | 2026-11-07T13:56:01.860Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_suppliers | COMPLETED |  | 2026-11-07T13:56:02.313Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_products | COMPLETED | 400 | 2026-11-07T13:56:12.278Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_stores | COMPLETED | 50 | 2026-11-07T13:56:12.355Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_holidays | COMPLETED | 16 | 2026-11-07T13:56:12.406Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_promotions | COMPLETED | 4433 | 2026-11-07T13:56:14.108Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_suppliers | COMPLETED | 24 | 2026-11-07T13:56:18.592Z |
| serverless_stable_3vku19_catalog.inventory_risk.gold_promo_store_sku_daily | COMPLETED | 738010 | 2026-11-07T13:56:21.528Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_pos_sales | COMPLETED |  | 2026-11-07T13:56:26.940Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_po_events | COMPLETED |  | 2026-11-07T13:56:26.948Z |
| serverless_stable_3vku19_catalog.inventory_risk.bronze_inventory_snapshots | COMPLETED |  | 2026-11-07T13:56:37.681Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_po_events | COMPLETED |  | 2026-11-07T13:56:37.796Z |
| serverless_stable_3vku19_catalog.inventory_risk.gold_po_lines | COMPLETED | 2119307 | 2026-11-07T13:56:47.560Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_inventory_snapshots | COMPLETED |  | 2026-11-07T13:56:53.405Z |
| serverless_stable_3vku19_catalog.inventory_risk.gold_supplier_lead_time_stats | COMPLETED | 24 | 2026-11-07T13:56:53.426Z |
| serverless_stable_3vku19_catalog.inventory_risk.gold_inbound_po_pipeline | COMPLETED | 14543 | 2026-11-07T13:56:57.816Z |
| serverless_stable_3vku19_catalog.inventory_risk.silver_pos_sales | COMPLETED |  | 2026-11-07T13:57:17.224Z |
| serverless_stable_3vku19_catalog.inventory_risk.gold_daily_store_sku_sales | COMPLETED | 14597084 | 2026-11-07T13:57:34.468Z |
| serverless_stable_3vku19_catalog.inventory_risk.gold_current_inventory_position | COMPLETED | 19996 | 2026-11-07T13:57:38.434Z |
