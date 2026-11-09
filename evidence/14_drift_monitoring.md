# Forecast drift check and conditional retraining

_Captured 2026-11-09 13:30 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

### model_monitoring (every drift check, newest first)

```sql
SELECT checked_at, as_of_date, champion_version, champion_current_wape, champion_registered_wape, baseline_current_wape,
  degradation_pct, drift_threshold_pct, retrain, reasons FROM serverless_stable_3vku19_catalog.inventory_risk.model_monitoring ORDER BY checked_at DESC LIMIT 10
```

| checked_at | as_of_date | champion_version | champion_current_wape | champion_registered_wape | baseline_current_wape | degradation_pct | drift_threshold_pct | retrain | reasons |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-09T13:19:25.838553+00:00 | 2026-11-06 | 2 | 0.4547 | 0.4547 | 0.5291 | -0.01 | -1.0 | true | accuracy drift: WAPE 0.4547 is -0.0% worse than at registration (0.4547) |
| 2026-11-09T12:59:04.268375+00:00 | 2026-11-06 | 2 | 0.4547 | 0.4547 | 0.5291 | -0.01 | 10.0 | false | champion healthy: within drift threshold and better than baseline |

### Job run `1079588740947181` (drift_threshold_pct = 10, the default) - SUCCESS

| Task | Result |
|---|---|
| drift_check | SUCCESS |
| needs_retrain | SUCCESS |
| train_forecast | EXCLUDED |
| batch_forecast | SUCCESS |

### Job run `912248781031579` (drift_threshold_pct = -1, lowered to simulate drift) - SUCCESS

| Task | Result |
|---|---|
| drift_check | SUCCESS |
| needs_retrain | SUCCESS |
| train_forecast | SUCCESS |
| batch_forecast | SUCCESS |

### Registered model versions

| version | created | aliases |
|---|---|---|
| 1 | 2026-11-07 13:14 |  |
| 2 | 2026-11-07 14:01 | @champion |
