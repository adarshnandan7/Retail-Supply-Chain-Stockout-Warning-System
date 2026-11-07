"""Feature engineering shared by training and batch forecasting.

Direct multi-horizon design: for a forecast origin date `o` (last day with known sales) and each
target date `o + h` (h = 1..HORIZON) we build one row per store/SKU with
  * history features computed only from data <= o (no leakage), and
  * calendar features known in advance for the target date (weekday, planned promotion, holiday proximity).
One global LightGBM model learns across all 20,000 store/SKU series and all horizons.

Days that ended in a stockout (on hand = 0) are censored demand: sales understate what customers
wanted. They are excluded from history averages and from training/evaluation labels.
"""
from datetime import date, timedelta

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

HORIZON = 28
CATEGORIES = ["Fresh Produce", "Dairy & Eggs", "Bakery", "Meat & Seafood", "Frozen", "Pantry & Baking",
              "Beverages", "Snacks", "Household", "Personal Care"]
HOLIDAYS = ["Thanksgiving", "Christmas", "New Year", "Easter", "Memorial Day", "Independence Day", "Labor Day"]

FEATURES = [
    "horizon", "target_dow", "discount_pct", "on_promo", "days_to_next_holiday", "next_holiday_code",
    "category_code", "is_perishable", "unit_price", "r7", "r28", "sn4_dow", "r28_std", "stockout_days_28",
    "promo_ratio_sku", "store_scale", "hol_ratio_sku",
]
CATEGORICAL = ["target_dow", "next_holiday_code", "category_code"]


def holiday_calendar(spark: SparkSession, fq: str, start: date, end: date) -> DataFrame:
    """Per calendar date: days to the next holiday (capped at 30) and which holiday it is."""
    hol = spark.table(f"{fq}.silver_holidays").toPandas()
    hol["holiday_date"] = pd.to_datetime(hol["holiday_date"])
    hol = hol.sort_values("holiday_date")
    rows = []
    d = pd.Timestamp(start)
    while d <= pd.Timestamp(end):
        nxt = hol[hol.holiday_date >= d].head(1)
        if len(nxt):
            dd = int((nxt.holiday_date.iloc[0] - d).days)
            name = nxt.holiday_name.iloc[0]
        else:
            dd, name = 99, "None"
        code = HOLIDAYS.index(name) + 1 if (name in HOLIDAYS and dd <= 30) else 0
        rows.append((d.date(), min(dd, 30), code))
        d += pd.Timedelta(days=1)
    return spark.createDataFrame(pd.DataFrame(rows, columns=["target_date", "days_to_next_holiday", "next_holiday_code"]))


def history_features(spark: SparkSession, fq: str, origin: date) -> DataFrame:
    """Store/SKU history features as of `origin` (inclusive)."""
    daily = spark.table(f"{fq}.gold_daily_store_sku_sales")
    o = F.lit(origin.isoformat()).cast("date")
    clean_units = F.when(~F.col("is_stockout"), F.col("units_sold"))
    w28 = daily.where((F.col("sale_date") > F.date_sub(o, 28)) & (F.col("sale_date") <= o))
    agg = w28.groupBy("store_id", "sku_id").agg(
        F.avg(F.when(F.col("sale_date") > F.date_sub(o, 7), clean_units)).alias("r7"),
        F.avg(clean_units).alias("r28"),
        F.stddev(clean_units).alias("r28_std"),
        F.sum(F.col("is_stockout").cast("int")).alias("stockout_days_28"),
    )
    dow = (w28.withColumn("target_dow", F.dayofweek("sale_date"))
           .groupBy("store_id", "sku_id", "target_dow").agg(F.avg(clean_units).alias("sn4_dow")))
    # one-year promo and holiday-ramp response per SKU (chain level, robust to sparse store history)
    w365 = daily.where((F.col("sale_date") > F.date_sub(o, 365)) & (F.col("sale_date") <= o) & ~F.col("is_stockout"))
    promo_ratio = w365.groupBy("sku_id").agg(
        (F.avg(F.when(F.col("on_promo"), F.col("units_sold"))) /
         F.greatest(F.avg(F.when(~F.col("on_promo"), F.col("units_sold"))), F.lit(0.01))).alias("promo_ratio_sku"),
        (F.avg(F.when(F.col("days_to_next_holiday") <= 6, F.col("units_sold"))) /
         F.greatest(F.avg(F.when(F.col("days_to_next_holiday") > 14, F.col("units_sold"))), F.lit(0.01))).alias("hol_ratio_sku"),
    )
    store_scale = (w365.groupBy("store_id").agg(F.avg("units_sold").alias("s"))
                   .crossJoin(w365.agg(F.avg("units_sold").alias("chain")))
                   .select("store_id", (F.col("s") / F.col("chain")).alias("store_scale")))
    prod = spark.table(f"{fq}.silver_products").select(
        "sku_id", "category", F.col("is_perishable").cast("int").alias("is_perishable"),
        F.col("unit_price").cast("double").alias("unit_price"))
    cat_map = F.create_map(*[x for i, c in enumerate(CATEGORIES) for x in (F.lit(c), F.lit(i))])
    return (agg.join(promo_ratio, "sku_id", "left").join(store_scale, "store_id", "left").join(prod, "sku_id", "left")
            .withColumn("category_code", cat_map[F.col("category")])
            .withColumn("forecast_origin", o)
            .join(dow, ["store_id", "sku_id"], "left")
            .fillna({"promo_ratio_sku": 1.0, "hol_ratio_sku": 1.0, "store_scale": 1.0, "r28_std": 0.0}))


