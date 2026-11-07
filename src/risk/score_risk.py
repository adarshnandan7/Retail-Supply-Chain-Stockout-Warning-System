# Databricks notebook source
# MAGIC %md
# MAGIC # 05b - Inventory-risk scoring and recommended actions
# MAGIC
# MAGIC Compares forecast demand over each item's replenishment window with on-hand + inbound stock, and ranks
# MAGIC likely stockouts with quantified drivers and a suggested action (see `risk_logic.py` for the full method).
# MAGIC
# MAGIC * **Production run** - origin = as-of date, forecasts from `demand_forecast` -> `risk_recommendations`
# MAGIC * **Backtest run** - origin = as-of minus 28 days, forecasts from `forecast_backtest` -> `risk_backtest`,
# MAGIC   then alert precision/recall vs. what actually stocked out, compared with today's rule of thumb
# MAGIC   ("days of cover below supplier lead time").

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("as_of_date", "2026-11-06")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
AS_OF = dbutils.widgets.get("as_of_date")
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"

# COMMAND ----------

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
from pyspark.sql import functions as F

from risk_logic import score

as_of = date.fromisoformat(AS_OF)
backtest_origin = as_of - timedelta(days=28)


def inputs(origin: date):
    """Inventory position, supplier performance and open POs exactly as they were known at `origin`."""
    o = F.lit(origin.isoformat()).cast("date")
    daily = spark.table(f"{FQ}.gold_daily_store_sku_sales")
    hist = daily.where((F.col("sale_date") > F.date_sub(o, 28)) & (F.col("sale_date") <= o))
    clean = F.when(~F.col("is_stockout"), F.col("units_sold"))
    stats = hist.groupBy("store_id", "sku_id").agg(
        F.avg(F.when(F.col("sale_date") > F.date_sub(o, 7), clean)).alias("r7"), F.avg(clean).alias("r28"),
        F.stddev(clean).alias("r28_std"))
    onhand = daily.where(F.col("sale_date") == o).select("store_id", "sku_id", F.col("eod_on_hand_units").alias("on_hand_units"))
    lines = spark.table(f"{FQ}.gold_po_lines")
    rec = lines.where((F.col("received_date") <= o) & (F.col("received_date") > F.date_sub(o, 90)))
    recent = F.col("received_date") > F.date_sub(o, 30)
    sup = rec.groupBy("supplier_id").agg(
        F.avg(F.when(recent, F.col("actual_lead_time_days"))).alias("avg_lead_time_30d"),
        (1 - F.avg(F.when(recent, F.col("is_late").cast("int")))).alias("on_time_rate_last_30d"),
        F.avg(F.when(recent, F.col("days_late"))).alias("avg_days_late_last_30d"),
        F.avg(F.when(recent & F.col("is_late"), F.col("days_late"))).alias("avg_days_late_when_late_30d"))
    supm = spark.table(f"{FQ}.silver_suppliers").select("supplier_id", "supplier_name", "contract_lead_time_days")
    prod = spark.table(f"{FQ}.silver_products").select("sku_id", "sku_name", "category", "supplier_id", "unit_price", "case_pack", "is_perishable")
    stores = spark.table(f"{FQ}.silver_stores").select("store_id", "store_name", "region")
    position = (onhand.join(stats, ["store_id", "sku_id"], "left").join(prod, "sku_id").join(stores, "store_id")
                .join(supm, "supplier_id", "left").join(sup, "supplier_id", "left")).toPandas()
    open_at_o = lines.where((F.col("order_date") <= o) & (F.col("received_date").isNull() | (F.col("received_date") > o)))
    exp_day = F.datediff("expected_delivery_date", o)
    inbound = (open_at_o.join(sup.select("supplier_id", "avg_days_late_last_30d", "avg_days_late_when_late_30d"), "supplier_id", "left")
               .select("store_id", "sku_id", F.col("order_qty").alias("qty"), exp_day.alias("expected_day"),
                       # not yet due: shift by average delay; already overdue: known late, shift by average lateness when late
                       F.when(exp_day > 0, exp_day + F.ceil(F.coalesce("avg_days_late_last_30d", F.lit(0.0))))
                        .otherwise(F.greatest(F.lit(1), exp_day + F.ceil(F.coalesce("avg_days_late_when_late_30d", F.lit(2.0)))))
                        .cast("int").alias("projected_day"))).toPandas()
    return position, inbound


# COMMAND ----------

# MAGIC %md ## Production run (as-of date)

# COMMAND ----------

pos, inb = inputs(as_of)
fc = spark.table(f"{FQ}.demand_forecast").select("store_id", "sku_id", "horizon", "forecast_units", "baseline_units",
                                                 "on_promo", "days_to_next_holiday").toPandas()
model_version = spark.table(f"{FQ}.demand_forecast").select(F.max("model_version")).first()[0]
risk = score(pos, fc, inb)
risk.insert(0, "recommendation_id", risk.store_id + "-" + risk.sku_id)
risk.insert(1, "as_of_date", as_of)
risk["model_version"] = int(model_version)
risk = risk.sort_values(["risk_score", "revenue_at_risk"], ascending=False).reset_index(drop=True)
risk["risk_rank"] = np.arange(1, len(risk) + 1)
def nan_to_null(sdf):
    """pandas NaN -> SQL NULL for float columns (Postgres sync and BI tools expect NULL, not NaN)."""
    for c, t in sdf.dtypes:
        if t in ("double", "float"):
            sdf = sdf.withColumn(c, F.when(F.isnan(c), None).otherwise(F.col(c)))
    return sdf


