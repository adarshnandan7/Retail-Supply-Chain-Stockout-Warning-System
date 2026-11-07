# Inventory-risk scoring, drivers, actions and Gen AI notes

_Captured 2026-11-07 14:12 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- Scored 19,996 store/SKUs as of 2026-11-06
- Tiers: {'Low': 16832, 'High': 1530, 'Medium': 826, 'Critical': 808}
- Suggested actions: {'MONITOR': 16832, 'EXPEDITE': 2527, 'REORDER': 585, 'TRANSFER': 52}
- Primary drivers (Critical+High): {'Late supplier delivery': 2094, 'Upcoming promotion': 184, 'No open purchase order': 29, 'Recent demand surge': 27, 'Demand trend above baseline': 2, 'Normal variability': 2}
- Revenue at risk (Critical+High): $53,020

### Top 20 ranked risks

```sql
SELECT risk_rank, risk_tier, risk_score, store_name, sku_name, on_hand_units, inbound_units_in_window, forecast_demand_window,
  lead_time_window_days, projected_stockout_in_days, round(stockout_probability, 3) AS p_stockout, round(revenue_at_risk, 0) AS revenue_at_risk,
  primary_driver, recommended_action, recommended_qty, action_source_id FROM serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations ORDER BY risk_rank LIMIT 20
```

