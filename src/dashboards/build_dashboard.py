"""Generate the AI/BI dashboard definition (inventory_risk.lvdash.json) from readable Python.

Run: python src/dashboards/build_dashboard.py [catalog] [schema]
The bundle (resources/dashboard.yml) deploys the generated file.
"""
import json
import sys
from pathlib import Path

CATALOG = sys.argv[1] if len(sys.argv) > 1 else "serverless_stable_3vku19_catalog"
SCHEMA = sys.argv[2] if len(sys.argv) > 2 else "inventory_risk"
FQ = f"{CATALOG}.{SCHEMA}"

DATASETS = {
    "ds_risk": ("Risk queue", f"""
SELECT risk_rank, risk_tier, risk_score, region, store_name, category, sku_name, supplier_name, on_hand_units,
       inbound_units_in_window, ROUND(forecast_demand_window, 0) AS forecast_demand_window, lead_time_window_days,
       projected_stockout_in_days, stockout_probability, revenue_at_risk, primary_driver, recommended_action, recommended_qty,
       planner_explanation, CASE WHEN projected_stockout_in_days <= 3 THEN 1 ELSE 0 END AS out_within_3d, as_of_date
FROM {FQ}.risk_recommendations
WHERE risk_tier IN ('Critical', 'High')
ORDER BY risk_rank"""),
    "ds_cover": ("Inventory cover", f"""
SELECT region, category,
       CASE WHEN days_of_cover < 3 THEN '1: <3 days' WHEN days_of_cover < 7 THEN '2: 3-7 days' WHEN days_of_cover < 14 THEN '3: 7-14 days'
            WHEN days_of_cover <= 45 THEN '4: 14-45 days' ELSE '5: >45 days (excess)' END AS cover_band,
       COUNT(*) AS store_skus
FROM {FQ}.risk_recommendations GROUP BY ALL"""),
    "ds_wape_overall": ("Forecast accuracy", f"""
SELECT MEASURE(model_wape) AS model_wape, MEASURE(baseline_wape) AS baseline_wape, MEASURE(wape_improvement_pct) / 100 AS wape_improvement,
       MEASURE(model_bias) AS model_bias
FROM {FQ}.mv_forecast_accuracy"""),
    "ds_wape_category": ("WAPE by category", f"""
SELECT category, 'Champion model' AS forecast, MEASURE(model_wape) AS wape FROM {FQ}.mv_forecast_accuracy GROUP BY category
UNION ALL
SELECT category, 'Seasonal naive (today)' AS forecast, MEASURE(baseline_wape) AS wape FROM {FQ}.mv_forecast_accuracy GROUP BY category"""),
    "ds_wape_promo": ("WAPE promo vs regular", f"""
SELECT on_promo AS day_type, 'Champion model' AS forecast, MEASURE(model_wape) AS wape FROM {FQ}.mv_forecast_accuracy GROUP BY on_promo
UNION ALL
SELECT on_promo AS day_type, 'Seasonal naive (today)' AS forecast, MEASURE(baseline_wape) AS wape FROM {FQ}.mv_forecast_accuracy GROUP BY on_promo"""),
    "ds_stockout_trend": ("Stockout rate trend", f"""
SELECT sale_week, region, MEASURE(stockout_rate) AS stockout_rate
FROM {FQ}.mv_stockout_history WHERE sale_week >= '2025-11-01' GROUP BY ALL"""),
    "ds_alert_quality": ("Alert quality backtest", f"""
SELECT 'Risk radar (Critical+High)' AS method, MEASURE(radar_alerts) AS alerts, MEASURE(radar_alert_precision) AS precision, MEASURE(radar_alert_recall) AS recall
FROM {FQ}.mv_alert_backtest
UNION ALL
SELECT 'Rule of thumb (cover < lead time)', MEASURE(rule_alerts), MEASURE(rule_alert_precision), MEASURE(rule_alert_recall)
FROM {FQ}.mv_alert_backtest"""),
    "ds_supplier": ("Supplier performance", f"""
SELECT supplier_name, primary_category, contract_lead_time_days, avg_actual_lead_time_days, on_time_rate_last_30d, open_lines, overdue_open_lines
FROM {FQ}.gold_supplier_lead_time_stats ORDER BY on_time_rate_last_30d"""),
}

CUR = {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 1}}
PCT = {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 1}}


def text(name, line, x, y, w, h=1):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [line]}}, "position": {"x": x, "y": y, "width": w, "height": h}}


def counter(name, ds, expr_name, expr, title, x, y, w=3, fmt=None, disagg=False):
    enc = {"fieldName": expr_name, "displayName": title}
    if fmt:
        enc["format"] = fmt
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [{"name": expr_name, "expression": expr}], "disaggregated": disagg}}],
                       "spec": {"version": 2, "widgetType": "counter", "encodings": {"value": enc}, "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": 3}}


