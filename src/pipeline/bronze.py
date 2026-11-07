"""Bronze layer: incremental, append-only ingestion of raw source-system file drops with Auto Loader.

Every table is a streaming table so new monthly drops are picked up incrementally (exactly once) and
lineage back to the landing file is kept in `_source_file` / `_ingested_at`.
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

LANDING = spark.conf.get("landing_path")

SCHEMAS = {
    "sales": "sale_date STRING, store_id STRING, sku_id STRING, units_sold INT, unit_price DOUBLE, net_sales DOUBLE, on_promo INT, pos_batch_ts STRING",
    "inventory": "snapshot_date STRING, store_id STRING, sku_id STRING, on_hand_units INT, source_system STRING",
    "purchase_orders": "event_id STRING, event_type STRING, event_ts STRING, po_line_id STRING, store_id STRING, sku_id STRING, supplier_id STRING, order_qty INT, expected_delivery_date STRING, received_qty INT",
    "products": "sku_id STRING, sku_name STRING, category STRING, subcategory STRING, brand STRING, is_perishable BOOLEAN, shelf_life_days INT, unit_price DOUBLE, unit_cost DOUBLE, case_pack INT, supplier_id STRING",
    "stores": "store_id STRING, store_name STRING, region STRING, format STRING, opened_date STRING, size_band STRING",
    "suppliers": "supplier_id STRING, supplier_name STRING, primary_category STRING, contract_lead_time_days INT, on_time_rate_target DOUBLE, mean_delay_when_late_days DOUBLE, min_order_cases INT",
    "promotions": "promo_id STRING, sku_id STRING, scope STRING, start_date STRING, end_date STRING, discount_pct DOUBLE, promo_type STRING, planned_uplift_hint DOUBLE",
    "calendar": "holiday_date STRING, holiday_name STRING",
}


def autoload(folder: str, fmt: str):
    reader = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", fmt)
        .option("rescuedDataColumn", "_rescued_data")
        .schema(SCHEMAS[folder])
    )
    if fmt == "csv":
        reader = reader.option("header", "true")
    return (
        reader.load(f"{LANDING}/{folder}/")
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_ingested_at", F.current_timestamp())
    )


@dp.table(name="bronze_pos_sales", comment="Raw POS daily store-SKU sales drops (CSV, monthly files). Append-only.",
          table_properties={"quality": "bronze"})
def bronze_pos_sales():
    return autoload("sales", "csv")


@dp.table(name="bronze_inventory_snapshots", comment="Raw end-of-day on-hand snapshots from store inventory management (JSON). Append-only.",
          table_properties={"quality": "bronze"})
def bronze_inventory_snapshots():
    return autoload("inventory", "json")


@dp.table(name="bronze_po_events", comment="Raw purchase-order lifecycle events from ERP purchasing (PO_CREATED / PO_RECEIVED). Append-only.",
          table_properties={"quality": "bronze"})
def bronze_po_events():
    return autoload("purchase_orders", "json")


@dp.table(name="bronze_products", comment="Raw product master from merchandising.", table_properties={"quality": "bronze"})
def bronze_products():
    return autoload("products", "csv")


@dp.table(name="bronze_stores", comment="Raw store master from store operations.", table_properties={"quality": "bronze"})
def bronze_stores():
    return autoload("stores", "csv")


@dp.table(name="bronze_suppliers", comment="Raw supplier master with contract lead times.", table_properties={"quality": "bronze"})
def bronze_suppliers():
    return autoload("suppliers", "csv")


@dp.table(name="bronze_promotions", comment="Raw promotion calendar from marketing, including planned future promotions.",
          table_properties={"quality": "bronze"})
def bronze_promotions():
    return autoload("promotions", "csv")


@dp.table(name="bronze_holidays", comment="Raw holiday calendar.", table_properties={"quality": "bronze"})
def bronze_holidays():
    return autoload("calendar", "csv")
