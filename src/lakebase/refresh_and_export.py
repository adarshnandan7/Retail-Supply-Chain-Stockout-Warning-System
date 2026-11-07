# Databricks notebook source
# MAGIC %md
# MAGIC # 08 - Lakebase operational serving: refresh the app's read model and land planner actions in Delta
# MAGIC
# MAGIC * **Delta -> Lakebase**: refresh the snapshot synced table `risk_recommendations_online` so the planner app reads the
# MAGIC   newest ranked risks from Postgres with millisecond latency.
# MAGIC * **Lakebase -> Delta**: copy the app's transactional state (planner decisions, overrides, notes, watchlists) into
# MAGIC   Delta (`planner_action_history`, ...) so analytical history and KPIs (time to planner action, override rate,
# MAGIC   alert precision vs. planner judgement) live next to the forecasts in Unity Catalog.

# COMMAND ----------

# MAGIC %pip install -q "psycopg[binary]==3.2.9" "databricks-sdk>=0.81.0"
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("lakebase_endpoint", "projects/inventory-risk-radar/branches/production/endpoints/primary")
dbutils.widgets.text("pg_database", "inventory_risk_app")
dbutils.widgets.text("app_sp_client_id", "")
APP_SP = dbutils.widgets.get("app_sp_client_id")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
ENDPOINT = dbutils.widgets.get("lakebase_endpoint")
PG_DB = dbutils.widgets.get("pg_database")
SYNCED = f"{FQ}.risk_recommendations_online"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"

# COMMAND ----------

import json, time
import pandas as pd
import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
st = w.postgres.get_synced_table(name=f"synced_tables/{SYNCED}")
pipeline_id = st.status.pipeline_id if st.status else None
print("synced table:", st.name, "| pipeline:", pipeline_id)
upd = w.pipelines.start_update(pipeline_id=pipeline_id, full_refresh=False)
t0 = time.time()
while True:
    u = w.pipelines.get_update(pipeline_id=pipeline_id, update_id=upd.update_id).update
    if u.state.value in ("COMPLETED", "FAILED", "CANCELED"):
        break
    time.sleep(15)
print(f"sync update {upd.update_id}: {u.state.value} in {time.time() - t0:.0f}s")
assert u.state.value == "COMPLETED", "synced table refresh failed"

# COMMAND ----------

ep = w.postgres.get_endpoint(name=ENDPOINT)
token = w.postgres.generate_database_credential(endpoint=ENDPOINT).token
conn = psycopg.connect(host=ep.status.hosts.host, dbname=PG_DB, user=w.current_user.me().user_name, password=token,
                       sslmode="require", autocommit=True)

def pg(sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description]) if cur.description else None

# the snapshot refresh can recreate the Postgres table, so (re)grant the app's Postgres role read access every run
if APP_SP:
    pg(f'GRANT USAGE ON SCHEMA "{SCHEMA}" TO "{APP_SP}"')
    pg(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{SCHEMA}" TO "{APP_SP}"')
    if pg("SELECT count(*) AS n FROM information_schema.schemata WHERE schema_name = 'app'").n.iloc[0] > 0:
        pg(f'GRANT USAGE, CREATE ON SCHEMA app TO "{APP_SP}"')
        pg(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO "{APP_SP}"')
        pg(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO "{APP_SP}"')
    print("granted Lakebase privileges to app role", APP_SP)

checks = {}
checks["synced_rows_by_tier"] = pg(f'SELECT risk_tier, count(*) AS rows FROM "{SCHEMA}"."risk_recommendations_online" GROUP BY 1 ORDER BY 2 DESC')
t = time.time(); top = pg(f'SELECT risk_rank, store_name, sku_name, risk_score, recommended_action FROM "{SCHEMA}"."risk_recommendations_online" WHERE region = \'Metro North\' AND risk_tier = \'Critical\' ORDER BY risk_rank LIMIT 10')
checks["point_query_ms"] = round((time.time() - t) * 1000, 1)
checks["top_metro_north"] = top
print(checks["synced_rows_by_tier"].to_string(index=False)); print("point query latency ms:", checks["point_query_ms"]); print(top.to_string(index=False))

# COMMAND ----------

# MAGIC %md ## Lakebase -> Delta: planner actions

# COMMAND ----------

has_app = pg("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema = 'app'").n.iloc[0] > 0
exported = {}
if has_app:
    for tbl in ["planner_actions", "planner_notes", "watchlists"]:
        df = pg(f"SELECT * FROM app.{tbl}")
        target = {"planner_actions": "planner_action_history", "planner_notes": "planner_note_history", "watchlists": "planner_watchlists"}[tbl]
        if len(df):
            for c in df.columns:
                if str(df[c].dtype).startswith("datetime64[ns,"):
                    df[c] = df[c].dt.tz_convert("UTC").dt.tz_localize(None)
            spark.createDataFrame(df).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{FQ}.{target}")
            spark.sql(f"COMMENT ON TABLE {FQ}.{target} IS 'Copy of Lakebase app.{tbl} (planner app transactional state) for analytics.'")
        exported[target] = len(df)
    if exported.get("planner_action_history"):
        kpi = spark.sql(f"""
          SELECT count(*) AS decisions, count_if(is_override) AS overrides, round(avg(CASE WHEN is_override THEN 1 ELSE 0 END), 3) AS override_rate,
                 count(DISTINCT planner) AS planners,
                 round(percentile_approx((unix_timestamp(a.created_at) - unix_timestamp(r.scored_at)) / 3600.0, 0.5), 2) AS median_hours_to_action
          FROM {FQ}.planner_action_history a JOIN {FQ}.risk_recommendations r
            ON a.recommendation_id = r.recommendation_id AND a.as_of_date = r.as_of_date AND a.created_at >= r.scored_at""").toPandas()
        checks["planner_kpis_from_delta"] = kpi
        print(kpi.to_string(index=False))
print("exported:", exported)
conn.close()

# COMMAND ----------

with open(f"{EVIDENCE}/08_lakebase.json", "w") as fh:
    json.dump({"synced_table": SYNCED, "pipeline_id": pipeline_id, "sync_state": u.state.value, "exported_to_delta": exported,
               **{k: (v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v) for k, v in checks.items()}}, fh, indent=2, default=str)
