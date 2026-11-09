# Demand forecast: baseline vs champion model

_Captured 2026-11-09 13:27 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- MLflow experiment: `/Users/adarsh.nandan@databricks.com/inventory-risk-radar-demand-forecast`
- Baseline run: `40608202e50c465c8dda082f4fd70e4e` | LightGBM run: `c48c1a77a54a487fa5997fec169de17c`
- Registered model: `serverless_stable_3vku19_catalog.inventory_risk.demand_forecast` version **2** with alias **@champion** (status READY)
- Holdout origin 2026-10-09; 534,339 store/SKU/day rows scored (stockout days excluded); 1,886,854 training rows

| Metric | Seasonal naive (baseline) | LightGBM (champion) |
|---|---|---|
| holdout_wape | 0.5291 | 0.4548 |
| holdout_bias | 0.0576 | 0.0161 |
| holdout_mae | 3.2539 | 2.7969 |
| holdout_wape_promo_days | 0.5487 | 0.4012 |
| holdout_wape_non_promo_days | 0.5278 | 0.4585 |

**WAPE reduction vs baseline: 14.0%**

### By category

| Category | Baseline WAPE | Model WAPE | Reduction % |
|---|---|---|---|
| Bakery | 0.490 | 0.426 | 13.1 |
| Beverages | 0.575 | 0.462 | 19.7 |
| Dairy & Eggs | 0.491 | 0.431 | 12.1 |
| Fresh Produce | 0.478 | 0.411 | 14.1 |
| Frozen | 0.552 | 0.480 | 13.1 |
| Household | 0.691 | 0.621 | 10.1 |
| Meat & Seafood | 0.584 | 0.495 | 15.3 |
| Pantry & Baking | 0.566 | 0.497 | 12.1 |
| Personal Care | 0.795 | 0.728 | 8.4 |
| Snacks | 0.536 | 0.458 | 14.6 |

### Top features (gain)

| Feature | Gain |
|---|---|
| r28 | 43813720 |
| r7 | 2094676 |
| discount_pct | 1527596 |
| target_dow | 896861 |
| sn4_dow | 669949 |
| r28_std | 336044 |
| days_to_next_holiday | 276393 |
| category_code | 187430 |
| next_holiday_code | 158617 |
| hol_ratio_sku | 89970 |

### Metric view check: WAPE promo vs regular days

```sql
SELECT on_promo, ROUND(MEASURE(model_wape), 4) AS model_wape, ROUND(MEASURE(baseline_wape), 4) AS baseline_wape, ROUND(MEASURE(wape_improvement_pct), 1) AS improvement_pct FROM serverless_stable_3vku19_catalog.inventory_risk.mv_forecast_accuracy GROUP BY ALL
```

| on_promo | model_wape | baseline_wape | improvement_pct |
|---|---|---|---|
| Regular day | 0.4585 | 0.5278 | 13.1 |
| Promotion day | 0.4012 | 0.5487 | 26.9 |