| risk_rank | risk_tier | risk_score | store_name | sku_name | on_hand_units | inbound_units_in_window | forecast_demand_window | lead_time_window_days | projected_stockout_in_days | p_stockout | revenue_at_risk | primary_driver | recommended_action | recommended_qty | action_source_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Critical | 100 | Harvest Lane Stonebrook Superstore II | Meadow Fresh Green Beans 2ct | 46 | 0 | 255.3 | 3 | 1.0 | 1.0 | 1134.0 | Late supplier delivery | EXPEDITE | 348 | V003 |
| 2 | Critical | 100 | Harvest Lane Oakhurst Superstore II | Harvest Lane Heavy Cream Large | 0 | 0 | 139.7 | 3 | 1.0 | 1.0 | 820.0 | Late supplier delivery | EXPEDITE | 138 | V005 |
| 3 | Critical | 100 | Harvest Lane Yarrow Superstore | Crestline Sweet Potatoes Value Pack | 86 | 192 | 425.1 | 4 | 1.0 | 0.999 | 750.0 | Upcoming promotion | EXPEDITE | 192 | V001 |
| 4 | Critical | 100 | Harvest Lane Thornbury Standard II | Meadow Fresh Green Beans 2ct | 53 | 0 | 164.5 | 3 | 1.0 | 0.996 | 605.0 | Late supplier delivery | EXPEDITE | 204 | V003 |
| 5 | Critical | 100 | Harvest Lane Stonebrook Superstore II | Harvest Lane Peanut Butter Organic | 0 | 372 | 450.9 | 13 | 12.0 | 0.997 | 545.0 | Late supplier delivery | REORDER | 96 | V016 |
| 6 | Critical | 100 | Harvest Lane Dunmore Superstore | Crestline Sweet Potatoes Value Pack | 0 | 192 | 296.3 | 4 | 1.0 | 1.0 | 532.0 | Late supplier delivery | EXPEDITE | 192 | V001 |
| 7 | Critical | 100 | Harvest Lane Juniper Bay Superstore II | Meadow Fresh 2% Milk Organic | 46 | 0 | 141.1 | 5 | 2.0 | 1.0 | 422.0 | Late supplier delivery | EXPEDITE | 84 | V004 |
| 8 | Critical | 100 | Harvest Lane Riverside Standard | Green Valley Oat Milk Value Pack | 16 | 0 | 74.5 | 5 | 1.0 | 1.0 | 398.0 | Late supplier delivery | EXPEDITE | 40 | V004 |
| 9 | Critical | 100 | Harvest Lane Fairhaven Standard II | Green Valley Oat Milk Value Pack | 13 | 0 | 70.7 | 5 | 1.0 | 0.999 | 392.0 | Late supplier delivery | EXPEDITE | 60 | V004 |
| 10 | Critical | 100 | Harvest Lane Oakhurst Superstore II | Blue Harbor Large Eggs 2ct | 16 | 0 | 75.5 | 5 | 1.0 | 0.997 | 367.0 | Late supplier delivery | EXPEDITE | 42 | V004 |
| 11 | Critical | 100 | Harvest Lane Cedar Point Superstore II | Crestline Cheddar Block | 23 | 0 | 123.1 | 5 | 1.0 | 1.0 | 367.0 | Late supplier delivery | EXPEDITE | 72 | V004 |
| 12 | Critical | 100 | Harvest Lane Oakhurst Superstore II | Sunrise Baby Spinach Family Size | 28 | 0 | 102.0 | 3 | 1.0 | 1.0 | 352.0 | Late supplier delivery | EXPEDITE | 108 | V003 |
| 13 | Critical | 100 | Harvest Lane Juniper Bay Superstore II | Golden Fields Butter | 38 | 0 | 108.3 | 5 | 2.0 | 0.998 | 335.0 | Late supplier delivery | EXPEDITE | 72 | V004 |
| 14 | Critical | 100 | Harvest Lane Kingsley Standard | Crestline Cheddar Block | 4 | 0 | 92.9 | 5 | 1.0 | 1.0 | 326.0 | Upcoming promotion | EXPEDITE | 36 | V004 |
| 15 | Critical | 100 | Harvest Lane Violet Springs Standard | Green Valley Oat Milk Value Pack | 0 | 48 | 90.7 | 5 | 1.0 | 1.0 | 291.0 | Late supplier delivery | EXPEDITE | 112 | V004 |
| 16 | Critical | 100 | Harvest Lane Kingsley Standard II | Golden Fields Heavy Cream | 17 | 0 | 89.6 | 5 | 1.0 | 1.0 | 289.0 | Late supplier delivery | EXPEDITE | 60 | V004 |
| 17 | Critical | 100 | Harvest Lane Yarrow Standard II | Green Valley Oat Milk Value Pack | 0 | 60 | 102.4 | 5 | 1.0 | 0.997 | 289.0 | Late supplier delivery | EXPEDITE | 132 | V004 |
| 18 | Critical | 100 | Harvest Lane Stonebrook Superstore II | Golden Fields Russet Potatoes Large | 41 | 0 | 128.2 | 3 | 1.0 | 0.999 | 286.0 | Late supplier delivery | EXPEDITE | 144 | V002 |
| 19 | Critical | 100 | Harvest Lane Stonebrook Superstore II | Crestline Sour Cream Large | 0 | 0 | 47.2 | 5 | 1.0 | 1.0 | 269.0 | Late supplier delivery | EXPEDITE | 36 | V004 |
| 20 | Critical | 100 | Harvest Lane Maple Ridge Standard II | Crestline Greek Yogurt | 13 | 0 | 74.7 | 5 | 1.0 | 1.0 | 260.0 | Late supplier delivery | EXPEDITE | 56 | V004 |

### Gen AI planner notes (ai_query) for the top 8

```sql
SELECT risk_rank, sku_name, store_name, planner_explanation FROM serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations WHERE explanation_is_llm ORDER BY risk_rank LIMIT 8
```

