# Demand forecast: baseline vs champion model

_Captured 2026-11-07 14:12 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- MLflow experiment: `/Users/adarsh.nandan@databricks.com/inventory-risk-radar-demand-forecast`
- Baseline run: `180788f3dbce49efb830faec6ec85dad` | LightGBM run: `218d0ae089fa4f7faf61c866135e1ba0`
- Registered model: `serverless_stable_3vku19_catalog.inventory_risk.demand_forecast` version **2** with alias **@champion** (status READY)
- Holdout origin 2026-10-09; 534,339 store/SKU/day rows scored (stockout days excluded); 1,886,854 training rows

| Metric | Seasonal naive (baseline) | LightGBM (champion) |
|---|---|---|
| holdout_wape | 0.5291 | 0.4547 |
| holdout_bias | 0.0576 | 0.0155 |
| holdout_mae | 3.2539 | 2.7959 |
| holdout_wape_promo_days | 0.5487 | 0.4011 |
| holdout_wape_non_promo_days | 0.5278 | 0.4583 |

**WAPE reduction vs baseline: 14.1%**

### By category

| Category | Baseline WAPE | Model WAPE | Reduction % |
|---|---|---|---|
| Bakery | 0.490 | 0.426 | 13.1 |
| Beverages | 0.575 | 0.461 | 19.9 |
| Dairy & Eggs | 0.491 | 0.431 | 12.1 |
| Fresh Produce | 0.478 | 0.410 | 14.2 |
| Frozen | 0.552 | 0.481 | 12.9 |
| Household | 0.691 | 0.621 | 10.1 |
| Meat & Seafood | 0.584 | 0.494 | 15.4 |
| Pantry & Baking | 0.566 | 0.497 | 12.1 |
| Personal Care | 0.795 | 0.729 | 8.4 |
| Snacks | 0.536 | 0.458 | 14.6 |

### Top features (gain)

| Feature | Gain |
|---|---|
| r28 | 43800682 |
| r7 | 2118398 |
| discount_pct | 1528948 |
| target_dow | 891901 |
| sn4_dow | 597524 |
| r28_std | 343208 |
| days_to_next_holiday | 273562 |
| category_code | 183948 |
| next_holiday_code | 160181 |
| on_promo | 85768 |

### Metric view check: WAPE promo vs regular days

```sql
SELECT on_promo, ROUND(MEASURE(model_wape), 4) AS model_wape, ROUND(MEASURE(baseline_wape), 4) AS baseline_wape, ROUND(MEASURE(wape_improvement_pct), 1) AS improvement_pct FROM serverless_stable_3vku19_catalog.inventory_risk.mv_forecast_accuracy GROUP BY ALL
```

| on_promo | model_wape | baseline_wape | improvement_pct |
|---|---|---|---|
| Regular day | 0.4583 | 0.5278 | 13.2 |
| Promotion day | 0.4011 | 0.5487 | 26.9 |