def target_frame(spark: SparkSession, fq: str, origin: date, with_actuals: bool) -> DataFrame:
    """Target dates o+1..o+HORIZON per store/SKU with planned promo and holiday context."""
    o = F.lit(origin.isoformat()).cast("date")
    series = spark.table(f"{fq}.gold_current_inventory_position").select("store_id", "sku_id", "region")
    dates = spark.range(1, HORIZON + 1).select(F.col("id").cast("int").alias("horizon")).withColumn(
        "target_date", F.date_add(o, F.col("horizon")))
    promo = spark.table(f"{fq}.gold_promo_store_sku_daily").select(
        F.col("promo_date").alias("target_date"), "store_id", "sku_id", "discount_pct")
    cal = holiday_calendar(spark, fq, origin + timedelta(days=1), origin + timedelta(days=HORIZON))
    t = (series.crossJoin(dates).join(promo, ["target_date", "store_id", "sku_id"], "left")
         .join(cal, "target_date", "left")
         .withColumn("discount_pct", F.coalesce("discount_pct", F.lit(0.0)))
         .withColumn("on_promo", (F.col("discount_pct") > 0).cast("int"))
         .withColumn("target_dow", F.dayofweek("target_date")))
    if with_actuals:
        act = spark.table(f"{fq}.gold_daily_store_sku_sales").select(
            F.col("sale_date").alias("target_date"), "store_id", "sku_id", "units_sold", "is_stockout")
        t = t.join(act, ["target_date", "store_id", "sku_id"], "inner")
    return t


def build_frame(spark: SparkSession, fq: str, origin: date, with_actuals: bool, series_fraction: float = 1.0) -> DataFrame:
    hist = history_features(spark, fq, origin)
    tgt = target_frame(spark, fq, origin, with_actuals)
    if series_fraction < 1.0:
        keep = hist.select("store_id", "sku_id").distinct().sample(fraction=series_fraction, seed=origin.toordinal())
        tgt = tgt.join(keep, ["store_id", "sku_id"])
    df = tgt.join(hist, ["store_id", "sku_id", "target_dow"], "left")
    for c in ["r7", "r28", "sn4_dow"]:
        df = df.withColumn(c, F.coalesce(F.col(c), F.col("r28"), F.lit(0.0)))
    return df


def seasonal_naive(pdf: pd.DataFrame) -> pd.Series:
    """Baseline most grocers already run: same-weekday average of the last 4 weeks, no promo/holiday awareness."""
    return pdf["sn4_dow"].fillna(pdf["r28"]).fillna(0.0)


def wape(actual, pred) -> float:
    actual = pd.Series(actual).astype(float)
    return float((actual - pd.Series(pred, index=actual.index)).abs().sum() / max(actual.sum(), 1e-9))


def bias(actual, pred) -> float:
    actual = pd.Series(actual).astype(float)
    return float((pd.Series(pred, index=actual.index) - actual).sum() / max(actual.sum(), 1e-9))
