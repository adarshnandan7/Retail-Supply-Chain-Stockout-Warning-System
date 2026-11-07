# Success metrics (buyer KPIs)

All KPIs are defined once as Unity Catalog metric views (`src/metrics/create_metric_views.py`) and reused by Genie, the AI/BI dashboard and the readout. Improvement targets are set **after** a baseline is established with the retailer's own data. The numbers in this repo come from synthetic data and show the method, not a promise.

| KPI | Definition | Source | Owner | Direction |
|---|---|---|---|---|
| Forecast error (WAPE) | Σ\|actual − forecast\| / Σ actual over store/SKU/days without a stockout (censored days excluded) | `mv_forecast_accuracy` | Demand planning | ↓ |
| Forecast bias | (Σ forecast − Σ actual) / Σ actual | `mv_forecast_accuracy` | Demand planning | → 0 |
| Stockout rate | Share of store/SKU/days ending with zero on hand. On-shelf availability = 1 − stockout rate | `mv_stockout_history` | Store ops / VP Supply Chain | ↓ |
| Inventory cover | On hand ÷ average forecast daily demand for the next 7 days | `mv_inventory_risk` | Replenishment | in band |
| Excess inventory | Share of store/SKUs with > 45 days of cover | `mv_inventory_risk` | Finance / Replenishment | ↓ |
| Revenue at risk | Expected lost units within the replenishment window × unit price | `mv_inventory_risk` | VP Supply Chain | ↓ |
| Alert precision | Share of Critical/High alerts that actually stocked out within their window (backtest) | `mv_alert_backtest` | Replenishment lead | ↑ |
| Alert recall | Share of actual stockouts that were alerted | `mv_alert_backtest` | Replenishment lead | ↑ |
| Time to planner action | Median hours from risk publication (`scored_at`) to the planner's first decision | app → Lakebase → `planner_action_history` | Replenishment lead | ↓ |
| Override rate | Share of decisions that differ from the suggested action or quantity | `planner_action_history` | Replenishment lead | monitor |

## Business value framing (to be calibrated with the retailer's baseline)

Lost sales from stockouts ≈ stockout days × average daily sales of the affected store/SKUs × substitution-adjusted loss rate. The radar's value is the share of those lost-sales days it prevents. That share comes from three numbers that can be measured in a pilot:

1. **Alert precision.** It decides how much planner time goes to real problems.
2. **Recall at a fixed workload.** It decides how many real stockouts are caught.
3. **Action effectiveness.** This is the share of actioned alerts where the shelf did not go empty.

Steps 1 and 2 are measured by the backtest in this repo. Step 3 needs the pilot, because it depends on how fast planners act and on supplier and DC responsiveness.