| risk_rank | sku_name | store_name | planner_explanation |
|---|---|---|---|
| 1 | Meadow Fresh Green Beans 2ct | Harvest Lane Stonebrook Superstore II | Meadow Fresh Green Beans 2ct at Harvest Lane Stonebrook Superstore II will likely run out because only 46 units are on hand against 255.3 units of forecast demand in the 3-day window, with no inbound arriving in that window, since the 348 late units are now projected in 5 days and demand is running above usual (230.2). Expedite 348 units by asking Riverbend Fresh Supply Co. to speed up the delayed PO units. |
| 2 | Harvest Lane Heavy Cream Large | Harvest Lane Oakhurst Superstore II | Harvest Lane Heavy Cream Large at Harvest Lane Oakhurst Superstore II has 0 units on hand and no inbound units arriving within the 3-day window, while forecast demand of 139.7 units (usual 88.9) is driven by a 51-unit promotion lift and 138 late inbound units now projected to arrive in 4 days. Expedite 138 units by asking Summit Dairy Wholesale to accelerate the delayed PO units. |
| 3 | Crestline Sweet Potatoes Value Pack | Harvest Lane Yarrow Superstore | Forecast demand of 425.1 units over the next 4 days far exceeds the 86 units on hand, driven by a 248-unit promotion lift and 192 inbound units that are late and now projected to arrive in 2 days. Expedite 192 units by asking Pacific Fresh Foods to expedite the delayed PO units. |
| 4 | Meadow Fresh Green Beans 2ct | Harvest Lane Thornbury Standard II | Harvest Lane Thornbury Standard II has only 53 units on hand against 164.5 units of forecast demand in the 3-day window, and none of the 204 inbound units arrive in that window because the overdue PO is now projected to land in 4 days. The planner should ask Riverbend Fresh Supply Co. to expedite the 204 delayed PO units. |
| 5 | Harvest Lane Peanut Butter Organic | Harvest Lane Stonebrook Superstore II | With 0 units on hand, the 372 inbound units are late and now projected to arrive in 1 day (1 PO line overdue, supplier on-time 83% over the last 30 days), while forecast demand of 450.9 units over the 13-day window exceeds the usual 234.3 because of an upcoming promotion adding 217 units. Place an additional order of 96 units with Summit Pantry Foods (case pack 6). |
| 6 | Crestline Sweet Potatoes Value Pack | Harvest Lane Dunmore Superstore | With zero units on hand, the 192 inbound units are running late (now projected in 2 days), while forecast demand of 296.3 units over the 4-day window is inflated by an upcoming promotion adding 161 units versus usual. Expedite 192 units by asking Pacific Fresh Foods to expedite the delayed PO units. |
| 7 | Meadow Fresh 2% Milk Organic | Harvest Lane Juniper Bay Superstore II | Meadow Fresh 2% Milk Organic is likely to run out because 84 inbound units are late and now projected to arrive in 6 days, while on-hand stock of 46 units and zero inbound in the window cannot cover forecast demand of 141.1 units. Expedite 84 units by asking Summit Dairy Wholesale to speed up the delayed PO, since its on-time rate was 58% over the last 30 days. |
| 8 | Green Valley Oat Milk Value Pack | Harvest Lane Riverside Standard | The Green Valley Oat Milk Value Pack at Harvest Lane Riverside Standard is likely to run out because 16 units on hand fall well short of 74.5 units of forecast demand in the 5-day window, and the 40 inbound units are late and not projected to arrive for 6 days. Expedite 40 units by asking Summit Dairy Wholesale to rush the delayed PO units so they arrive within the window. |

### LLM output completeness

```sql
SELECT count(*) AS prompts, count(llm_explanation) AS non_empty, count(llm_error) AS errors, percentile(length(llm_explanation), 0.5) AS median_chars, max(llm_endpoint) AS endpoint FROM serverless_stable_3vku19_catalog.inventory_risk.risk_explanations
```

| prompts | non_empty | errors | median_chars | endpoint |
|---|---|---|---|---|
| 400 | 400 | 0 | 362.0 | databricks-claude-haiku-5-5 |

### Expedite opportunities grouped by supplier (one call covers many store/SKUs)

```sql
SELECT supplier_name, count(*) AS store_skus, sum(recommended_qty) AS units_to_expedite, round(sum(revenue_at_risk), 0) AS revenue_at_risk
FROM serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations WHERE recommended_action = 'EXPEDITE' GROUP BY supplier_name ORDER BY store_skus DESC LIMIT 8
```

| supplier_name | store_skus | units_to_expedite | revenue_at_risk |
|---|---|---|---|
| Summit Dairy Wholesale | 516 | 20786 | 19834.0 |
| Summit Pantry Foods | 423 | 38676 | 1215.0 |
| Northern Pantry Supply Co. | 189 | 11982 | 1171.0 |
| Riverbend Fresh Supply Co. | 181 | 11888 | 6939.0 |
| Pacific Fresh Foods | 140 | 10888 | 2423.0 |
| Summit Snacks Supply Co. | 121 | 28260 | 214.0 |
| Heartland Household Distributors | 102 | 4500 | 33.0 |
| Atlas Fresh Distributors | 98 | 5222 | 1719.0 |
