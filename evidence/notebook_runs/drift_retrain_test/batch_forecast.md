# Task `batch_forecast` - SUCCESS
- Task run id: `897354879912939`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/ml/batch_forecast`
- Duration: 80 s

## Cell 1

```markdown
%md
# 05a - Batch demand forecast with the `@champion` model
Scores the next 28 days for every store/SKU from the as-of date using the model version that holds the
`@champion` alias in Unity Catalog, and writes the result to the Delta table `demand_forecast`.
The seasonal-naive baseline is stored alongside so planners (and the risk drivers) can see the uplift the model expects.
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
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
AS_OF = dbutils.widgets.get("as_of_date")
MODEL_NAME = f"{FQ}.demand_forecast"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
```

## Cell 4

```python
import json
from datetime import date

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from pyspark.sql import functions as F

from features import CATEGORICAL, FEATURES, build_frame, seasonal_naive

mlflow.set_registry_uri("databricks-uc")
mv = MlflowClient().get_model_version_by_alias(MODEL_NAME, "champion")
model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
print(f"Loaded {MODEL_NAME} version {mv.version} (@champion), run {mv.run_id}")
```

**Output**

```text
Loaded serverless_stable_3vku19_catalog.inventory_risk.demand_forecast version 2 (@champion), run 218d0ae089fa4f7faf61c866135e1ba0
```

## Cell 5

```python
origin = date.fromisoformat(AS_OF)
pdf = build_frame(spark, FQ, origin, with_actuals=False).select(
    "store_id", "region", "sku_id", "category", "forecast_origin", "target_date", *FEATURES).toPandas()
for c in CATEGORICAL:
    pdf[c] = pdf[c].fillna(0).astype(int)
pdf["forecast_units"] = np.clip(model.predict(pdf[FEATURES]), 0, None).round(3)
pdf["baseline_units"] = seasonal_naive(pdf).round(3)
pdf["model_name"] = MODEL_NAME
pdf["model_version"] = int(mv.version)
out = spark.createDataFrame(pdf[["forecast_origin", "store_id", "region", "sku_id", "category", "target_date", "horizon",
                                 "on_promo", "discount_pct", "days_to_next_holiday", "forecast_units", "baseline_units",
                                 "model_name", "model_version"]]).withColumn("scored_at", F.current_timestamp())
out.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{FQ}.demand_forecast")
spark.sql(f"COMMENT ON TABLE {FQ}.demand_forecast IS 'Next-28-day daily demand forecast per store/SKU from the @champion model, with the seasonal-naive baseline for comparison.'")
```

## Cell 6

```python
summary = spark.sql(f"""
  SELECT count(*) AS rows, count(DISTINCT store_id, sku_id) AS series, min(target_date) AS first_day, max(target_date) AS last_day,
         round(sum(forecast_units)) AS total_forecast_units, round(sum(baseline_units)) AS total_baseline_units,
         round(sum(CASE WHEN on_promo = 1 THEN forecast_units END) / sum(CASE WHEN on_promo = 1 THEN baseline_units END), 3) AS promo_day_uplift_vs_baseline
  FROM {FQ}.demand_forecast""").toPandas().to_dict(orient="records")[0]
by_cat = spark.sql(f"""SELECT category, round(sum(forecast_units)) AS forecast_units_28d, round(sum(baseline_units)) AS baseline_units_28d,
  round(sum(forecast_units)/sum(baseline_units)-1, 3) AS uplift_vs_baseline FROM {FQ}.demand_forecast GROUP BY category ORDER BY uplift_vs_baseline DESC""").toPandas()
print(json.dumps(summary, indent=2, default=str))
print(by_cat.to_string(index=False))
with open(f"{EVIDENCE}/05a_batch_forecast.json", "w") as fh:
    json.dump({"model_version": int(mv.version), "summary": summary, "by_category": by_cat.to_dict(orient="records")}, fh, indent=2, default=str)
```

**Output**

```text
{
  "rows": 559888,
  "series": 19996,
  "first_day": "2026-11-07",
  "last_day": "2026-12-04",
  "total_forecast_units": 3581745.0,
  "total_baseline_units": 3483939.0,
  "promo_day_uplift_vs_baseline": 2.123
}
       category  forecast_units_28d  baseline_units_28d  uplift_vs_baseline
 Meat & Seafood            206409.0            178666.0               0.155
Pantry & Baking            403811.0            356377.0               0.133
         Bakery            375489.0            343591.0               0.093
   Dairy & Eggs            408622.0            389874.0               0.048
      Household             93392.0             91623.0               0.019
         Snacks            400992.0            393951.0               0.018
  Personal Care             53813.0             52906.0               0.017
  Fresh Produce           1044412.0           1052865.0              -0.008
         Frozen            252349.0            257645.0              -0.021
      Beverages            342456.0            366441.0              -0.065
```
