# Genie: natural-language questions over the governed risk data

_Captured 2026-11-09 13:30 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

Genie space `01f1dab0693c13bc83454db2585ad2c2` (bundle resource `inventory_risk_genie`). Questions asked through the Genie Conversation API.

## Q: Which 5 store-SKUs have the highest revenue at risk right now?

Status: COMPLETED

**Description:** You want to see the top 5 store-SKU combinations with the highest revenue at risk right now, focusing on those with Critical or High risk tiers.

```sql
WITH `latest_date` AS (
  SELECT MAX(`as_of_date`) AS `as_of_date`
  FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations`
), `ranked` AS (
  SELECT
    `store_name`,
    `sku_name`,
    `risk_tier`,
    `risk_score`,
    `revenue_at_risk`,
    `primary_driver`,
    `recommended_action`,
    `recommended_qty`,
    `risk_rank`,
    RANK() OVER (ORDER BY `revenue_at_risk` DESC, `risk_rank` ASC) AS `rev_rank`
  FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations`
  WHERE `as_of_date` = (SELECT `as_of_date` FROM `latest_date`)
    AND `risk_tier` IN ('Critical', 'High')
    AND `revenue_at_risk` IS NOT NULL
    AND `risk_rank` IS NOT NULL
)
SELECT
  `store_name`,
  `sku_name`,
  `risk_tier`,
  `risk_score`,
  `revenue_at_risk`,
  `primary_driver`,
  `recommended_action`,
  `recommended_qty`
FROM `ranked`
WHERE `rev_rank` <= 5
ORDER BY `revenue_at_risk` DESC, `risk_rank` ASC
```

| store_name | sku_name | risk_tier | risk_score | revenue_at_risk | primary_driver | recommended_action | recommended_qty |
|---|---|---|---|---|---|---|---|
| Harvest Lane Stonebrook Superstore II | Meadow Fresh Green Beans 2ct | Critical | 100 | 1134.28 | Late supplier delivery | EXPEDITE | 348 |
| Harvest Lane Oakhurst Superstore II | Harvest Lane Heavy Cream Large | Critical | 100 | 819.9 | Late supplier delivery | EXPEDITE | 138 |
| Harvest Lane Yarrow Superstore | Crestline Sweet Potatoes Value Pack | Critical | 100 | 750.23 | Upcoming promotion | EXPEDITE | 192 |
| Harvest Lane Thornbury Standard II | Meadow Fresh Green Beans 2ct | Critical | 100 | 604.78 | Late supplier delivery | EXPEDITE | 204 |
| Harvest Lane Kingsley Standard II | Meadow Fresh Green Beans 2ct | Critical | 99 | 583.17 | Late supplier delivery | EXPEDITE | 180 |

**Answer text:** Right now, the **5 store-SKUs with the highest revenue at risk** are:
- **Harvest Lane Stonebrook Superstore II — Meadow Fresh Green Beans 2ct**: **$1,134** at risk, **Critical**, recommended action **EXPEDITE** for **348** units
- **Harvest Lane Oakhurst Superstore II — Harvest Lane Heavy Cream Large**: **$820** at risk, **Critical**, recommended action **EXPEDITE** for **138** units
- **Harvest Lane Yarrow Superstore — Crestline Sweet Potatoes Value Pack**: **$750** at risk, **Critical**, recommended action **EXPEDITE** for **192** units
- **Harvest Lane Thornbury Standard II — Meadow Fresh Green Beans 2ct**: **$605** at risk, **Critical**, recommended action **EXPEDITE** for **204** units
- **Harvest Lane Kingsley Standard II — Meadow Fresh Green Beans 2ct**: **$583** at risk, **Critical**, recommended action **EXPEDITE** for **180** units
Across all 5 results, every item is **Critical** and all recommended actions are **EXPEDITE**, with **Late supplier delivery** appearing as the main driver in 4 of the 5 cases.

## Q: How many Critical and High risks are there by region?

Status: COMPLETED

**Description:** You want to see the number of Critical and High stockout risks (alerts) broken down by region.

```sql
SELECT
  `region`,
  MEASURE(`critical_alerts`) AS `critical_alerts`,
  MEASURE(`critical_high_alerts`) AS `critical_high_alerts`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`mv_inventory_risk`
WHERE `region` IS NOT NULL
GROUP BY ALL
ORDER BY `region` ASC
```

| region | critical_alerts | critical_high_alerts |
|---|---|---|
| Coastal | 164 | 474 |
| Lakeshore | 166 | 495 |
| Metro North | 131 | 438 |
| Metro South | 147 | 425 |
| Valley | 200 | 506 |

**Answer text:** By region, **Critical** risks range from **131** to **200**, and **Critical + High** risks range from **425** to **506** across all **5 regions** shown.

- **Coastal:** **164 Critical**, **474 Critical + High**
- **Lakeshore:** **166 Critical**, **495 Critical + High**
- **Metro North:** **131 Critical**, **438 Critical + High**
- **Metro South:** **147 Critical**, **425 Critical + High**
- **Valley:** **200 Critical**, **506 Critical + High**

**Valley** has the most alerts in both measures, while **Metro South** has the fewest Critical + High alerts and **Metro North** has the fewest Critical alerts.

## Q: Which suppliers are causing the most late-delivery risks?

Status: COMPLETED

**Description:** You're asking to see which suppliers are responsible for the most critical and high late-delivery stockout risks. The results show each supplier's name, the number of these high-risk alerts they have, the total revenue at risk from these alerts, their best on-time delivery rate in the last 30 days as a percentage, and the highest count of their overdue open purchase order lines. The list is ordered by the number of critical and high alerts, then by revenue at risk.

```sql
SELECT
  `r`.`supplier_name`,
  COUNT(*) AS `critical_high_alerts`,
  SUM(`r`.`revenue_at_risk`) AS `revenue_at_risk_usd`,
  MAX(`s`.`on_time_rate_last_30d`) * 100 AS `on_time_pct_last_30d`,
  MAX(`s`.`overdue_open_lines`) AS `overdue_open_po_lines`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations` AS `r`
JOIN `serverless_stable_3vku19_catalog`.`inventory_risk`.`gold_supplier_lead_time_stats` AS `s`
  ON `r`.`supplier_id` = `s`.`supplier_id`
WHERE `r`.`risk_tier` IN ('Critical', 'High')
  AND `r`.`primary_driver` = 'Late supplier delivery'
  AND `r`.`supplier_name` IS NOT NULL
GROUP BY `r`.`supplier_name`
ORDER BY `critical_high_alerts` DESC, `revenue_at_risk_usd` DESC
```

| supplier_name | critical_high_alerts | revenue_at_risk_usd | on_time_pct_last_30d | overdue_open_po_lines |
|---|---|---|---|---|
| Summit Dairy Wholesale | 553 | 22392.240000000005 | 83.32000000000001 | 517 |
| Summit Pantry Foods | 379 | 2650.4299999999994 | 83.07 | 521 |
| Riverbend Fresh Supply Co. | 159 | 6979.93 | 81.02000000000001 | 188 |
| Northern Pantry Supply Co. | 139 | 1031.0999999999995 | 94.91000000000001 | 32 |
| Pacific Fresh Foods | 98 | 1177.6600000000003 | 84.46000000000001 | 62 |
| Summit Snacks Supply Co. | 96 | 208.5 | 96.37 | 2 |
| Atlas Fresh Distributors | 78 | 1715.6399999999999 | 87.31 | 89 |
| Heartland Household Distributors | 68 | 64.63999999999999 | 76.92 | 8 |
| Keystone Household Supply Co. | 64 | 501.21999999999997 | 86.19 | 9 |
| Heartland Bakery Wholesale | 55 | 1102.88 | 72.61 | 51 |
| Keystone Beverages Distributors | 54 | 75.78000000000002 | 92.41 | 9 |
| Keystone Dairy Foods | 45 | 7.949999999999998 | 77.08 | 57 |

**Answer text:** The suppliers driving the most **late-delivery** Critical/High alerts are led by **Summit Dairy Wholesale** with **553 alerts** and **$22,392** in revenue at risk, followed by **Summit Pantry Foods** with **379 alerts** and **$2,650**, and **Riverbend Fresh Supply Co.** with **159 alerts** and **$6,980**. Examples include:
- **Summit Dairy Wholesale** — **553 alerts**, **$22,392** at risk, **83.32%** on-time rate, **517** overdue open PO lines
- **Summit Pantry Foods** — **379 alerts**, **$2,650** at risk, **83.07%** on-time rate, **521** overdue open PO lines
- **Riverbend Fresh Supply Co.** — **159 alerts**, **$6,980** at risk, **81.02%** on-time rate, **188** overdue open PO lines
- **Northern Pantry Supply Co.** — **139 alerts**, **$1,031** at risk, **94.91%** on-time rate, **32** overdue open PO lines
- **Pacific Fresh Foods** — **98 alerts**, **$1,178** at risk, **84.46%** on-time rate, **62** overdue open PO lines

Across the **23 suppliers** shown, the biggest late-delivery risk is concentrated in the top two Summit suppliers, which also have the highest counts of overdue open PO lines.

## Q: What is the forecast WAPE of the model vs the baseline by category?

Status: COMPLETED

**Description:** You want to see the forecast weighted absolute percentage error (WAPE) for the champion model compared to the baseline, broken down by product category, and the percentage improvement of the model over the baseline.

```sql
SELECT
  `category`,
  MEASURE(`model_wape`) AS `model_wape`,
  MEASURE(`baseline_wape`) AS `baseline_wape`,
  MEASURE(`wape_improvement_pct`) AS `wape_improvement_pct`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`mv_forecast_accuracy`
WHERE `category` IS NOT NULL
GROUP BY ALL
ORDER BY `wape_improvement_pct` DESC
```

| category | model_wape | baseline_wape | wape_improvement_pct |
|---|---|---|---|
| Beverages | 0.46224787101191195 | 0.575390314588884 | 19.66359890117585 |
| Meat & Seafood | 0.4945991699377364 | 0.5839908623992697 | 15.307036157085783 |
| Snacks | 0.4578756073033759 | 0.5362787824445984 | 14.619854021415088 |
| Fresh Produce | 0.41088442612876797 | 0.4783985470232157 | 14.112526326542419 |
| Frozen | 0.480007788867091 | 0.5523174512968858 | 13.092047383258654 |
| Bakery | 0.4260675144362512 | 0.49025081079536503 | 13.091930690534745 |
| Pantry & Baking | 0.4972009552147059 | 0.5657472824082951 | 12.116068309121788 |
| Dairy & Eggs | 0.43138722610214864 | 0.4907984449425469 | 12.105013667545942 |
| Household | 0.6209622005449288 | 0.6910972283029669 | 10.148358998669291 |
| Personal Care | 0.7283303840165539 | 0.7953430894942646 | 8.425634969723827 |

**Answer text:** Forecast WAPE is **lower for the model than the baseline in all 10 categories**, so the model performs better across the board. Examples include:
- **Beverages:** model **46.2%** vs baseline **57.5%** (**19.7%** improvement)
- **Meat & Seafood:** model **49.5%** vs baseline **58.4%** (**15.3%** improvement)
- **Snacks:** model **45.8%** vs baseline **53.6%** (**14.6%** improvement)
- **Fresh Produce:** model **41.1%** vs baseline **47.8%** (**14.1%** improvement)
- **Personal Care:** model **72.8%** vs baseline **79.5%** (**8.4%** improvement)
Overall, the biggest gain is in **Beverages**, while **Personal Care** has the smallest improvement and the highest WAPE for both approaches.

## Q: What was the alert precision of the radar compared with the rule of thumb?

Status: COMPLETED

**Description:** You want to see a comparison of alert precision and recall between the radar system and the rule of thumb method.

```sql
SELECT MEASURE(`radar_alerts`) AS `radar_alerts`, ROUND(MEASURE(`radar_alert_precision`) * 100, 1) AS `radar_precision_pct`, ROUND(MEASURE(`radar_alert_recall`) * 100, 1) AS `radar_recall_pct`, MEASURE(`rule_alerts`) AS `rule_alerts`, ROUND(MEASURE(`rule_alert_precision`) * 100, 1) AS `rule_precision_pct`, ROUND(MEASURE(`rule_alert_recall`) * 100, 1) AS `rule_recall_pct`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`mv_alert_backtest`
GROUP BY ALL
```

| radar_alerts | radar_precision_pct | radar_recall_pct | rule_alerts | rule_precision_pct | rule_recall_pct |
|---|---|---|---|---|---|
| 1172 | 62.5 | 38.3 | 5372 | 20.4 | 57.5 |

**Answer text:** The radar’s alert precision was **62.5%**, compared with **20.4%** for the rule of thumb. In this backtest, the radar generated **1,172 alerts** versus **5,372 alerts** for the rule of thumb, which means the radar was more precise while flagging far fewer alerts.

## Q: Explain the recommendation for green beans at Stonebrook

Status: COMPLETED

**Description:** You want to see the detailed stockout risk recommendation for green beans at the Stonebrook store.

```sql
SELECT
  `store_name`,
  `sku_name`,
  `risk_tier`,
  `risk_score`,
  ROUND(`stockout_probability` * 100) AS `stockout_probability_pct`,
  `on_hand_units`,
  `forecast_demand_window`,
  `lead_time_window_days`,
  `primary_driver`,
  `driver_details`,
  `recommended_action`,
  `recommended_qty`,
  `action_source_id`,
  `planner_explanation`,
  `explanation_is_llm`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations`
WHERE `sku_name` ILIKE '%green beans%'
  AND `store_name` ILIKE '%stonebrook%'
ORDER BY `risk_rank`
LIMIT 5
```

| store_name | sku_name | risk_tier | risk_score | stockout_probability_pct | on_hand_units | forecast_demand_window | lead_time_window_days | primary_driver | driver_details | recommended_action | recommended_qty | action_source_id | planner_explanation | explanation_is_llm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Harvest Lane Stonebrook Superstore II | Meadow Fresh Green Beans 2ct | Critical | 100 | 100.0 | 46 | 255.3 | 3 | Late supplier delivery | Late supplier delivery: 348 inbound units are late; now projected in 5 days (1 PO lines overdue, supplier on-time 81% last 30d) / Demand trend above baseline: forecast +25 units vs. usual over the next 3 days | EXPEDITE | 348 | V003 | Only 46 units are on hand against 255.3 units of forecast demand over the 3-day window (usual 230.2), and the 348 inbound units are late, now projected to arrive in 5 days, after the window closes. Ask Riverbend Fresh Supply Co. to expedite the 348 delayed PO units. | true |
| Harvest Lane Stonebrook Superstore II | Meadow Fresh Green Beans Family Size | High | 47 | 47.0 | 50 | 49.0 | 3 | Late supplier delivery | Late supplier delivery: 60 inbound units are late; now projected in 5 days (1 PO lines overdue, supplier on-time 81% last 30d) | EXPEDITE | 60 | V003 | Meadow Fresh Green Beans Family Size at Harvest Lane Stonebrook Superstore II has a 47.0% chance of running out in the next 3 days (Late supplier delivery). Suggested: EXPEDITE 60 units. | false |
| Harvest Lane Stonebrook Superstore II | Golden Fields Green Beans | Low | 2 | 3.0 | 175 | 107.5 | 4 | Normal variability | No dominant driver; risk reflects normal demand variability | MONITOR | 0 |  | Golden Fields Green Beans at Harvest Lane Stonebrook Superstore II has a 3.0% chance of running out in the next 4 days (Normal variability). Suggested: MONITOR. | false |
| Harvest Lane Stonebrook Neighborhood | Prairie Co. Green Beans Value Pack | Low | 2 | 4.0 | 22 | 13.5 | 3 | Normal variability | No dominant driver; risk reflects normal demand variability | MONITOR | 0 |  | Prairie Co. Green Beans Value Pack at Harvest Lane Stonebrook Neighborhood has a 4.0% chance of running out in the next 3 days (Normal variability). Suggested: MONITOR. | false |
| Harvest Lane Stonebrook Neighborhood | Golden Fields Green Beans | Low | 2 | 4.0 | 46 | 38.0 | 4 | Late supplier delivery | Late supplier delivery: 36 inbound units are late; now projected in 4 days (0 PO lines overdue, supplier on-time 84% last 30d) | MONITOR | 0 |  | Golden Fields Green Beans at Harvest Lane Stonebrook Neighborhood has a 4.0% chance of running out in the next 4 days (Late supplier delivery). Suggested: MONITOR. | false |

**Answer text:** At **Harvest Lane Stonebrook Superstore II**, the strongest green beans recommendation is for **Meadow Fresh Green Beans 2ct**: **EXPEDITE 348 units** because only **46 units** are on hand versus **255.3 units** of forecast demand over the next **3 days**, and the inbound shipment is now expected in **5 days**, after the risk window closes. Another Stonebrook green beans item, **Meadow Fresh Green Beans Family Size**, is also flagged for **EXPEDITE 60 units** due to a late supplier delivery, with a **47%** stockout risk over the next **3 days**. Across the **5** green beans rows returned for Stonebrook, late supplier delivery is the main reason behind the items with meaningful risk, while the other three are low-risk and set to **MONITOR**.

## Q: How good are the Gen AI planner notes?

Status: COMPLETED

**Description:** You want to see an overall evaluation of the Gen AI planner notes quality.

```sql
SELECT COUNT(*) AS `notes_evaluated`, ROUND(AVG(CASE WHEN `final_pass` THEN 1 ELSE 0 END) * 100, 1) AS `pass_rate_pct`, ROUND(AVG(`judge_faithfulness`), 2) AS `avg_faithfulness_1_to_5`, ROUND(AVG(`judge_actionability`), 2) AS `avg_actionability_1_to_5`, SUM(`unsupported_number_count`) AS `unsupported_numbers` FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_explanation_eval`
```

| notes_evaluated | pass_rate_pct | avg_faithfulness_1_to_5 | avg_actionability_1_to_5 | unsupported_numbers |
|---|---|---|---|---|
| 400 | 94.5 | 4.95 | 4.96 | 4 |

**Answer text:** The Gen AI planner notes look **very strong** in this evaluation: **400** notes were reviewed, the **pass rate was 94.5%**, the average **faithfulness score was 4.95 out of 5**, and the average **actionability score was 4.96 out of 5**. Across those **400** notes, there were **4** unsupported numbers, which indicates very few quantified details were flagged.
