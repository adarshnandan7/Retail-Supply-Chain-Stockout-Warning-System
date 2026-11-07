# Task `train_forecast` - SUCCESS
- Task run id: `745938303385983`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/ml/train_forecast`
- Duration: 275 s

## Cell 1

```markdown
%md
# 04 - Train demand forecast: seasonal-naive baseline vs. global LightGBM

* **Baseline** - same-weekday average of the last 4 weeks (what a spreadsheet replenishment process does today).
* **Challenger** - one global LightGBM model across all 20,000 store/SKU series and horizons 1-28 days,
  using history features plus calendar signals known in advance (planned promotions, holiday proximity).
* **Validation** - time-based holdout: forecast origin = as-of date minus 28 days; every store/SKU, every horizon.
  Stockout days are excluded from labels (censored demand).
* Both runs are tracked in MLflow; the winner is registered in Unity Catalog and gets the `@champion` alias.
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
dbutils.widgets.text("experiment_name", "/Users/adarsh.nandan@databricks.com/inventory-risk-radar-demand-forecast")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
AS_OF = dbutils.widgets.get("as_of_date")
EXPERIMENT = dbutils.widgets.get("experiment_name")
MODEL_NAME = f"{FQ}.demand_forecast"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
```

## Cell 4

```python
import json
from datetime import date, timedelta

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

from features import CATEGORIES, CATEGORICAL, FEATURES, HORIZON, bias, build_frame, seasonal_naive, wape

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(EXPERIMENT)
as_of = date.fromisoformat(AS_OF)
holdout_origin = as_of - timedelta(days=HORIZON)
train_origins = [holdout_origin - timedelta(days=HORIZON * k) for k in range(1, 15)]  # ~13 months incl. last year's holidays
print("holdout origin:", holdout_origin, "| train origins:", train_origins[-1], "->", train_origins[0])
```

**Output**

```text
holdout origin: 2026-10-09 | train origins: 2025-09-12 -> 2026-09-11

If you are using MLflow Tracing, you can migrate your traces to Unity Catalog for unlimited storage, fine-grained access controls, and queryability from notebooks, SQL, and dashboards. Learn more: https://docs.databricks.com/aws/en/mlflow3/genai/tracing/migrate-traces-to-uc
```

## Cell 5

```markdown
%md ## Build training and holdout sets
```

## Cell 6

```python
train_sdf = None
for o in train_origins:
    f = build_frame(spark, FQ, o, with_actuals=True, series_fraction=0.25).where("NOT is_stockout")
    train_sdf = f if train_sdf is None else train_sdf.unionByName(f)
cols = ["store_id", "sku_id", "category", "target_date", "forecast_origin", "units_sold"] + FEATURES
# horizon/discount/holiday columns are both identifiers and features; FEATURES already contains them
train = train_sdf.select(*cols).toPandas()
hold = build_frame(spark, FQ, holdout_origin, with_actuals=True).select(*cols, "is_stockout", "region").toPandas()
print(f"train rows: {len(train):,} | holdout rows: {len(hold):,} (stockout days in holdout: {int(hold.is_stockout.sum()):,})")
hold_eval = hold[~hold.is_stockout].copy()
for df in (train, hold, hold_eval):
    for c in CATEGORICAL:
        df[c] = df[c].fillna(0).astype(int)
```

**Output**

```text
train rows: 1,886,854 | holdout rows: 559,762 (stockout days in holdout: 25,423)
```

## Cell 7

```markdown
%md ## Baseline run: seasonal naive
```

## Cell 8

```python
def category_table(df, pred_col):
    rows = []
    for c, g in df.groupby("category"):
        rows.append({"category": c, "wape": round(wape(g.units_sold, g[pred_col]), 4), "bias": round(bias(g.units_sold, g[pred_col]), 4)})
    return pd.DataFrame(rows)