(nan_to_null(spark.createDataFrame(risk)).withColumn("scored_at", F.current_timestamp())
 .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{FQ}.risk_scores"))
print(risk.risk_tier.value_counts().to_dict())
print(risk.recommended_action.value_counts().to_dict())
print(risk.head(15)[["risk_rank", "store_id", "sku_name", "risk_score", "risk_tier", "stockout_probability", "revenue_at_risk",
                     "primary_driver", "recommended_action", "recommended_qty"]].to_string(index=False))

# COMMAND ----------

# MAGIC %md ## Backtest: would the radar have warned planners 4 weeks ago?

# COMMAND ----------

pos_b, inb_b = inputs(backtest_origin)
bt = spark.table(f"{FQ}.forecast_backtest").select(
    "store_id", "sku_id", "horizon", F.col("lgbm_pred").alias("forecast_units"), F.col("baseline_pred").alias("baseline_units"),
    "on_promo", "days_to_next_holiday", "is_stockout").toPandas()
risk_b = score(pos_b, bt, inb_b)
# actual outcome: did the item stock out (end-of-day on hand = 0) within its replenishment window?
act = bt.merge(risk_b[["store_id", "sku_id", "lead_time_window_days"]], on=["store_id", "sku_id"])
act = act[act.horizon <= act.lead_time_window_days].groupby(["store_id", "sku_id"])["is_stockout"].any().rename("actual_stockout_in_window")
risk_b = risk_b.merge(act.reset_index(), on=["store_id", "sku_id"], how="left").fillna({"actual_stockout_in_window": False})
# today's rule of thumb: trailing days of cover below contract lead time
pb = pos_b.set_index(["store_id", "sku_id"])
rule_cover = (pb.on_hand_units / pb.r28.clip(lower=0.05)).reindex(pd.MultiIndex.from_frame(risk_b[["store_id", "sku_id"]])).to_numpy()
risk_b["rule_of_thumb_alert"] = rule_cover < pb.contract_lead_time_days.reindex(pd.MultiIndex.from_frame(risk_b[["store_id", "sku_id"]])).to_numpy()
risk_b["radar_alert"] = risk_b.risk_tier.isin(["Critical", "High"])
risk_b["as_of_date"] = backtest_origin
(nan_to_null(spark.createDataFrame(risk_b)).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{FQ}.risk_backtest"))


def pr(alert, actual):
    tp = int((alert & actual).sum()); fp = int((alert & ~actual).sum()); fn = int((~alert & actual).sum())
    return {"alerts": int(alert.sum()), "true_positives": tp, "false_positives": fp, "missed_stockouts": fn,
            "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4)}


# Early-warning evaluation: only items that still had stock at the origin (already-empty shelves are known, not predicted)
risk_b["rule_cover_days"] = rule_cover
ev = risk_b[risk_b.on_hand_units > 0].copy()
actual = ev.actual_stockout_in_window.astype(bool)
n_alerts = int(ev.radar_alert.sum())
rule_same_volume = ev.rule_cover_days.rank(method="first") <= n_alerts  # rule ranked by lowest cover, same planner workload
radar_rank = ev.risk_score.rank(ascending=False, method="first")
bt_summary = {
    "backtest_origin": str(backtest_origin), "series_evaluated_with_stock_on_hand": len(ev),
    "series_already_out_of_stock_excluded": int((risk_b.on_hand_units == 0).sum()),
    "actual_stockouts_in_window": int(actual.sum()),
    "radar_critical_high": pr(ev.radar_alert, actual),
    "radar_critical_only": pr(ev.risk_tier.eq("Critical"), actual),
    "rule_of_thumb_cover_lt_leadtime": pr(ev.rule_of_thumb_alert.astype(bool), actual),
    "rule_lowest_cover_same_alert_volume": pr(rule_same_volume, actual),
    "radar_top_500": pr(radar_rank <= 500, actual),
    "rule_top_500_lowest_cover": pr(ev.rule_cover_days.rank(method="first") <= 500, actual),
    "lost_revenue_flagged_by_radar_usd": round(float(ev.loc[ev.radar_alert & actual, "revenue_at_risk"].sum()), 2),
}
print(json.dumps(bt_summary, indent=2))

# COMMAND ----------

summary = {
    "as_of_date": AS_OF, "series_scored": len(risk), "tiers": risk.risk_tier.value_counts().to_dict(),
    "actions": risk.recommended_action.value_counts().to_dict(),
    "primary_drivers_critical_high": risk[risk.risk_tier.isin(["Critical", "High"])].primary_driver.value_counts().to_dict(),
    "revenue_at_risk_critical_high": round(float(risk.loc[risk.risk_tier.isin(["Critical", "High"]), "revenue_at_risk"].sum()), 2),
    "top_15": risk.head(15)[["risk_rank", "store_id", "store_name", "sku_id", "sku_name", "risk_score", "risk_tier", "stockout_probability",
                             "on_hand_units", "forecast_demand_window", "lead_time_window_days", "revenue_at_risk", "primary_driver",
                             "recommended_action", "recommended_qty", "driver_details"]].to_dict(orient="records"),
    "backtest": bt_summary,
}
with open(f"{EVIDENCE}/05b_risk_scoring.json", "w") as fh:
    json.dump(summary, fh, indent=2, default=str)
