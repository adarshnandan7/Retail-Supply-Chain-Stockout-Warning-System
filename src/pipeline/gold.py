"""Gold layer: analytics-ready materialized views that join and aggregate the silver feeds.

These are the governed inputs for forecasting, inventory-risk scoring, AI/BI dashboards and Genie.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql import Window

AS_OF = spark.conf.get("as_of_date")


@dp.materialized_view(name="gold_promo_store_sku_daily",
                      comment="Promotion calendar expanded to one row per date/store/SKU in promotion (history and next 5 weeks).",
                      table_properties={"quality": "gold"})
def gold_promo_store_sku_daily():
    promos = spark.read.table("silver_promotions")
    stores = spark.read.table("silver_stores").select("store_id", "region")
    exploded = promos.withColumn("promo_date", F.explode(F.sequence("start_date", "end_date")))
    joined = exploded.join(stores, (F.col("scope") == "ALL") | (F.col("scope") == F.col("region")))
    return (joined.groupBy("promo_date", "store_id", "sku_id")
            .agg(F.max("discount_pct").alias("discount_pct"), F.first("promo_id").alias("promo_id"),
                 F.first("promo_type").alias("promo_type")))


@dp.materialized_view(name="gold_daily_store_sku_sales",
                      comment="Daily store/SKU fact: units sold, revenue, end-of-day on hand, stockout flag, promo and holiday context. "
                              "Grid comes from inventory snapshots so zero-sales days are explicit.",
                      table_properties={"quality": "gold"},
                      cluster_by=["sku_id", "store_id"])
def gold_daily_store_sku_sales():
    inv = spark.read.table("silver_inventory_snapshots").select(
        F.col("snapshot_date").alias("sale_date"), "store_id", "sku_id", F.col("on_hand_units").alias("eod_on_hand_units"))
    sales = spark.read.table("silver_pos_sales").select("sale_date", "store_id", "sku_id", "units_sold", "net_sales", "unit_price")
    promo = spark.read.table("gold_promo_store_sku_daily").select(
        F.col("promo_date").alias("sale_date"), "store_id", "sku_id", "discount_pct")
    hol = spark.read.table("silver_holidays")
    prod = spark.read.table("silver_products").select("sku_id", "category", F.col("unit_price").alias("list_price"))
    stores = spark.read.table("silver_stores").select("store_id", "region")
    days_to_holiday = (hol.alias("h").crossJoin(inv.select("sale_date").distinct().alias("d"))
                       .where(F.col("h.holiday_date") >= F.col("d.sale_date"))
                       .groupBy("d.sale_date").agg(F.min(F.datediff("h.holiday_date", "d.sale_date")).alias("days_to_next_holiday")))
    return (inv.join(sales, ["sale_date", "store_id", "sku_id"], "left")
            .join(promo, ["sale_date", "store_id", "sku_id"], "left")
            .join(prod, "sku_id", "left").join(stores, "store_id", "left")
            .join(days_to_holiday, "sale_date", "left")
            .select("sale_date", "store_id", "region", "sku_id", "category",
                    F.coalesce("units_sold", F.lit(0)).alias("units_sold"),
                    F.coalesce("net_sales", F.lit(0)).cast("decimal(12,2)").alias("net_sales"),
                    F.coalesce("unit_price", (F.col("list_price") * (1 - F.coalesce("discount_pct", F.lit(0))))).cast("decimal(10,2)").alias("unit_price"),
                    F.col("discount_pct").isNotNull().alias("on_promo"),
                    F.coalesce("discount_pct", F.lit(0.0)).alias("discount_pct"),
                    "eod_on_hand_units",
                    (F.col("eod_on_hand_units") == 0).alias("is_stockout"),
                    F.coalesce("days_to_next_holiday", F.lit(99)).alias("days_to_next_holiday")))


@dp.materialized_view(name="gold_po_lines",
                      comment="One row per purchase-order line with ordered/received quantities, expected vs actual delivery, lateness and status.",
                      table_properties={"quality": "gold"})
def gold_po_lines():
    ev = spark.read.table("silver_po_events")
    created = ev.where("event_type = 'PO_CREATED'").select(
        "po_line_id", "store_id", "sku_id", "supplier_id", "order_qty", "expected_delivery_date",
        F.to_date("event_ts").alias("order_date"))
    received = ev.where("event_type = 'PO_RECEIVED'").groupBy("po_line_id").agg(
        F.min(F.to_date("event_ts")).alias("received_date"), F.sum("received_qty").alias("received_qty"))
    return (created.join(received, "po_line_id", "left")
            .withColumn("status", F.when(F.col("received_date").isNull(), "OPEN").otherwise("RECEIVED"))
            .withColumn("actual_lead_time_days", F.datediff("received_date", "order_date"))
            .withColumn("days_late", F.greatest(F.lit(0), F.datediff("received_date", "expected_delivery_date")))
            .withColumn("days_overdue_as_of", F.when(F.col("status") == "OPEN",
                        F.greatest(F.lit(0), F.datediff(F.lit(AS_OF).cast("date"), "expected_delivery_date"))))
            .withColumn("is_late", F.col("days_late") > 0))


@dp.materialized_view(name="gold_supplier_lead_time_stats",
                      comment="Supplier delivery performance: contract vs actual lead time (avg, p90), on-time rate overall and last 30 days.",
                      table_properties={"quality": "gold"})
def gold_supplier_lead_time_stats():
    lines = spark.read.table("gold_po_lines")
    rec = lines.where("status = 'RECEIVED'")
    recent = F.col("received_date") > F.date_sub(F.lit(AS_OF).cast("date"), 30)
    stats = rec.groupBy("supplier_id").agg(
        F.count("*").alias("received_lines"),
        F.round(F.avg("actual_lead_time_days"), 2).alias("avg_actual_lead_time_days"),
        F.percentile_approx("actual_lead_time_days", 0.9).alias("p90_actual_lead_time_days"),
        F.round(1 - F.avg(F.col("is_late").cast("int")), 4).alias("on_time_rate"),
        F.round(1 - F.avg(F.when(recent, F.col("is_late").cast("int"))), 4).alias("on_time_rate_last_30d"),
        F.round(F.avg(F.when(recent & F.col("is_late"), F.col("days_late"))), 2).alias("avg_days_late_when_late_last_30d"),
        F.round(F.avg(F.when(recent, F.col("days_late"))), 2).alias("avg_days_late_last_30d"))
    open_ = lines.where("status = 'OPEN'").groupBy("supplier_id").agg(
        F.count("*").alias("open_lines"), F.sum(F.when(F.col("days_overdue_as_of") > 0, 1).otherwise(0)).alias("overdue_open_lines"))
    sup = spark.read.table("silver_suppliers").select("supplier_id", "supplier_name", "primary_category", "contract_lead_time_days")
    return sup.join(stats, "supplier_id", "left").join(open_, "supplier_id", "left").fillna(0, ["open_lines", "overdue_open_lines"])


@dp.materialized_view(name="gold_inbound_po_pipeline",
                      comment="Open purchase-order lines with projected arrival date adjusted for the supplier's recent lateness.",
                      table_properties={"quality": "gold"})
def gold_inbound_po_pipeline():
    lines = spark.read.table("gold_po_lines").where("status = 'OPEN'")
    sup = spark.read.table("gold_supplier_lead_time_stats").select("supplier_id", "supplier_name", "on_time_rate_last_30d", "avg_days_late_last_30d")
    as_of = F.lit(AS_OF).cast("date")
    return (lines.join(sup, "supplier_id", "left")
            .withColumn("expected_delay_days", F.ceil(F.coalesce("avg_days_late_last_30d", F.lit(0))).cast("int"))
            .withColumn("projected_arrival_date",
                        F.greatest(F.date_add("expected_delivery_date", F.col("expected_delay_days")), F.date_add(as_of, 1)))
            .withColumn("projected_days_until_arrival", F.datediff("projected_arrival_date", as_of))
            .select("po_line_id", "store_id", "sku_id", "supplier_id", "supplier_name", "order_date", "order_qty",
                    "expected_delivery_date", "days_overdue_as_of", "on_time_rate_last_30d", "expected_delay_days",
                    "projected_arrival_date", "projected_days_until_arrival"))


@dp.materialized_view(name="gold_current_inventory_position",
                      comment="As-of inventory position per store/SKU: on hand, inbound units and timing, trailing demand, days of cover, recent stockout days.",
                      table_properties={"quality": "gold"})
def gold_current_inventory_position():
    as_of = F.lit(AS_OF).cast("date")
    daily = spark.read.table("gold_daily_store_sku_sales")
    last28 = daily.where((F.col("sale_date") > F.date_sub(as_of, 28)) & (F.col("sale_date") <= as_of)).groupBy("store_id", "sku_id").agg(
        F.round(F.avg("units_sold"), 3).alias("avg_daily_units_28d"),
        F.sum(F.col("is_stockout").cast("int")).alias("stockout_days_28d"),
        F.sum("net_sales").alias("net_sales_28d"))
    current = daily.where(F.col("sale_date") == as_of).select("store_id", "region", "sku_id", "category", "eod_on_hand_units")
    inbound = spark.read.table("gold_inbound_po_pipeline").groupBy("store_id", "sku_id").agg(
        F.sum("order_qty").alias("inbound_units"), F.count("*").alias("open_po_lines"),
        F.min("projected_arrival_date").alias("next_projected_arrival_date"),
        F.max("days_overdue_as_of").alias("max_days_overdue"))
    prod = spark.read.table("silver_products").select("sku_id", "sku_name", "supplier_id", "unit_price", "unit_cost", "is_perishable", "case_pack")
    return (current.join(last28, ["store_id", "sku_id"], "left").join(inbound, ["store_id", "sku_id"], "left")
            .join(prod, "sku_id", "left")
            .fillna(0, ["inbound_units", "open_po_lines", "max_days_overdue"])
            .withColumn("as_of_date", as_of)
            .withColumn("days_of_cover", F.round(F.col("eod_on_hand_units") / F.greatest(F.col("avg_daily_units_28d"), F.lit(0.05)), 1)))