hold_eval["baseline_pred"] = seasonal_naive(hold_eval)
promo_mask = hold_eval.on_promo == 1
holiday_mask = hold_eval.days_to_next_holiday <= 7
with mlflow.start_run(run_name="baseline_seasonal_naive") as run_b:
    m_b = {
        "holdout_wape": wape(hold_eval.units_sold, hold_eval.baseline_pred),
        "holdout_bias": bias(hold_eval.units_sold, hold_eval.baseline_pred),
        "holdout_mae": float((hold_eval.units_sold - hold_eval.baseline_pred).abs().mean()),
        "holdout_wape_promo_days": wape(hold_eval.units_sold[promo_mask], hold_eval.baseline_pred[promo_mask]),
        "holdout_wape_non_promo_days": wape(hold_eval.units_sold[~promo_mask], hold_eval.baseline_pred[~promo_mask]),
    }
    mlflow.log_params({"model_type": "seasonal_naive", "lookback_weeks": 4, "holdout_origin": str(holdout_origin)})
    mlflow.log_metrics(m_b)
    cat_b = category_table(hold_eval, "baseline_pred")
    mlflow.log_table(cat_b, "category_metrics.json")
baseline_run_id = run_b.info.run_id
print(json.dumps({k: round(v, 4) for k, v in m_b.items()}, indent=2))
```

**Output**

```text
{
  "holdout_wape": 0.5291,
  "holdout_bias": 0.0576,
  "holdout_mae": 3.2539,
  "holdout_wape_promo_days": 0.5487,
  "holdout_wape_non_promo_days": 0.5278
}
```

## Cell 9

```markdown
%md ## Challenger run: global LightGBM (Tweedie objective for intermittent count demand)
```

## Cell 10

```python
params = {"objective": "tweedie", "tweedie_variance_power": 1.2, "learning_rate": 0.05, "num_leaves": 127,
          "min_data_in_leaf": 200, "feature_fraction": 0.85, "bagging_fraction": 0.8, "bagging_freq": 1,
          "lambda_l2": 1.0, "verbose": -1, "seed": 7}
# last training origin acts as early-stopping validation
val_origin = pd.Timestamp(train_origins[0]).date()
is_val = pd.to_datetime(train.forecast_origin).dt.date == val_origin
dtrain = lgb.Dataset(train.loc[~is_val, FEATURES], train.loc[~is_val, "units_sold"], categorical_feature=CATEGORICAL)
dval = lgb.Dataset(train.loc[is_val, FEATURES], train.loc[is_val, "units_sold"], categorical_feature=CATEGORICAL, reference=dtrain)

with mlflow.start_run(run_name="lightgbm_global_direct_multihorizon") as run_l:
    booster = lgb.train(params, dtrain, num_boost_round=1500, valid_sets=[dval], valid_names=["val"],
                        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)])
    hold_eval["lgbm_pred"] = np.clip(booster.predict(hold_eval[FEATURES], num_iteration=booster.best_iteration), 0, None)
    m_l = {
        "holdout_wape": wape(hold_eval.units_sold, hold_eval.lgbm_pred),
        "holdout_bias": bias(hold_eval.units_sold, hold_eval.lgbm_pred),
        "holdout_mae": float((hold_eval.units_sold - hold_eval.lgbm_pred).abs().mean()),
        "holdout_wape_promo_days": wape(hold_eval.units_sold[promo_mask], hold_eval.lgbm_pred[promo_mask]),
        "holdout_wape_non_promo_days": wape(hold_eval.units_sold[~promo_mask], hold_eval.lgbm_pred[~promo_mask]),
        "best_iteration": booster.best_iteration,
    }
    mlflow.log_params({**params, "model_type": "lightgbm", "features": ",".join(FEATURES), "horizon_days": HORIZON,
                       "train_origins": len(train_origins), "train_rows": len(train), "holdout_origin": str(holdout_origin)})
    mlflow.log_metrics(m_l)
    cat_l = category_table(hold_eval, "lgbm_pred")
    mlflow.log_table(cat_l, "category_metrics.json")
    imp = pd.DataFrame({"feature": FEATURES, "gain": booster.feature_importance("gain")}).sort_values("gain", ascending=False)
    mlflow.log_table(imp, "feature_importance.json")
    sample = hold_eval[FEATURES].head(50)
    signature = infer_signature(sample, booster.predict(sample, num_iteration=booster.best_iteration))
    mlflow.lightgbm.log_model(booster, artifact_path="model", signature=signature, input_example=sample.head(5),
                              pip_requirements=["lightgbm==4.5.0", "pandas", "numpy"])