def bar(name, ds, fields, x_enc, y_enc, color, title, x, y, w=6, h=6, group=False):
    spec = {"version": 3, "widgetType": "bar", "encodings": {"x": x_enc, "y": y_enc}, "frame": {"showTitle": True, "title": title}}
    if color:
        spec["encodings"]["color"] = color
    if group:
        spec["mark"] = {"layout": "group"}
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": fields, "disaggregated": False}}], "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def table(name, ds, cols, title, x, y, w=12, h=8):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [{"name": c, "expression": f"`{c}`"} for c, _ in cols], "disaggregated": True}}],
                       "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [{"fieldName": c, "displayName": d} for c, d in cols]},
                                "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def mfilter(name, ds_fields, title, x, y, w):
    qs = [{"name": f"{name}_{ds}", "query": {"datasetName": ds, "fields": [{"name": f, "expression": f"`{f}`"}], "disaggregated": False}} for ds, f in ds_fields]
    return {"widget": {"name": name, "queries": qs,
                       "spec": {"version": 2, "widgetType": "filter-multi-select",
                                "encodings": {"fields": [{"fieldName": f, "displayName": title, "queryName": f"{name}_{ds}"} for ds, f in ds_fields]},
                                "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": 2}}


q = lambda n, e: {"name": n, "expression": e}

page1 = [
    text("title", "## Harvest Lane Markets - Inventory Risk Radar", 0, 0, 12),
    text("subtitle", "Store/SKUs likely to stock out before replenishment arrives, ranked by risk and revenue at risk. Planners decide; nothing is ordered automatically.", 0, 1, 12),
    mfilter("f_region", [("ds_risk", "region"), ("ds_cover", "region")], "Region", 0, 2, 4),
    mfilter("f_category", [("ds_risk", "category"), ("ds_cover", "category")], "Category", 4, 2, 4),
    mfilter("f_tier", [("ds_risk", "risk_tier")], "Risk tier", 8, 2, 4),
    counter("k_alerts", "ds_risk", "count(risk_rank)", "COUNT(`risk_rank`)", "Critical + High alerts", 0, 4),
    counter("k_revenue", "ds_risk", "sum(revenue_at_risk)", "SUM(`revenue_at_risk`)", "Revenue at risk", 3, 4, fmt=CUR),
    counter("k_out3", "ds_risk", "sum(out_within_3d)", "SUM(`out_within_3d`)", "Projected out within 3 days", 6, 4),
    counter("k_prob", "ds_risk", "avg(stockout_probability)", "AVG(`stockout_probability`)", "Avg stockout probability", 9, 4, fmt=PCT),
    bar("c_region_tier", "ds_risk", [q("region", "`region`"), q("risk_tier", "`risk_tier`"), q("sum(revenue_at_risk)", "SUM(`revenue_at_risk`)")],
        {"fieldName": "region", "scale": {"type": "categorical"}, "displayName": "Region"},
        {"fieldName": "sum(revenue_at_risk)", "scale": {"type": "quantitative"}, "displayName": "Revenue at risk", "format": CUR},
        {"fieldName": "risk_tier", "scale": {"type": "categorical"}, "displayName": "Tier"}, "Revenue at risk by region and tier", 0, 7),
    bar("c_driver", "ds_risk", [q("primary_driver", "`primary_driver`"), q("count(risk_rank)", "COUNT(`risk_rank`)")],
        {"fieldName": "count(risk_rank)", "scale": {"type": "quantitative"}, "displayName": "Alerts"},
        {"fieldName": "primary_driver", "scale": {"type": "categorical", "sort": {"by": "x-reversed"}}, "displayName": "Primary driver"},
        None, "Why items are at risk (primary driver)", 6, 7),
    bar("c_action", "ds_risk", [q("recommended_action", "`recommended_action`"), q("count(risk_rank)", "COUNT(`risk_rank`)")],
        {"fieldName": "recommended_action", "scale": {"type": "categorical"}, "displayName": "Suggested action"},
        {"fieldName": "count(risk_rank)", "scale": {"type": "quantitative"}, "displayName": "Alerts"}, None, "Suggested planner actions", 0, 13),
    bar("c_cover", "ds_cover", [q("cover_band", "`cover_band`"), q("sum(store_skus)", "SUM(`store_skus`)")],
        {"fieldName": "cover_band", "scale": {"type": "categorical"}, "displayName": "Days of cover"},
        {"fieldName": "sum(store_skus)", "scale": {"type": "quantitative"}, "displayName": "Store/SKUs"}, None, "Inventory cover across all store/SKUs (shortage to excess)", 6, 13),
    table("t_queue", "ds_risk", [("risk_rank", "#"), ("risk_tier", "Tier"), ("risk_score", "Score"), ("store_name", "Store"), ("sku_name", "Item"),
                                 ("on_hand_units", "On hand"), ("forecast_demand_window", "Forecast (window)"), ("lead_time_window_days", "Window (d)"),
                                 ("projected_stockout_in_days", "Out in (d)"), ("revenue_at_risk", "Revenue at risk"), ("primary_driver", "Driver"),
                                 ("recommended_action", "Action"), ("recommended_qty", "Qty"), ("planner_explanation", "Planner note")],
          "Ranked exceptions", 0, 19, h=9),
]

page2 = [
    text("title2", "## Forecast accuracy, availability and alert quality", 0, 0, 12),
    text("subtitle2", "Holdout: last 28 days, every store/SKU and horizon. Stockout days excluded (censored demand). Backtest: risk scored 4 weeks ago vs what actually happened.", 0, 1, 12),
    counter("k_model_wape", "ds_wape_overall", "model_wape", "`model_wape`", "Model WAPE (lower is better)", 0, 2, w=3, fmt=PCT, disagg=True),
    counter("k_base_wape", "ds_wape_overall", "baseline_wape", "`baseline_wape`", "Baseline WAPE (today's method)", 3, 2, w=3, fmt=PCT, disagg=True),
    counter("k_improve", "ds_wape_overall", "wape_improvement", "`wape_improvement`", "Forecast error reduction", 6, 2, w=3, fmt=PCT, disagg=True),
    counter("k_bias", "ds_wape_overall", "model_bias", "`model_bias`", "Model bias", 9, 2, w=3, fmt=PCT, disagg=True),
    bar("c_wape_cat", "ds_wape_category", [q("category", "`category`"), q("forecast", "`forecast`"), q("sum(wape)", "SUM(`wape`)")],
        {"fieldName": "category", "scale": {"type": "categorical"}, "displayName": "Category"},
        {"fieldName": "sum(wape)", "scale": {"type": "quantitative"}, "displayName": "WAPE", "format": PCT},
        {"fieldName": "forecast", "scale": {"type": "categorical"}, "displayName": "Forecast"}, "Forecast error by category", 0, 5, group=True),
    bar("c_wape_promo", "ds_wape_promo", [q("day_type", "`day_type`"), q("forecast", "`forecast`"), q("sum(wape)", "SUM(`wape`)")],
        {"fieldName": "day_type", "scale": {"type": "categorical"}, "displayName": "Day type"},
        {"fieldName": "sum(wape)", "scale": {"type": "quantitative"}, "displayName": "WAPE", "format": PCT},
        {"fieldName": "forecast", "scale": {"type": "categorical"}, "displayName": "Forecast"}, "Forecast error on promotion vs regular days", 6, 5, group=True),
    {"widget": {"name": "c_stockout_trend", "queries": [{"name": "main_query", "query": {"datasetName": "ds_stockout_trend", "fields": [
        q("sale_week", "`sale_week`"), q("region", "`region`"), q("avg(stockout_rate)", "AVG(`stockout_rate`)")], "disaggregated": False}}],
                "spec": {"version": 3, "widgetType": "line", "encodings": {
                    "x": {"fieldName": "sale_week", "scale": {"type": "temporal"}, "displayName": "Week"},
                    "y": {"fieldName": "avg(stockout_rate)", "scale": {"type": "quantitative"}, "displayName": "Stockout rate", "format": PCT},
                    "color": {"fieldName": "region", "scale": {"type": "categorical"}, "displayName": "Region"}},
                    "frame": {"showTitle": True, "title": "Weekly stockout rate (share of store/SKU/days ending at zero on hand)"}}},
     "position": {"x": 0, "y": 11, "width": 12, "height": 6}},
    table("t_alert_quality", "ds_alert_quality", [("method", "Method"), ("alerts", "Alerts"), ("precision", "Precision"), ("recall", "Recall")],
          "Alert quality (4-week backtest, items with stock on hand)", 0, 17, w=6, h=5),
    table("t_supplier", "ds_supplier", [("supplier_name", "Supplier"), ("primary_category", "Category"), ("contract_lead_time_days", "Contract LT"),
                                        ("avg_actual_lead_time_days", "Actual LT"), ("on_time_rate_last_30d", "On-time 30d"),
                                        ("overdue_open_lines", "Overdue lines")], "Supplier delivery performance", 6, 17, w=6, h=5),
]

dashboard = {
    "datasets": [{"name": n, "displayName": d, "queryLines": [l + "\n" for l in sql.strip().splitlines()]} for n, (d, sql) in DATASETS.items()],
    "pages": [
        {"name": "risk_overview", "displayName": "Risk radar", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": page1},
        {"name": "accuracy", "displayName": "Forecast & alert quality", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": page2},
    ],
}
out = Path(__file__).parent / "inventory_risk.lvdash.json"
out.write_text(json.dumps(dashboard, indent=2))
print(f"wrote {out}: {len(DATASETS)} datasets, {len(page1) + len(page2)} widgets")
if "--print-sql" in sys.argv:
    for n, (_, s) in DATASETS.items():
        print(f"--- {n}\n{s.strip()}")
