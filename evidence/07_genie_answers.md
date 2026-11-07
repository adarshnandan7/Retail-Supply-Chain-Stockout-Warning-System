# Genie: natural-language questions over the governed risk data

_Captured 2026-11-07 14:14 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

Genie space `01f1dab0693c13bc83454db2585ad2c2` (bundle resource `inventory_risk_genie`). Questions asked through the Genie Conversation API.

## Q: Which 5 store-SKUs have the highest revenue at risk right now?

Status: COMPLETED

**Description:** You want to see the top 5 store-SKU combinations with the highest revenue at risk right now, focusing on those with critical or high stockout risk.

```sql
WITH `latest_risks` AS (
  SELECT
    `risk_rank`,
    `store_name`,
    `sku_name`,
    `risk_tier`,
    `risk_score`,
    `revenue_at_risk`,
    `primary_driver`,
    `recommended_action`,
    `recommended_qty`,
    RANK() OVER (ORDER BY `revenue_at_risk` DESC) AS `rev_rank`
  FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations`
  WHERE `as_of_date` = (
      SELECT MAX(`as_of_date`)
      FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations`
    )
    AND `risk_tier` IN ('Critical', 'High')
    AND `store_name` IS NOT NULL
    AND `sku_name` IS NOT NULL
    AND `revenue_at_risk` IS NOT NULL
    AND `risk_tier` IS NOT NULL
    AND `risk_rank` IS NOT NULL
)
SELECT
  `risk_rank`,
  `store_name`,
  `sku_name`,
  `risk_tier`,
  `risk_score`,
  CAST(ROUND(`revenue_at_risk`, 0) AS BIGINT) AS `revenue_at_risk_usd`,
  `primary_driver`,
  `recommended_action`,
  `recommended_qty`
FROM `latest_risks`
WHERE `rev_rank` <= 5
ORDER BY `revenue_at_risk_usd` DESC, `risk_rank` ASC
```

| risk_rank | store_name | sku_name | risk_tier | risk_score | revenue_at_risk_usd | primary_driver | recommended_action | recommended_qty |
|---|---|---|---|---|---|---|---|---|
| 1 | Harvest Lane Stonebrook Superstore II | Meadow Fresh Green Beans 2ct | Critical | 100 | 1134 | Late supplier delivery | EXPEDITE | 348 |
| 2 | Harvest Lane Oakhurst Superstore II | Harvest Lane Heavy Cream Large | Critical | 100 | 820 | Late supplier delivery | EXPEDITE | 138 |
| 3 | Harvest Lane Yarrow Superstore | Crestline Sweet Potatoes Value Pack | Critical | 100 | 750 | Upcoming promotion | EXPEDITE | 192 |
| 4 | Harvest Lane Thornbury Standard II | Meadow Fresh Green Beans 2ct | Critical | 100 | 605 | Late supplier delivery | EXPEDITE | 204 |
| 231 | Harvest Lane Kingsley Standard II | Meadow Fresh Green Beans 2ct | Critical | 99 | 583 | Late supplier delivery | EXPEDITE | 180 |

**Answer text:** The **5 store-SKUs with the highest revenue at risk right now** are all **Critical** alerts, ranging from **$583** to **$1,134** in revenue at risk.

- **Harvest Lane Stonebrook Superstore II — Meadow Fresh Green Beans 2ct:** **$1,134** at risk, risk score **100**, driver **Late supplier delivery**, suggested action **EXPEDITE** **348** units
- **Harvest Lane Oakhurst Superstore II — Harvest Lane Heavy Cream Large:** **$820** at risk, risk score **100**, driver **Late supplier delivery**, suggested action **EXPEDITE** **138** units
- **Harvest Lane Yarrow Superstore — Crestline Sweet Potatoes Value Pack:** **$750** at risk, risk score **100**, driver **Upcoming promotion**, suggested action **EXPEDITE** **192** units
- **Harvest Lane Thornbury Standard II — Meadow Fresh Green Beans 2ct:** **$605** at risk, risk score **100**, driver **Late supplier delivery**, suggested action **EXPEDITE** **204** units
- **Harvest Lane Kingsley Standard II — Meadow Fresh Green Beans 2ct:** **$583** at risk, risk score **99**, driver **Late supplier delivery**, suggested action **EXPEDITE** **180** units

A notable pattern is that **4 of the 5** highest-risk store-SKUs are driven by **late supplier delivery**, and **Meadow Fresh Green Beans 2ct** appears in **3 of the 5** spots.

## Q: How many Critical and High risks are there by region?

Status: COMPLETED

**Description:** You want to see the number of Critical and High stockout risks by region, sorted by the count of Critical and High risks in descending order.

```sql
SELECT
  `region`,
  MEASURE(`critical_alerts`) AS `critical_alerts`,
  MEASURE(`critical_high_alerts`) AS `critical_high_alerts`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`mv_inventory_risk`
WHERE `region` IS NOT NULL
GROUP BY ALL
ORDER BY `critical_high_alerts` DESC
```

| region | critical_alerts | critical_high_alerts |
|---|---|---|
| Valley | 200 | 506 |
| Lakeshore | 166 | 495 |
| Coastal | 164 | 474 |
| Metro North | 131 | 438 |
| Metro South | 147 | 425 |

**Answer text:** By region, **Valley** has **200 Critical** risks and **506 Critical + High** risks, the highest in the results, while **Metro South** has the lowest combined total at **425**. Examples include:
- **Valley** — **200 Critical**, **506 Critical + High**
- **Lakeshore** — **166 Critical**, **495 Critical + High**
- **Coastal** — **164 Critical**, **474 Critical + High**
- **Metro North** — **131 Critical**, **438 Critical + High**
- **Metro South** — **147 Critical**, **425 Critical + High**

## Q: Which suppliers are causing the most late-delivery risks?

Status: COMPLETED

**Description:** You want to see which suppliers are responsible for the most critical and high late-delivery stockout risks.

```sql
SELECT
  r.`supplier_name`,
  COUNT(*) AS `critical_high_alerts`,
  SUM(r.`revenue_at_risk`) AS `revenue_at_risk_usd`,
  MAX(s.`on_time_rate_last_30d`) * 100 AS `on_time_pct_last_30d`,
  MAX(s.`overdue_open_lines`) AS `overdue_open_po_lines`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`risk_recommendations` r
JOIN `serverless_stable_3vku19_catalog`.`inventory_risk`.`gold_supplier_lead_time_stats` s
  ON r.`supplier_id` = s.`supplier_id`
WHERE r.`risk_tier` IN ('Critical', 'High')
  AND r.`primary_driver` = 'Late supplier delivery'
  AND r.`supplier_name` IS NOT NULL
  AND r.`supplier_id` IS NOT NULL
GROUP BY r.`supplier_name`
ORDER BY `critical_high_alerts` DESC, `revenue_at_risk_usd` DESC
```

| supplier_name | critical_high_alerts | revenue_at_risk_usd | on_time_pct_last_30d | overdue_open_po_lines |
|---|---|---|---|---|
| Summit Dairy Wholesale | 553 | 22392.24 | 83.32000000000001 | 517 |
| Summit Pantry Foods | 379 | 2650.4299999999994 | 83.07 | 521 |
| Riverbend Fresh Supply Co. | 159 | 6979.93 | 81.02000000000001 | 188 |
| Northern Pantry Supply Co. | 139 | 1031.0999999999995 | 94.91000000000001 | 32 |
| Pacific Fresh Foods | 98 | 1177.66 | 84.46000000000001 | 62 |
| Summit Snacks Supply Co. | 96 | 208.5 | 96.37 | 2 |
| Atlas Fresh Distributors | 78 | 1715.6399999999999 | 87.31 | 89 |
| Heartland Household Distributors | 68 | 64.63999999999999 | 76.92 | 8 |
| Keystone Household Supply Co. | 64 | 501.2199999999999 | 86.19 | 9 |
| Heartland Bakery Wholesale | 55 | 1102.88 | 72.61 | 51 |
| Keystone Beverages Distributors | 54 | 75.78000000000002 | 92.41 | 9 |
| Keystone Dairy Foods | 45 | 7.949999999999998 | 77.08 | 57 |

**Answer text:** Examples include:
- **Summit Dairy Wholesale**: **553** Critical/High late-delivery alerts, **$22,392** revenue at risk, **83.3%** on-time rate, and **517** overdue open PO lines.
- **Summit Pantry Foods**: **379** alerts, **$2,650** revenue at risk, **83.1%** on-time rate, and **521** overdue open PO lines.
- **Riverbend Fresh Supply Co.**: **159** alerts, **$6,980** revenue at risk, **81.0%** on-time rate, and **188** overdue open PO lines.
- **Northern Pantry Supply Co.**: **139** alerts, **$1,031** revenue at risk, **94.9%** on-time rate, and **32** overdue open PO lines.
- **Pacific Fresh Foods**: **98** alerts, **$1,178** revenue at risk, **84.5%** on-time rate, and **62** overdue open PO lines.
Across the 23 suppliers shown, the biggest late-delivery risk is concentrated in **Summit Dairy Wholesale** and **Summit Pantry Foods**, which also have the highest overdue open PO line counts.

## Q: What is the forecast WAPE of the model vs the baseline by category?

Status: COMPLETED

**Description:** You want to see the forecast weighted absolute percentage error (WAPE) for the model compared to the baseline, broken down by product category.

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
| Beverages | 0.4609918653477352 | 0.575390314588884 | 19.881886493499024 |
| Meat & Seafood | 0.49422485202635896 | 0.5839908623992697 | 15.371132692747238 |
| Snacks | 0.4578486309888909 | 0.5362787824445985 | 14.62488429957789 |
| Fresh Produce | 0.4105457761716631 | 0.4783985470232157 | 14.183314576049458 |
| Bakery | 0.4263026895567251 | 0.49025081079536503 | 13.043960322042663 |
| Frozen | 0.4809665510547926 | 0.5523174512968858 | 12.918458410929365 |
| Pantry & Baking | 0.49701680623608274 | 0.5657472824082951 | 12.148617997710527 |
| Dairy & Eggs | 0.43142658762855807 | 0.4907984449425468 | 12.096993771229018 |
| Household | 0.6212433515724441 | 0.6910972283029668 | 10.107677164623174 |
| Personal Care | 0.7288163914768816 | 0.7953430894942646 | 8.364528326974636 |

**Answer text:** The model has a **lower WAPE than the baseline in all 10 categories**, with improvement ranging from **8.4% to 19.9%**. Examples include:
- **Beverages:** model **46.1%** vs baseline **57.5%** (**19.9%** better)
- **Meat & Seafood:** model **49.4%** vs baseline **58.4%** (**15.4%** better)
- **Snacks:** model **45.8%** vs baseline **53.6%** (**14.6%** better)
- **Fresh Produce:** model **41.1%** vs baseline **47.8%** (**14.2%** better)
- **Bakery:** model **42.6%** vs baseline **49.0%** (**13.0%** better)
Overall, the model performs best relative to the baseline in **Beverages** and shows the smallest gain in **Personal Care**.

## Q: What was the alert precision of the radar compared with the rule of thumb?

Status: COMPLETED

**Description:** You want to see a comparison of the alert precision and recall between the radar system and the rule of thumb method for stockout alerts.

```sql
SELECT MEASURE(`radar_alerts`) AS `radar_alerts`, ROUND(MEASURE(`radar_alert_precision`) * 100, 1) AS `radar_precision_pct`, ROUND(MEASURE(`radar_alert_recall`) * 100, 1) AS `radar_recall_pct`, MEASURE(`rule_alerts`) AS `rule_alerts`, ROUND(MEASURE(`rule_alert_precision`) * 100, 1) AS `rule_precision_pct`, ROUND(MEASURE(`rule_alert_recall`) * 100, 1) AS `rule_recall_pct`
FROM `serverless_stable_3vku19_catalog`.`inventory_risk`.`mv_alert_backtest`
GROUP BY ALL
```

| radar_alerts | radar_precision_pct | radar_recall_pct | rule_alerts | rule_precision_pct | rule_recall_pct |
|---|---|---|---|---|---|
| 1172 | 62.5 | 38.3 | 5372 | 20.4 | 57.5 |

**Answer text:** The radar’s alert precision was **62.5%**, compared with **20.4%** for the rule of thumb. In this backtest, the radar generated **1,172 alerts** versus **5,372 alerts** for the rule of thumb, indicating the radar was more precise while flagging fewer alerts.
