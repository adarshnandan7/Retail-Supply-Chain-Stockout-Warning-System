# Databricks notebook source
# MAGIC %md
# MAGIC # 05c - Gen AI planner explanations and the published `risk_recommendations` table
# MAGIC
# MAGIC The risk score and drivers are computed deterministically (05b). Here an LLM served by Databricks
# MAGIC (`ai_query` on a Foundation Model endpoint) only *rephrases* those quantified facts into a two-sentence
# MAGIC note a store or replenishment planner can act on. Every number in the prompt comes from governed tables,
# MAGIC and the model is instructed not to invent any. Lower-tier items get a deterministic template instead,
# MAGIC which keeps cost predictable.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("llm_endpoint", "databricks-claude-haiku-5-5")
dbutils.widgets.text("max_llm_rows", "400")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
LLM = dbutils.widgets.get("llm_endpoint")
MAX_ROWS = int(dbutils.widgets.get("max_llm_rows"))
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"

# COMMAND ----------

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
AS SELECT recommendation_id,
  nullif(trim(r.result), '') AS llm_explanation, r.errorMessage AS llm_error,
  '{LLM}' AS llm_endpoint, current_timestamp() AS generated_at
FROM (SELECT recommendation_id,
        -- generous token budget: the endpoint may spend tokens on internal reasoning before the 2 visible sentences
        ai_query('{LLM}', prompt, modelParameters => named_struct('max_tokens', 2000), failOnError => false) AS r
      FROM llm_input)
""")
print(spark.sql(f"SELECT count(*) AS rows, count(llm_explanation) AS ok, count(llm_error) AS errors, percentile(length(llm_explanation), 0.5) AS median_chars FROM {FQ}.risk_explanations").toPandas().to_string(index=False))

# COMMAND ----------

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

# COMMAND ----------

import json
sample = spark.sql(f"""SELECT risk_rank, store_name, sku_name, risk_score, risk_tier, recommended_action, recommended_qty, planner_explanation
  FROM {FQ}.risk_recommendations WHERE explanation_is_llm ORDER BY risk_rank LIMIT 10""").toPandas()
for r in sample.itertuples():
    print(f"#{r.risk_rank} [{r.risk_tier} {r.risk_score}] {r.sku_name} @ {r.store_name} -> {r.recommended_action} {r.recommended_qty}\n   {r.planner_explanation}\n")
with open(f"{EVIDENCE}/05c_genai_explanations.json", "w") as fh:
    json.dump({"llm_endpoint": LLM, "explanations": int(spark.table(f'{FQ}.risk_explanations').count()),
               "non_empty": int(spark.sql(f"SELECT count(llm_explanation) FROM {FQ}.risk_explanations").first()[0]),
               "samples": sample.to_dict(orient="records")}, fh, indent=2, default=str)
