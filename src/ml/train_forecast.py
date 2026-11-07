# Databricks notebook source
# MAGIC %md
# MAGIC # 04 - Train demand forecast: seasonal-naive baseline vs. global LightGBM
# MAGIC
# MAGIC * **Baseline** - same-weekday average of the last 4 weeks (what a spreadsheet replenishment process does today).
# MAGIC * **Challenger** - one global LightGBM model across all 20,000 store/SKU series and horizons 1-28 days,
# MAGIC   using history features plus calendar signals known in advance (planned promotions, holiday proximity).
# MAGIC * **Validation** - time-based holdout: forecast origin = as-of date minus 28 days; every store/SKU, every horizon.
# MAGIC   Stockout days are excluded from labels (censored demand).
# MAGIC * Both runs are tracked in MLflow; the winner is registered in Unity Catalog and gets the `@champion` alias.

# COMMAND ----------

# MAGIC %pip install -q lightgbm==4.5.0 "mlflow>=2.17"
# MAGIC %restart_python

# COMMAND ----------

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

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Build training and holdout sets

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Baseline run: seasonal naive

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Challenger run: global LightGBM (Tweedie objective for intermittent count demand)

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Compare and register the winner in Unity Catalog

# COMMAND ----------

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

# COMMAND ----------

# MAGIC %md ## Persist holdout predictions (forecast-error KPI and safety-buffer sigma)

# COMMAND ----------

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