lgbm_run_id = run_l.info.run_id
print(json.dumps({k: round(float(v), 4) for k, v in m_l.items()}, indent=2))
print(imp.head(10).to_string(index=False))
```

**Output**

```text
[100]	val's tweedie: 25.9449
[200]	val's tweedie: 25.9441

/local_disk0/.ephemeral_nfs/envs/pythonEnv-841e8e37-f4f9-48e2-a830-d9e584907fd4/lib/python3.12/site-packages/mlflow/types/utils.py:440: UserWarning: Hint: Inferred schema contains integer column(s). Integer columns in Python cannot represent missing values. If your input data contains missing values at inference time, it will be encoded as floats and will cause a schema enforcement error. The best way to avoid this problem is to infer the model schema based on a realistic data sample (training dataset) that includes missing values. Alternatively, you can declare integer columns as doubles (float64) whenever these columns may have missing values. See `Handling Integers With Missing Values <https://www.mlflow.org/docs/latest/models.html#handling-integers-with-missing-values>`_ for more details.
  warnings.warn(
2026/11/07 14:01:48 WARNING mlflow.models.model: `artifact_path` is deprecated. Please use `name` instead.
🔗 View Logged Model at: https://fevm-serverless-stable-3vku19.cloud.databricks.com/ml/experiments/1061037449516920/models/m-1cecc67d589947c291f7f80bbd6f2d7f?o=7474656932908638

{
  "holdout_wape": 0.4547,
  "holdout_bias": 0.0155,
  "holdout_mae": 2.7959,
  "holdout_wape_promo_days": 0.4011,
  "holdout_wape_non_promo_days": 0.4583,
  "best_iteration": 210.0
}
             feature         gain
                 r28 4.380068e+07
                  r7 2.118398e+06
        discount_pct 1.528948e+06
          target_dow 8.919010e+05
             sn4_dow 5.975240e+05
             r28_std 3.432080e+05
days_to_next_holiday 2.735622e+05
       category_code 1.839477e+05
   next_holiday_code 1.601812e+05
            on_promo 8.576826e+04
```

## Cell 11

```markdown
%md ## Compare and register the winner in Unity Catalog
```

## Cell 12

```python
comparison = pd.DataFrame([
    {"model": "seasonal_naive (baseline)", "run_id": baseline_run_id, **{k: round(v, 4) for k, v in m_b.items()}},
    {"model": "lightgbm_global (challenger)", "run_id": lgbm_run_id, **{k: round(float(v), 4) for k, v in m_l.items() if k != "best_iteration"}},
])
print(comparison.to_string(index=False))
by_cat = cat_b.rename(columns={"wape": "baseline_wape", "bias": "baseline_bias"}).merge(
    cat_l.rename(columns={"wape": "lgbm_wape", "bias": "lgbm_bias"}), on="category")
by_cat["wape_reduction_pct"] = ((by_cat.baseline_wape - by_cat.lgbm_wape) / by_cat.baseline_wape * 100).round(1)
print(by_cat.to_string(index=False))

client = MlflowClient()
winner = "lightgbm" if m_l["holdout_wape"] < m_b["holdout_wape"] else "baseline"
registered = None
if winner == "lightgbm":
    mv = mlflow.register_model(f"runs:/{lgbm_run_id}/model", MODEL_NAME)
    client.set_registered_model_alias(MODEL_NAME, "champion", mv.version)
    client.update_model_version(MODEL_NAME, mv.version, description=(
        f"Global LightGBM direct multi-horizon demand forecast. Holdout WAPE {m_l['holdout_wape']:.3f} vs "
        f"seasonal-naive {m_b['holdout_wape']:.3f} (origin {holdout_origin})."))
    client.set_model_version_tag(MODEL_NAME, mv.version, "holdout_wape", f"{m_l['holdout_wape']:.4f}")
    client.set_model_version_tag(MODEL_NAME, mv.version, "baseline_wape", f"{m_b['holdout_wape']:.4f}")
    registered = int(mv.version)
print(f"winner={winner} registered={MODEL_NAME} v{registered} alias=@champion")
```

**Output**

```text
model                           run_id  holdout_wape  holdout_bias  holdout_mae  holdout_wape_promo_days  holdout_wape_non_promo_days
   seasonal_naive (baseline) 180788f3dbce49efb830faec6ec85dad        0.5291        0.0576       3.2539                   0.5487                       0.5278
lightgbm_global (challenger) 218d0ae089fa4f7faf61c866135e1ba0        0.4547        0.0155       2.7959                   0.4011                       0.4583
       category  baseline_wape  baseline_bias  lgbm_wape  lgbm_bias  wape_reduction_pct
         Bakery         0.4903        -0.0233     0.4263    -0.0401                13.1
      Beverages         0.5754         0.2092     0.4610     0.1030                19.9
   Dairy & Eggs         0.4908         0.0089     0.4314    -0.0087                12.1
  Fresh Produce         0.4784         0.0738     0.4105     0.0265                14.2
         Frozen         0.5523         0.0853     0.4810     0.0372                12.9
      Household         0.6911        -0.0042     0.6212    -0.0118                10.1
 Meat & Seafood         0.5840         0.0920     0.4942     0.0317                15.4
Pantry & Baking         0.5657        -0.0024     0.4970    -0.0391                12.1
  Personal Care         0.7953        -0.0252     0.7288    -0.0223                 8.4
         Snacks         0.5363         0.0296     0.4578     0.0123                14.6

Registered model 'serverless_stable_3vku19_catalog.inventory_risk.demand_forecast' already exists. Creating a new version of this model...
2026/11/07 14:01:57 WARNING mlflow.tracking._model_registry.fluent: Run with id 218d0ae089fa4f7faf61c866135e1ba0 has no artifacts at artifact path 'model', registering model based on models:/m-1cecc67d589947c291f7f80bbd6f2d7f instead



🔗 Created version '2' of model 'serverless_stable_3vku19_catalog.inventory_risk.demand_forecast': https://fevm-serverless-stable-3vku19.cloud.databricks.com/explore/data/models/serverless_stable_3vku19_catalog/inventory_risk/demand_forecast/version/2?o=7474656932908638

winner=lightgbm registered=serverless_stable_3vku19_catalog.inventory_risk.demand_forecast v2 alias=@champion
```

## Cell 13

```markdown
%md ## Persist holdout predictions (forecast-error KPI and safety-buffer sigma)
```

## Cell 14

```python
hold_out = hold.copy()
hold_out["baseline_pred"] = seasonal_naive(hold_out)
hold_out["lgbm_pred"] = np.clip(booster.predict(hold_out[FEATURES], num_iteration=booster.best_iteration), 0, None)
hold_sdf = spark.createDataFrame(hold_out[["store_id", "region", "sku_id", "category", "forecast_origin", "target_date", "horizon",
                                           "on_promo", "discount_pct", "days_to_next_holiday", "units_sold", "is_stockout",
                                           "baseline_pred", "lgbm_pred"]])
(hold_sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{FQ}.forecast_backtest"))
spark.sql(f"COMMENT ON TABLE {FQ}.forecast_backtest IS 'Holdout (backtest) forecasts vs actuals per store/SKU/day for the baseline and the champion model. Source for forecast-error KPIs and residual sigma.'")

summary = {"holdout_origin": str(holdout_origin), "train_rows": len(train), "holdout_rows_scored": len(hold_eval),
           "baseline": {k: round(v, 4) for k, v in m_b.items()}, "lightgbm": {k: round(float(v), 4) for k, v in m_l.items()},
           "wape_reduction_pct": round((m_b["holdout_wape"] - m_l["holdout_wape"]) / m_b["holdout_wape"] * 100, 1),
           "winner": winner, "registered_model": MODEL_NAME, "registered_version": registered,
           "mlflow_runs": {"baseline": baseline_run_id, "lightgbm": lgbm_run_id}, "experiment": EXPERIMENT,
           "by_category": by_cat.to_dict(orient="records"), "top_features": imp.head(10).to_dict(orient="records")}
with open(f"{EVIDENCE}/04_model_comparison.json", "w") as fh:
    json.dump(summary, fh, indent=2, default=str)
print(json.dumps(summary, indent=2, default=str))
```

**Output**

```text
{
  "holdout_origin": "2026-10-09",
  "train_rows": 1886854,
  "holdout_rows_scored": 534339,
  "baseline": {
    "holdout_wape": 0.5291,
    "holdout_bias": 0.0576,
    "holdout_mae": 3.2539,
    "holdout_wape_promo_days": 0.5487,
    "holdout_wape_non_promo_days": 0.5278
  },
  "lightgbm": {
    "holdout_wape": 0.4547,
    "holdout_bias": 0.0155,
    "holdout_mae": 2.7959,
    "holdout_wape_promo_days": 0.4011,
    "holdout_wape_non_promo_days": 0.4583,
    "best_iteration": 210.0
  },
  "wape_reduction_pct": 14.1,
  "winner": "lightgbm",
  "registered_model": "serverless_stable_3vku19_catalog.inventory_risk.demand_forecast",
  "registered_version": 2,
  "mlflow_runs": {
    "baseline": "180788f3dbce49efb830faec6ec85dad",
    "lightgbm": "218d0ae089fa4f7faf61c866135e1ba0"
  },
  "experiment": "/Users/adarsh.nandan@databricks.com/inventory-risk-radar-demand-forecast",
  "by_category": [
    {
      "category": "Bakery",
      "baseline_wape": 0.4903,
      "baseline_bias": -0.0233,
      "lgbm_wape": 0.4263,
      "lgbm_bias": -0.0401,
      "wape_reduction_pct": 13.1
    },
    {
      "category": "Beverages",
      "baseline_wape": 0.5754,
      "baseline_bias": 0.2092,
      "lgbm_wape": 0.461,
      "lgbm_bias": 0.103,
      "wape_reduction_pct": 19.9
    },
    {
      "category": "Dairy & Eggs",
      "baseline_wape": 0.4908,
      "baseline_bias": 0.0089,
      "lgbm_wape": 0.4314,
      "lgbm_bias": -0.0087,
      "wape_reduction_pct": 12.1
    },
    {
      "category": "Fresh Produce",
      "baseline_wape": 0.4784,
      "baseline_bias": 0.0738,
      "lgbm_wape": 0.4105,
      "lgbm_bias": 0.0265,
      "wape_reduction_pct": 14.2
    },
    {
      "category": "Frozen",
      "baseline_wape": 0.5523,
      "baseline_bias": 0.0853,
      "lgbm_wape": 0.481,
      "lgbm_bias": 0.0372,
      "wape_reduction_pct": 12.9
    },
    {
      "category": "Household",
      "baseline_wape": 0.6911,
      "baseline_bias": -0.0042,
      "lgbm_wape": 0.6212,
      "lgbm_bias": -0.0118,
      "wape_reduction_pct": 10.1
    },
    {
      "category": "Meat & Seafood",
      "baseline_wape": 0.584,
      "baseline_bias": 0.092,
      "lgbm_wape": 0.4942,
      "lgbm_bias": 0.0317,
      "wape_reduction_pct": 15.4
    },
    {
      "category": "Pantry & Baking",
      "baseline_wape": 0.5657,
      "baseline_bias": -0.0024,
      "lgbm_wape": 0.497,
      "lgbm_bias": -0.0391,
      "wape_reduction_pct": 12.1
    },
    {
      "category": "Personal Care",
      "baseline_wape": 0.7953,
      "baseline_bias": -0.0252,
      "lgbm_wape": 0.7288,
      "lgbm_bias": -0.0223,
      "wape_reduction_pct": 8.4
    },
    {
      "category": "Snacks",
      "baseline_wape": 0.5363,
      "baseline_bias": 0.0296,
      "lgbm_wape": 0.4578,
      "lgbm_bias": 0.0123,
      "wape_reduction_pct": 14.6
    }
  ],
  "top_features": [
    {
      "feature": "r28",
      "gain": 43800681.81296635
    },
    {
      "feature": "r7",
      "gain": 2118397.924232483
    },
    {
      "feature": "discount_pct",
      "gain": 1528948.4356908798
    },
    {
      "feature": "target_dow",
      "gain": 891901.015917778
    },
    {
      "feature": "sn4_dow",
      "gain": 597524.0454559326
    },
    {
      "feature": "r28_std",
      "gain": 343208.0067152977
    },
    {
      "feature": "days_to_next_holiday",
      "gain": 273562.22022151947
    },
    {
      "feature": "category_code",
      "gain": 183947.70071792603
    },
    {
      "feature": "next_holiday_code",
      "gain": 160181.19604492188
    },
    {
      "feature": "on_promo",
      "gain": 85768.25899600983
    }
  ]
}
```
