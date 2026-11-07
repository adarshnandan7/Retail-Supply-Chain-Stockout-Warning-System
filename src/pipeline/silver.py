"""Silver layer: typed, validated, de-duplicated records.

Append-only event feeds stay streaming tables; master data is published as materialized views so
late corrections in the source are reflected on refresh. Data-quality rules are enforced with
expectations and are visible in the pipeline event log.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.table(name="silver_pos_sales", comment="Validated POS daily sales: one row per date/store/SKU, duplicates and invalid rows removed.",
          table_properties={"quality": "silver"})
@dp.expect_or_drop("sku_present", "sku_id IS NOT NULL")
@dp.expect_or_drop("store_present", "store_id IS NOT NULL")
@dp.expect_or_drop("non_negative_units", "units_sold >= 0")
@dp.expect("price_positive", "unit_price > 0")
def silver_pos_sales():
    return (
        spark.readStream.table("bronze_pos_sales")
        .select(
            F.to_date("sale_date").alias("sale_date"), "store_id", "sku_id", "units_sold",
            F.col("unit_price").cast("decimal(10,2)").alias("unit_price"),
            F.col("net_sales").cast("decimal(12,2)").alias("net_sales"),
            (F.col("on_promo") == 1).alias("on_promo"),
            F.to_timestamp("pos_batch_ts").alias("pos_batch_ts"), "_source_file",
        )
        .withWatermark("pos_batch_ts", "3 days")
        .dropDuplicatesWithinWatermark(["sale_date", "store_id", "sku_id"])
    )


@dp.table(name="silver_inventory_snapshots", comment="Validated end-of-day on-hand units per store/SKU.",
          table_properties={"quality": "silver"})
@dp.expect_or_drop("non_negative_on_hand", "on_hand_units >= 0")
@dp.expect_or_drop("keys_present", "store_id IS NOT NULL AND sku_id IS NOT NULL")
def silver_inventory_snapshots():
    return spark.readStream.table("bronze_inventory_snapshots").select(
        F.to_date("snapshot_date").alias("snapshot_date"), "store_id", "sku_id", "on_hand_units", "source_system"
    )


@dp.table(name="silver_po_events", comment="Validated purchase-order lifecycle events.", table_properties={"quality": "silver"})
@dp.expect_or_drop("po_line_present", "po_line_id IS NOT NULL")
@dp.expect_or_drop("created_has_qty", "event_type <> 'PO_CREATED' OR order_qty > 0")
@dp.expect("received_has_qty", "event_type <> 'PO_RECEIVED' OR received_qty > 0")
def silver_po_events():
    return spark.readStream.table("bronze_po_events").select(
        "event_id", "event_type", F.to_timestamp("event_ts").alias("event_ts"), "po_line_id", "store_id", "sku_id",
        "supplier_id", "order_qty", F.to_date("expected_delivery_date").alias("expected_delivery_date"), "received_qty",
    )


@dp.materialized_view(name="silver_products", comment="Product master (one row per SKU).", table_properties={"quality": "silver"})
@dp.expect_or_fail("unique_sku", "sku_id IS NOT NULL")
def silver_products():
    return (spark.read.table("bronze_products").drop("_rescued_data", "_source_file", "_ingested_at")
            .withColumn("unit_price", F.col("unit_price").cast("decimal(10,2)"))
            .withColumn("unit_cost", F.col("unit_cost").cast("decimal(10,2)"))
            .dropDuplicates(["sku_id"]))


@dp.materialized_view(name="silver_stores", comment="Store master (one row per store).", table_properties={"quality": "silver"})
def silver_stores():
    return (spark.read.table("bronze_stores").drop("_rescued_data", "_source_file", "_ingested_at", "size_band")
            .withColumn("opened_date", F.to_date("opened_date")).dropDuplicates(["store_id"]))


@dp.materialized_view(name="silver_suppliers", comment="Supplier master with contract lead times.", table_properties={"quality": "silver"})
@dp.expect("lead_time_positive", "contract_lead_time_days > 0")
def silver_suppliers():
    return spark.read.table("bronze_suppliers").drop("_rescued_data", "_source_file", "_ingested_at").dropDuplicates(["supplier_id"])


@dp.materialized_view(name="silver_promotions", comment="Promotion calendar (historical and planned).", table_properties={"quality": "silver"})
@dp.expect_or_drop("valid_window", "end_date >= start_date")
def silver_promotions():
    return (spark.read.table("bronze_promotions").drop("_rescued_data", "_source_file", "_ingested_at")
            .withColumn("start_date", F.to_date("start_date")).withColumn("end_date", F.to_date("end_date"))
            .dropDuplicates(["promo_id"]))


@dp.materialized_view(name="silver_holidays", comment="Holiday calendar.", table_properties={"quality": "silver"})
def silver_holidays():
    return spark.read.table("bronze_holidays").select(F.to_date("holiday_date").alias("holiday_date"), "holiday_name").dropDuplicates()
