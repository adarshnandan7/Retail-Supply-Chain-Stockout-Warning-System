# Inventory-risk scoring, drivers, actions and Gen AI notes

_Captured 2026-11-09 13:27 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

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
| 1 | Meadow Fresh Green Beans 2ct | Harvest Lane Stonebrook Superstore II | Only 46 units are on hand against 255.3 units of forecast demand over the 3-day window (usual 230.2), and the 348 inbound units are late, now projected to arrive in 5 days, after the window closes. Ask Riverbend Fresh Supply Co. to expedite the 348 delayed PO units. |
| 2 | Harvest Lane Heavy Cream Large | Harvest Lane Oakhurst Superstore II | Harvest Lane Heavy Cream Large has 0 units on hand and no inbound units arriving within the 3-day window, while forecast demand of 139.7 units (usual 88.9) is pushed up by a promotion adding 51 units, and its 138 late inbound units are now projected to arrive in 4 days. Expedite 138 units by asking Summit Dairy Wholesale to speed up the delayed PO units to cover the $820.0 in revenue at risk. |
| 3 | Crestline Sweet Potatoes Value Pack | Harvest Lane Yarrow Superstore | Forecast demand of 425.1 units over the next 4 days far exceeds the 86 units on hand, driven by a promotion adding 248 units versus usual, and the 192 inbound units are late and now projected to arrive in 2 days. Ask Pacific Fresh Foods to expedite the 192 delayed PO units. |
| 4 | Meadow Fresh Green Beans 2ct | Harvest Lane Thornbury Standard II | Meadow Fresh Green Beans 2ct at Harvest Lane Thornbury Standard II is likely to run out because only 53 units are on hand against 164.5 units of forecast demand in the 3-day window, and its 204 inbound units are late and now projected to arrive in 4 days. Ask Riverbend Fresh Supply Co. to expedite the delayed PO for 204 units. |
| 5 | Harvest Lane Peanut Butter Organic | Harvest Lane Stonebrook Superstore II | With zero units on hand, 372 inbound units are running late (now projected to arrive in 1 day, with 1 PO line overdue and supplier on-time at 83% over the last 30 days), while a promotion lifts forecast demand to 450.9 units over the 13-day window versus a usual 234.3. Place a reorder of 96 units with Summit Pantry Foods (case pack 6) to cover the shortfall. |
| 6 | Crestline Sweet Potatoes Value Pack | Harvest Lane Dunmore Superstore | Crestline Sweet Potatoes Value Pack at Harvest Lane Dunmore Superstore has 0 units on hand, its 192 inbound units are late and now projected in 2 days, and an upcoming promotion pushes forecast demand to 296.3 units over the 4-day window (usual: 135.0). Ask Pacific Fresh Foods to expedite 192 delayed PO units to protect the $532.0 in revenue at risk. |
| 7 | Meadow Fresh 2% Milk Organic | Harvest Lane Juniper Bay Superstore II | Meadow Fresh 2% Milk Organic at Harvest Lane Juniper Bay Superstore II is likely to run out because 46 units on hand and no inbound arriving in the 5-day window cannot cover 141.1 forecast units, and the 84 late inbound units are now projected 6 days out, with the supplier on time only 58% of the time over the last 30 days. Ask Summit Dairy Wholesale to expedite 84 delayed PO units. |
| 8 | Green Valley Oat Milk Value Pack | Harvest Lane Riverside Standard | Green Valley Oat Milk Value Pack at Harvest Lane Riverside Standard is likely to run out because only 16 units are on hand, none arrive within the 5-day window, and forecast demand of 74.5 units exceeds that supply, while 40 late inbound units are now projected in 6 days and the supplier has been on time only 58% of the time over the last 30 days. Expedite 40 units by asking Summit Dairy Wholesale to speed up the delayed PO units. |

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
