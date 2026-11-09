# Backtest: would the radar have warned planners 4 weeks ago?

_Captured 2026-11-09 13:27 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

Risk scored as of **2026-10-09** using only information available that day, then compared with what actually happened (end-of-day on hand = 0 within the item's replenishment window). Items already out of stock at the origin are excluded (630); 19,367 store/SKUs evaluated, 1,909 actually stocked out.

| Method | Alerts | True positives | False positives | Missed | Precision | Recall |
|---|---|---|---|---|---|---|
| radar_critical_high | 1172 | 732 | 440 | 1177 | 62.5% | 38.3% |
| radar_critical_only | 472 | 337 | 135 | 1572 | 71.4% | 17.6% |
| rule_of_thumb_cover_lt_leadtime | 5372 | 1097 | 4275 | 812 | 20.4% | 57.5% |
| rule_lowest_cover_same_alert_volume | 1172 | 475 | 697 | 1434 | 40.5% | 24.9% |
| radar_top_500 | 500 | 357 | 143 | 1552 | 71.4% | 18.7% |
| rule_top_500_lowest_cover | 500 | 248 | 252 | 1661 | 49.6% | 13.0% |

Rule of thumb = today's process: alert when trailing days of cover < supplier contract lead time.

### Same result via the governed metric view

```sql
SELECT MEASURE(radar_alerts) AS radar_alerts, ROUND(MEASURE(radar_alert_precision), 4) AS radar_precision, ROUND(MEASURE(radar_alert_recall), 4) AS radar_recall, MEASURE(rule_alerts) AS rule_alerts, ROUND(MEASURE(rule_alert_precision), 4) AS rule_precision, ROUND(MEASURE(rule_alert_recall), 4) AS rule_recall FROM serverless_stable_3vku19_catalog.inventory_risk.mv_alert_backtest
```

| radar_alerts | radar_precision | radar_recall | rule_alerts | rule_precision | rule_recall |
|---|---|---|---|---|---|
| 1172 | 0.6246 | 0.3834 | 5372 | 0.2042 | 0.5746 |
