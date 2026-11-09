# Task `genai_explanations` - SUCCESS
- Task run id: `914518877414782`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/risk/genai_explanations`
- Duration: 108 s

## Cell 1

```markdown
%md
# 05c - Gen AI planner explanations and the published `risk_recommendations` table

The risk score and drivers are computed deterministically (05b). Here an LLM served by Databricks
(`ai_query` on a Foundation Model endpoint) only *rephrases* those quantified facts into a two-sentence
note a store or replenishment planner can act on. Every number in the prompt comes from governed tables,
and the model is instructed not to invent any. Lower-tier items get a deterministic template instead,
which keeps cost predictable.
```

## Cell 2

```python
dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("llm_endpoint", "databricks-claude-haiku-5-5")
dbutils.widgets.text("max_llm_rows", "400")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
LLM = dbutils.widgets.get("llm_endpoint")
MAX_ROWS = int(dbutils.widgets.get("max_llm_rows"))
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
```

## Cell 3

```python
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW llm_input AS
SELECT recommendation_id,
  concat(
    'You are a grocery replenishment analyst. Write exactly two short sentences for a store planner. ',
    'Sentence 1: why this item is likely to run out (use only the facts given). Sentence 2: the recommended action with quantity. ',
    'Do not invent numbers, dates, or causes. No preamble.\\n',
    'Item: ', sku_name, ' (', category, ') at ', store_name, ', region ', region, '.\\n',
    'Risk score: ', risk_score, '/100 (', risk_tier, '); stockout probability ', round(stockout_probability * 100), '% within the ',
    lead_time_window_days, '-day replenishment window.\\n',
    'On hand: ', on_hand_units, ' units; inbound arriving in window: ', inbound_units_in_window, ' units; forecast demand in window: ',
    forecast_demand_window, ' units (usual: ', baseline_demand_window, ').\\n',
    'Drivers: ', driver_details, '.\\n',
    'Revenue at risk: $', round(revenue_at_risk, 0), '.\\n',
    'Recommended action: ', recommended_action, ' ', recommended_qty, ' units - ', action_rationale, '.'
  ) AS prompt
FROM {FQ}.risk_scores
WHERE risk_tier IN ('Critical', 'High')
ORDER BY risk_rank
LIMIT {MAX_ROWS}
""")

spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.risk_explanations
COMMENT 'LLM-written planner notes for the highest-ranked stockout risks (ai_query over governed facts).'
AS SELECT recommendation_id, prompt,
  nullif(trim(r.result), '') AS llm_explanation, r.errorMessage AS llm_error,
  '{LLM}' AS llm_endpoint, current_timestamp() AS generated_at
FROM (SELECT recommendation_id, prompt,
        -- generous token budget: the endpoint may spend tokens on internal reasoning before the 2 visible sentences
        ai_query('{LLM}', prompt, modelParameters => named_struct('max_tokens', 2000), failOnError => false) AS r
      FROM llm_input)
""")
print(spark.sql(f"SELECT count(*) AS rows, count(llm_explanation) AS ok, count(llm_error) AS errors, percentile(length(llm_explanation), 0.5) AS median_chars FROM {FQ}.risk_explanations").toPandas().to_string(index=False))
```

**Output**

```text
rows  ok  errors  median_chars
  400 400       0         362.0
```

## Cell 4

```python
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.risk_recommendations
CLUSTER BY (region, risk_tier)
COMMENT 'Published, ranked stockout-risk recommendations per store/SKU for planners (synced to Lakebase for the planner app). Decision support only - nothing is ordered automatically.'
TBLPROPERTIES (delta.enableChangeDataFeed = true)
AS SELECT s.*,
  coalesce(e.llm_explanation,
    concat(s.sku_name, ' at ', s.store_name, ' has a ', round(s.stockout_probability * 100), '% chance of running out in the next ',
           s.lead_time_window_days, ' days (', s.primary_driver, '). Suggested: ', s.recommended_action,
           CASE WHEN s.recommended_qty > 0 THEN concat(' ', s.recommended_qty, ' units.') ELSE '.' END)) AS planner_explanation,
  e.llm_explanation IS NOT NULL AS explanation_is_llm
