# Task `train_forecast` - SUCCESS
- Task run id: `610385030731505`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/ml/train_forecast`
- Duration: 253 s

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
[100]	val's tweedie: 25.9444
[200]	val's tweedie: 25.9439
[300]	val's tweedie: 25.9439

/local_disk0/.ephemeral_nfs/envs/pythonEnv-a8e778e4-872d-4af4-b992-15ecc354b081/lib/python3.12/site-packages/mlflow/types/utils.py:440: UserWarning: Hint: Inferred schema contains integer column(s). Integer columns in Python cannot represent missing values. If your input data contains missing values at inference time, it will be encoded as floats and will cause a schema enforcement error. The best way to avoid this problem is to infer the model schema based on a realistic data sample (training dataset) that includes missing values. Alternatively, you can declare integer columns as doubles (float64) whenever these columns may have missing values. See `Handling Integers With Missing Values <https://www.mlflow.org/docs/latest/models.html#handling-integers-with-missing-values>`_ for more details.
  warnings.warn(
2026/11/09 13:24:06 WARNING mlflow.models.model: `artifact_path` is deprecated. Please use `name` instead.
🔗 View Logged Model at: https://fevm-serverless-stable-3vku19.cloud.databricks.com/ml/experiments/1061037449516920/models/m-48cb10039d344e42881bebd574d67a15?o=7474656932908638

{
  "holdout_wape": 0.4548,
  "holdout_bias": 0.0161,
  "holdout_mae": 2.7969,
  "holdout_wape_promo_days": 0.4012,
  "holdout_wape_non_promo_days": 0.4585,
  "best_iteration": 250.0
}
             feature         gain
                 r28 4.381372e+07
                  r7 2.094676e+06
        discount_pct 1.527596e+06
          target_dow 8.968613e+05
             sn4_dow 6.699489e+05
             r28_std 3.360440e+05
days_to_next_holiday 2.763932e+05
       category_code 1.874301e+05
   next_holiday_code 1.586166e+05
       hol_ratio_sku 8.996982e+04
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
# Champion/challenger: the new model must beat the seasonal-naive baseline AND be at least as good as the current
# champion's WAPE on the latest window (measured by the drift_check task that triggered this retrain).
try:
    current_champion_wape = float(dbutils.jobs.taskValues.get(taskKey="drift_check", key="champion_current_wape", default="", debugValue="") or "inf")
except Exception:
    current_champion_wape = float("inf")
beats_baseline = m_l["holdout_wape"] < m_b["holdout_wape"]
beats_champion = m_l["holdout_wape"] <= current_champion_wape
winner = "lightgbm" if (beats_baseline and beats_champion) else ("baseline" if not beats_baseline else "current_champion")
print(f"beats baseline={beats_baseline}, beats current champion ({current_champion_wape})={beats_champion} -> {winner}")
registered = None
if winner == "lightgbm":
    mv = mlflow.register_model(f"runs:/{lgbm_run_id}/model", MODEL_NAME)
    client.set_registered_model_alias(MODEL_NAME, "champion", mv.version)
    client.update_model_version(MODEL_NAME, mv.version, description=(
        f"Global LightGBM direct multi-horizon demand forecast. Holdout WAPE {m_l['holdout_wape']:.3f} vs "
        f"seasonal-naive {m_b['holdout_wape']:.3f} (origin {holdout_origin})."))
    client.set_model_version_tag(MODEL_NAME, mv.version, "holdout_wape", f"{m_l['holdout_wape']:.4f}")
    client.set_model_version_tag(MODEL_NAME, mv.version, "baseline_wape", f"{m_b['holdout_wape']:.4f}")
    client.set_model_version_tag(MODEL_NAME, mv.version, "holdout_origin", str(holdout_origin))
    registered = int(mv.version)
print(f"winner={winner} registered={MODEL_NAME} v{registered} alias=@champion")
```

**Output**

```text
model                           run_id  holdout_wape  holdout_bias  holdout_mae  holdout_wape_promo_days  holdout_wape_non_promo_days
   seasonal_naive (baseline) 40608202e50c465c8dda082f4fd70e4e        0.5291        0.0576       3.2539                   0.5487                       0.5278
lightgbm_global (challenger) c48c1a77a54a487fa5997fec169de17c        0.4548        0.0161       2.7969                   0.4012                       0.4585
       category  baseline_wape  baseline_bias  lgbm_wape  lgbm_bias  wape_reduction_pct
         Bakery         0.4903        -0.0233     0.4261    -0.0387                13.1
      Beverages         0.5754         0.2092     0.4622     0.1076                19.7
   Dairy & Eggs         0.4908         0.0089     0.4314    -0.0088                12.1
  Fresh Produce         0.4784         0.0738     0.4109     0.0277                14.1
         Frozen         0.5523         0.0853     0.4800     0.0316                13.1
      Household         0.6911        -0.0042     0.6210    -0.0127                10.1
 Meat & Seafood         0.5840         0.0920     0.4946     0.0316                15.3
Pantry & Baking         0.5657        -0.0024     0.4972    -0.0386                12.1
  Personal Care         0.7953        -0.0252     0.7283    -0.0243                 8.4
         Snacks         0.5363         0.0296     0.4579     0.0123                14.6
beats baseline=True, beats current champion (0.4547)=False -> current_champion
winner=current_champion registered=serverless_stable_3vku19_catalog.inventory_risk.demand_forecast vNone alias=@champion
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
           "winner": winner, "current_champion_wape_before": current_champion_wape if current_champion_wape != float("inf") else None,
           "registered_model": MODEL_NAME, "registered_version": registered,
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
    "holdout_wape": 0.4548,
    "holdout_bias": 0.0161,
    "holdout_mae": 2.7969,
    "holdout_wape_promo_days": 0.4012,
    "holdout_wape_non_promo_days": 0.4585,
    "best_iteration": 250.0
  },
  "wape_reduction_pct": 14.0,
  "winner": "current_champion",
  "current_champion_wape_before": 0.4547,
  "registered_model": "serverless_stable_3vku19_catalog.inventory_risk.demand_forecast",
  "registered_version": null,
  "mlflow_runs": {
    "baseline": "40608202e50c465c8dda082f4fd70e4e",
    "lightgbm": "c48c1a77a54a487fa5997fec169de17c"
  },
  "experiment": "/Users/adarsh.nandan@databricks.com/inventory-risk-radar-demand-forecast",
  "by_category": [
    {
      "category": "Bakery",
      "baseline_wape": 0.4903,
      "baseline_bias": -0.0233,
      "lgbm_wape": 0.4261,
      "lgbm_bias": -0.0387,
      "wape_reduction_pct": 13.1
    },
    {
      "category": "Beverages",
      "baseline_wape": 0.5754,
      "baseline_bias": 0.2092,
      "lgbm_wape": 0.4622,
      "lgbm_bias": 0.1076,
      "wape_reduction_pct": 19.7
    },
    {
      "category": "Dairy & Eggs",
      "baseline_wape": 0.4908,
      "baseline_bias": 0.0089,
      "lgbm_wape": 0.4314,
      "lgbm_bias": -0.0088,
      "wape_reduction_pct": 12.1
    },
    {
      "category": "Fresh Produce",
      "baseline_wape": 0.4784,
      "baseline_bias": 0.0738,
      "lgbm_wape": 0.4109,
      "lgbm_bias": 0.0277,
      "wape_reduction_pct": 14.1
    },
    {
      "category": "Frozen",
      "baseline_wape": 0.5523,
      "baseline_bias": 0.0853,
      "lgbm_wape": 0.48,
      "lgbm_bias": 0.0316,
      "wape_reduction_pct": 13.1
    },
    {
      "category": "Household",
      "baseline_wape": 0.6911,
      "baseline_bias": -0.0042,
      "lgbm_wape": 0.621,
      "lgbm_bias": -0.0127,
      "wape_reduction_pct": 10.1
    },
    {
      "category": "Meat & Seafood",
      "baseline_wape": 0.584,
      "baseline_bias": 0.092,
      "lgbm_wape": 0.4946,
      "lgbm_bias": 0.0316,
      "wape_reduction_pct": 15.3
    },
    {
      "category": "Pantry & Baking",
      "baseline_wape": 0.5657,
      "baseline_bias": -0.0024,
      "lgbm_wape": 0.4972,
      "lgbm_bias": -0.0386,
      "wape_reduction_pct": 12.1
    },
    {
      "category": "Personal Care",
      "baseline_wape": 0.7953,
      "baseline_bias": -0.0252,
      "lgbm_wape": 0.7283,
      "lgbm_bias": -0.0243,
      "wape_reduction_pct": 8.4
    },
    {
      "category": "Snacks",
      "baseline_wape": 0.5363,
      "baseline_bias": 0.0296,
      "lgbm_wape": 0.4579,
      "lgbm_bias": 0.0123,
      "wape_reduction_pct": 14.6
    }
  ],
  "top_features": [
    {
      "feature": "r28",
      "gain": 43813720.395058155
    },
    {
      "feature": "r7",
      "gain": 2094675.5314736366
    },
    {
      "feature": "discount_pct",
      "gain": 1527595.9874210358
    },
    {
      "feature": "target_dow",
      "gain": 896861.3329372406
    },
    {
      "feature": "sn4_dow",
      "gain": 669948.9160628319
    },
    {
      "feature": "r28_std",
      "gain": 336044.03692626953
    },
    {
      "feature": "days_to_next_holiday",
      "gain": 276393.1688756943
    },
    {
      "feature": "category_code",
      "gain": 187430.10121631622
    },
    {
      "feature": "next_holiday_code",
      "gain": 158616.60124444962
    },
    {
      "feature": "hol_ratio_sku",
      "gain": 89969.82108306885
    }
  ]
}
```
