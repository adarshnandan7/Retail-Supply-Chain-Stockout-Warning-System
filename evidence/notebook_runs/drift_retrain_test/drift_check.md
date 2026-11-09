# Task `drift_check` - SUCCESS
- Task run id: `799787029231383`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/ml/drift_check`
- Duration: 90 s

## Cell 1

```markdown
%md
# 03b - Forecast drift check: retrain only when the champion degrades

Runs every morning before training. It scores the current `@champion` on the **latest 28 days of actuals**
(stockout days excluded) and decides whether the job should retrain:

| Trigger | Rule |
|---|---|
| No champion | no model holds the `@champion` alias yet |
| Accuracy drift | latest WAPE is more than `drift_threshold_pct` % worse than the WAPE recorded when the champion was registered |
| Lost to baseline | latest WAPE is worse than the seasonal-naive baseline on the same window |
| Stale | the champion was validated on data more than `max_model_age_days` older than today's latest window |

The decision is written to the Delta table `model_monitoring` and passed to the job as the task value `retrain`,
which a condition task uses to run or skip `train_forecast`.
```

## Cell 2

```python
%pip install -q lightgbm==4.5.0 "mlflow>=2.17"
%restart_python
```

**Output**

```text
Note: you may need to restart the kernel using %restart_python or dbutils.library.restartPython() to use updated packages.
```

## Cell 3

```python
dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("as_of_date", "2026-11-06")
dbutils.widgets.text("drift_threshold_pct", "10")
dbutils.widgets.text("max_model_age_days", "56")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
AS_OF = dbutils.widgets.get("as_of_date")
THRESH = float(dbutils.widgets.get("drift_threshold_pct"))
MAX_AGE = int(dbutils.widgets.get("max_model_age_days"))
MODEL_NAME = f"{FQ}.demand_forecast"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
```

## Cell 4

```python
import json
from datetime import date, datetime, timedelta, timezone

import mlflow
import numpy as np
import pandas as pd
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from features import CATEGORICAL, FEATURES, HORIZON, build_frame, seasonal_naive, wape

mlflow.set_registry_uri("databricks-uc")
client = MlflowClient()
as_of = date.fromisoformat(AS_OF)
window_origin = as_of - timedelta(days=HORIZON)
result = {"checked_at": datetime.now(timezone.utc).isoformat(), "as_of_date": AS_OF, "window_origin": str(window_origin),
          "drift_threshold_pct": THRESH, "max_model_age_days": MAX_AGE}

try:
    mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
except MlflowException:
    mv = None

if mv is None:
    result.update(champion_version=None, retrain=True, reasons=["no champion registered"])
else:
    pdf = build_frame(spark, FQ, window_origin, with_actuals=True).where("NOT is_stockout").select(
        "units_sold", "category", *FEATURES).toPandas()
    for c in CATEGORICAL:
        pdf[c] = pdf[c].fillna(0).astype(int)
    model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
    pred = np.clip(model.predict(pdf[FEATURES]), 0, None)
    current = wape(pdf.units_sold, pred)
    baseline = wape(pdf.units_sold, seasonal_naive(pdf))
    tags = mv.tags or {}
    registered = float(tags.get("holdout_wape", current))
    validated_on = date.fromisoformat(tags.get("holdout_origin", str(window_origin)))
    degradation = (current - registered) / registered * 100
    age_days = (window_origin - validated_on).days
    reasons = []
    if degradation > THRESH:
        reasons.append(f"accuracy drift: WAPE {current:.4f} is {degradation:.1f}% worse than at registration ({registered:.4f})")
    if current >= baseline:
        reasons.append(f"lost to baseline: WAPE {current:.4f} >= seasonal naive {baseline:.4f}")
    if age_days > MAX_AGE:
        reasons.append(f"stale: validated on a window {age_days} days older than today's")
    result.update(champion_version=int(mv.version), rows_scored=len(pdf), champion_current_wape=round(current, 4),
                  baseline_current_wape=round(baseline, 4), champion_registered_wape=round(registered, 4),
                  degradation_pct=round(degradation, 2), model_age_days=age_days, retrain=bool(reasons),
                  reasons=reasons or ["champion healthy: within drift threshold and better than baseline"])

print(json.dumps(result, indent=2))
```

**Output**

```text
{
  "checked_at": "2026-11-09T13:19:25.838553+00:00",
  "as_of_date": "2026-11-06",
  "window_origin": "2026-10-09",
  "drift_threshold_pct": -1.0,
  "max_model_age_days": 56,
  "champion_version": 2,
  "rows_scored": 534339,
  "champion_current_wape": 0.4547,
  "baseline_current_wape": 0.5291,
  "champion_registered_wape": 0.4547,
  "degradation_pct": -0.01,
  "model_age_days": 0,
  "retrain": true,
  "reasons": [
    "accuracy drift: WAPE 0.4547 is -0.0% worse than at registration (0.4547)"
  ]
}
```

## Cell 5

```python
row = pd.DataFrame([{**{k: v for k, v in result.items() if k != "reasons"}, "reasons": " | ".join(result["reasons"])}])
spark.createDataFrame(row.astype({c: "string" for c in row.columns if row[c].dtype == object})).write.mode("append") \
    .option("mergeSchema", "true").saveAsTable(f"{FQ}.model_monitoring")
spark.sql(f"COMMENT ON TABLE {FQ}.model_monitoring IS 'Daily drift check of the @champion demand forecast: latest-window WAPE vs registration and baseline, and the retrain decision.'")
print(spark.sql(f"SELECT checked_at, champion_version, champion_current_wape, degradation_pct, retrain, reasons FROM {FQ}.model_monitoring ORDER BY checked_at DESC LIMIT 5").toPandas().to_string(index=False))

dbutils.jobs.taskValues.set(key="retrain", value="true" if result["retrain"] else "false")
dbutils.jobs.taskValues.set(key="champion_current_wape", value=str(result.get("champion_current_wape", "")))
with open(f"{EVIDENCE}/03b_drift_check.json", "w") as fh:
    json.dump(result, fh, indent=2, default=str)
```

**Output**

```text
checked_at  champion_version  champion_current_wape  degradation_pct  retrain                                                                  reasons
2026-11-09T13:19:25.838553+00:00                 2                 0.4547            -0.01     True accuracy drift: WAPE 0.4547 is -0.0% worse than at registration (0.4547)
2026-11-09T12:59:04.268375+00:00                 2                 0.4547            -0.01    False        champion healthy: within drift threshold and better than baseline
```