FROM {FQ}.risk_scores s LEFT JOIN {FQ}.risk_explanations e USING (recommendation_id)
""")
spark.sql(f"ALTER TABLE {FQ}.risk_recommendations ALTER COLUMN recommendation_id SET NOT NULL")
spark.sql(f"ALTER TABLE {FQ}.risk_recommendations DROP CONSTRAINT IF EXISTS risk_recommendations_pk")
spark.sql(f"ALTER TABLE {FQ}.risk_recommendations ADD CONSTRAINT risk_recommendations_pk PRIMARY KEY (recommendation_id)")
```

## Cell 5

```python
import json
sample = spark.sql(f"""SELECT risk_rank, store_name, sku_name, risk_score, risk_tier, recommended_action, recommended_qty, planner_explanation
  FROM {FQ}.risk_recommendations WHERE explanation_is_llm ORDER BY risk_rank LIMIT 10""").toPandas()
for r in sample.itertuples():
    print(f"#{r.risk_rank} [{r.risk_tier} {r.risk_score}] {r.sku_name} @ {r.store_name} -> {r.recommended_action} {r.recommended_qty}\n   {r.planner_explanation}\n")
with open(f"{EVIDENCE}/05c_genai_explanations.json", "w") as fh:
    json.dump({"llm_endpoint": LLM, "explanations": int(spark.table(f'{FQ}.risk_explanations').count()),
               "non_empty": int(spark.sql(f"SELECT count(llm_explanation) FROM {FQ}.risk_explanations").first()[0]),
               "samples": sample.to_dict(orient="records")}, fh, indent=2, default=str)
```

**Output**

```text
#1 [Critical 100] Meadow Fresh Green Beans 2ct @ Harvest Lane Stonebrook Superstore II -> EXPEDITE 348
   Only 46 units are on hand against 255.3 units of forecast demand over the 3-day window (usual 230.2), and the 348 inbound units are late, now projected to arrive in 5 days, after the window closes. Ask Riverbend Fresh Supply Co. to expedite the 348 delayed PO units.

#2 [Critical 100] Harvest Lane Heavy Cream Large @ Harvest Lane Oakhurst Superstore II -> EXPEDITE 138
   Harvest Lane Heavy Cream Large has 0 units on hand and no inbound units arriving within the 3-day window, while forecast demand of 139.7 units (usual 88.9) is pushed up by a promotion adding 51 units, and its 138 late inbound units are now projected to arrive in 4 days. Expedite 138 units by asking Summit Dairy Wholesale to speed up the delayed PO units to cover the $820.0 in revenue at risk.

#3 [Critical 100] Crestline Sweet Potatoes Value Pack @ Harvest Lane Yarrow Superstore -> EXPEDITE 192
   Forecast demand of 425.1 units over the next 4 days far exceeds the 86 units on hand, driven by a promotion adding 248 units versus usual, and the 192 inbound units are late and now projected to arrive in 2 days. Ask Pacific Fresh Foods to expedite the 192 delayed PO units.

#4 [Critical 100] Meadow Fresh Green Beans 2ct @ Harvest Lane Thornbury Standard II -> EXPEDITE 204
   Meadow Fresh Green Beans 2ct at Harvest Lane Thornbury Standard II is likely to run out because only 53 units are on hand against 164.5 units of forecast demand in the 3-day window, and its 204 inbound units are late and now projected to arrive in 4 days. Ask Riverbend Fresh Supply Co. to expedite the delayed PO for 204 units.

#5 [Critical 100] Harvest Lane Peanut Butter Organic @ Harvest Lane Stonebrook Superstore II -> REORDER 96
   With zero units on hand, 372 inbound units are running late (now projected to arrive in 1 day, with 1 PO line overdue and supplier on-time at 83% over the last 30 days), while a promotion lifts forecast demand to 450.9 units over the 13-day window versus a usual 234.3. Place a reorder of 96 units with Summit Pantry Foods (case pack 6) to cover the shortfall.

#6 [Critical 100] Crestline Sweet Potatoes Value Pack @ Harvest Lane Dunmore Superstore -> EXPEDITE 192
   Crestline Sweet Potatoes Value Pack at Harvest Lane Dunmore Superstore has 0 units on hand, its 192 inbound units are late and now projected in 2 days, and an upcoming promotion pushes forecast demand to 296.3 units over the 4-day window (usual: 135.0). Ask Pacific Fresh Foods to expedite 192 delayed PO units to protect the $532.0 in revenue at risk.

#7 [Critical 100] Meadow Fresh 2% Milk Organic @ Harvest Lane Juniper Bay Superstore II -> EXPEDITE 84
   Meadow Fresh 2% Milk Organic at Harvest Lane Juniper Bay Superstore II is likely to run out because 46 units on hand and no inbound arriving in the 5-day window cannot cover 141.1 forecast units, and the 84 late inbound units are now projected 6 days out, with the supplier on time only 58% of the time over the last 30 days. Ask Summit Dairy Wholesale to expedite 84 delayed PO units.

#8 [Critical 100] Green Valley Oat Milk Value Pack @ Harvest Lane Riverside Standard -> EXPEDITE 40
   Green Valley Oat Milk Value Pack at Harvest Lane Riverside Standard is likely to run out because only 16 units are on hand, none arrive within the 5-day window, and forecast demand of 74.5 units exceeds that supply, while 40 late inbound units are now projected in 6 days and the supplier has been on time only 58% of the time over the last 30 days. Expedite 40 units by asking Summit Dairy Wholesale to speed up the delayed PO units.

#9 [Critical 100] Green Valley Oat Milk Value Pack @ Harvest Lane Fairhaven Standard II -> EXPEDITE 60
   The Green Valley Oat Milk Value Pack at Harvest Lane Fairhaven Standard II has a 100.0% stockout probability in the 5-day window because its 60 late inbound units are now projected to arrive in 6 days, leaving 13 units on hand against 70.7 units of forecast demand. Ask Summit Dairy Wholesale to expedite 60 units from the delayed PO.

#10 [Critical 100] Blue Harbor Large Eggs 2ct @ Harvest Lane Oakhurst Superstore II -> EXPEDITE 42
   Blue Harbor Large Eggs 2ct at Harvest Lane Oakhurst Superstore II has only 16 units on hand against 75.5 units of forecast demand in the 5-day window, and its 42 inbound units are late, now projected in 6 days, with the supplier on time just 58% of the time over the last 30 days. Expedite 42 units by asking Summit Dairy Wholesale to speed up the delayed PO units.
```
