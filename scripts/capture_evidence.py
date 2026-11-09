"""Capture text-readable execution evidence for a completed end-to-end job run into evidence/.

Usage: uv run --with databricks-sdk --with "psycopg[binary]" python scripts/capture_evidence.py <job_run_id>
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient

sys.path.insert(0, str(Path(__file__).parent))
from run_sql import run, to_md  # noqa: E402

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "serverless-stable-3vku19")
CAT, SCH = "serverless_stable_3vku19_catalog", "inventory_risk"
FQ = f"{CAT}.{SCH}"
ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
w = WorkspaceClient(profile=PROFILE)


def sql_section(title, sql):
    cols, rows = run(sql, w)
    return f"\n### {title}\n\n```sql\n{sql.strip()}\n```\n\n{to_md(cols, rows)}\n"


def write(name, header, body):
    (EV / name).write_text(f"# {header}\n\n_Captured {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} from workspace `{w.config.host}`._\n{body}")
    print("wrote", name)


def main(run_id: int):
    EV.mkdir(exist_ok=True)
    (EV / "run_summaries").mkdir(exist_ok=True)

    # ---- 1. job run ----
    r = w.jobs.get_run(run_id)
    lines = [f"\n- Job: `{r.run_name}` (job id `{r.job_id}`)\n- Run id: `{run_id}`\n- Result: **{r.state.result_state.value}**\n",
             f"- Started: {datetime.fromtimestamp(r.start_time / 1000, timezone.utc):%Y-%m-%d %H:%M:%S UTC}\n",
             f"- Run page: {r.run_page_url}\n\n| Task | Result | Duration (s) | Task run id |\n|---|---|---|---|\n"]
    for t in sorted(r.tasks, key=lambda t: t.start_time or 0):
        lines.append(f"| {t.task_key} | {t.state.result_state.value if t.state.result_state else t.state.life_cycle_state.value} | "
                     f"{round((t.execution_duration or 0) / 1000)} | `{t.run_id}` |\n")
    write("01_job_run_summary.md", "End-to-end job run", "".join(lines))

    # ---- 2. raw run summaries written by each task to the evidence volume ----
    for f in w.files.list_directory_contents(f"/Volumes/{CAT}/{SCH}/evidence"):
        if f.name.endswith(".json"):
            body = w.files.download(f.path).contents.read()
            (EV / "run_summaries" / f.name).write_bytes(body)
    print("downloaded run summaries")

    # ---- 3. pipeline data quality ----
    pid = [t for t in r.tasks if t.task_key == "lakeflow_pipeline"][0].pipeline_task.pipeline_id
    body = sql_section("Expectation results (latest update)", f"""
SELECT origin.flow_name AS flow, e.name AS expectation, sum(e.passed_records) AS passed, sum(e.failed_records) AS failed
FROM event_log('{pid}') l
LATERAL VIEW explode(from_json(l.details:flow_progress.data_quality.expectations,
  'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) x AS e
WHERE l.event_type = 'flow_progress' AND l.details:flow_progress.data_quality IS NOT NULL
  AND l.origin.update_id = (SELECT origin.update_id FROM event_log('{pid}') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1)
GROUP BY ALL ORDER BY flow, expectation""")
    body += sql_section("Flow completion (latest update)", f"""
SELECT origin.flow_name AS flow, details:flow_progress.status AS status, details:flow_progress.metrics.num_output_rows AS output_rows, timestamp
FROM event_log('{pid}')
WHERE event_type = 'flow_progress' AND details:flow_progress.status IN ('COMPLETED', 'FAILED')
  AND origin.update_id = (SELECT origin.update_id FROM event_log('{pid}') WHERE event_type = 'create_update' ORDER BY timestamp DESC LIMIT 1)
ORDER BY timestamp""")
    write("02_pipeline_data_quality.md", "Lakeflow pipeline: data quality and flow progress", f"\nPipeline id `{pid}`.\n" + body)

    # ---- 4. table profiles ----
    tables = ["bronze_pos_sales", "silver_pos_sales", "bronze_inventory_snapshots", "silver_inventory_snapshots", "bronze_po_events",
              "silver_po_events", "gold_daily_store_sku_sales", "gold_po_lines", "gold_inbound_po_pipeline", "gold_supplier_lead_time_stats",
              "gold_current_inventory_position", "gold_promo_store_sku_daily", "forecast_backtest", "demand_forecast", "risk_scores",
              "risk_backtest", "risk_explanations", "risk_recommendations", "planner_action_history"]
    union = "\nUNION ALL ".join(f"SELECT '{t}' AS table_name, count(*) AS row_count FROM {FQ}.{t}" for t in tables)
    body = sql_section("Row counts by layer", union)
    body += sql_section("Sample: gold_daily_store_sku_sales", f"SELECT * FROM {FQ}.gold_daily_store_sku_sales WHERE store_id = 'S001' AND sku_id = 'P00043' ORDER BY sale_date DESC LIMIT 8")
    body += sql_section("Sample: gold_supplier_lead_time_stats (worst on-time first)", f"SELECT * FROM {FQ}.gold_supplier_lead_time_stats ORDER BY on_time_rate_last_30d LIMIT 8")
    body += sql_section("Sample: demand_forecast", f"SELECT * FROM {FQ}.demand_forecast WHERE store_id = 'S001' AND sku_id = 'P00043' ORDER BY horizon LIMIT 10")
    body += sql_section("Unity Catalog tags on published objects", f"""SELECT table_name, collect_list(concat(tag_name, '=', tag_value)) AS tags
FROM {CAT}.information_schema.table_tags WHERE schema_name = '{SCH}' AND table_name IN ('risk_recommendations','planner_risk_queue','mv_inventory_risk','gold_daily_store_sku_sales','demand_forecast')
GROUP BY table_name ORDER BY table_name""")
    write("03_table_profiles.md", "Table profiles across bronze / silver / gold / ML / serving", body)

    # ---- 5. model ----
    mc = json.loads((EV / "run_summaries" / "04_model_comparison.json").read_text())
    mv = w.model_versions.get_by_alias(f"{FQ}.demand_forecast", "champion")
    rows = "".join(f"| {c['category']} | {c['baseline_wape']:.3f} | {c['lgbm_wape']:.3f} | {c['wape_reduction_pct']} |\n" for c in mc["by_category"])
    feats = "".join(f"| {f['feature']} | {f['gain']:.0f} |\n" for f in mc["top_features"])
    body = (f"\n- MLflow experiment: `{mc['experiment']}`\n- Baseline run: `{mc['mlflow_runs']['baseline']}` | LightGBM run: `{mc['mlflow_runs']['lightgbm']}`\n"
            f"- Registered model: `{mc['registered_model']}` version **{mv.version}** with alias **@champion** (status {mv.status.value if mv.status else ''})\n"
            f"- Holdout origin {mc['holdout_origin']}; {mc['holdout_rows_scored']:,} store/SKU/day rows scored (stockout days excluded); {mc['train_rows']:,} training rows\n\n"
            "| Metric | Seasonal naive (baseline) | LightGBM (champion) |\n|---|---|---|\n"
            + "".join(f"| {k} | {mc['baseline'][k]} | {mc['lightgbm'][k]} |\n" for k in mc["baseline"])
            + f"\n**WAPE reduction vs baseline: {mc['wape_reduction_pct']}%**\n\n### By category\n\n| Category | Baseline WAPE | Model WAPE | Reduction % |\n|---|---|---|---|\n{rows}"
            f"\n### Top features (gain)\n\n| Feature | Gain |\n|---|---|\n{feats}")
    body += sql_section("Metric view check: WAPE promo vs regular days", f"SELECT on_promo, ROUND(MEASURE(model_wape), 4) AS model_wape, ROUND(MEASURE(baseline_wape), 4) AS baseline_wape, ROUND(MEASURE(wape_improvement_pct), 1) AS improvement_pct FROM {FQ}.mv_forecast_accuracy GROUP BY ALL")
    write("04_model_comparison.md", "Demand forecast: baseline vs champion model", body)

    # ---- 6. risk + backtest ----
    rs = json.loads((EV / "run_summaries" / "05b_risk_scoring.json").read_text())
    bt = rs["backtest"]
    bt_rows = "".join(f"| {k} | {v['alerts']} | {v['true_positives']} | {v['false_positives']} | {v['missed_stockouts']} | {v['precision']:.1%} | {v['recall']:.1%} |\n"
                      for k, v in bt.items() if isinstance(v, dict))
    body = (f"\n- Scored {rs['series_scored']:,} store/SKUs as of {rs['as_of_date']}\n- Tiers: {rs['tiers']}\n- Suggested actions: {rs['actions']}\n"
            f"- Primary drivers (Critical+High): {rs['primary_drivers_critical_high']}\n- Revenue at risk (Critical+High): ${rs['revenue_at_risk_critical_high']:,.0f}\n")
    body += sql_section("Top 20 ranked risks", f"""SELECT risk_rank, risk_tier, risk_score, store_name, sku_name, on_hand_units, inbound_units_in_window, forecast_demand_window,
  lead_time_window_days, projected_stockout_in_days, round(stockout_probability, 3) AS p_stockout, round(revenue_at_risk, 0) AS revenue_at_risk,
  primary_driver, recommended_action, recommended_qty, action_source_id FROM {FQ}.risk_recommendations ORDER BY risk_rank LIMIT 20""")
    body += sql_section("Gen AI planner notes (ai_query) for the top 8", f"SELECT risk_rank, sku_name, store_name, planner_explanation FROM {FQ}.risk_recommendations WHERE explanation_is_llm ORDER BY risk_rank LIMIT 8")
    body += sql_section("LLM output completeness", f"SELECT count(*) AS prompts, count(llm_explanation) AS non_empty, count(llm_error) AS errors, percentile(length(llm_explanation), 0.5) AS median_chars, max(llm_endpoint) AS endpoint FROM {FQ}.risk_explanations")
    body += sql_section("Expedite opportunities grouped by supplier (one call covers many store/SKUs)", f"""SELECT supplier_name, count(*) AS store_skus, sum(recommended_qty) AS units_to_expedite, round(sum(revenue_at_risk), 0) AS revenue_at_risk
FROM {FQ}.risk_recommendations WHERE recommended_action = 'EXPEDITE' GROUP BY supplier_name ORDER BY store_skus DESC LIMIT 8""")
    write("05_risk_recommendations.md", "Inventory-risk scoring, drivers, actions and Gen AI notes", body)
    write("06_backtest_alert_precision.md", "Backtest: would the radar have warned planners 4 weeks ago?",
          f"\nRisk scored as of **{bt['backtest_origin']}** using only information available that day, then compared with what actually happened "
          f"(end-of-day on hand = 0 within the item's replenishment window). Items already out of stock at the origin are excluded "
          f"({bt['series_already_out_of_stock_excluded']}); {bt['series_evaluated_with_stock_on_hand']:,} store/SKUs evaluated, "
          f"{bt['actual_stockouts_in_window']:,} actually stocked out.\n\n| Method | Alerts | True positives | False positives | Missed | Precision | Recall |\n|---|---|---|---|---|---|---|\n{bt_rows}"
          f"\nRule of thumb = today's process: alert when trailing days of cover < supplier contract lead time.\n"
          + sql_section("Same result via the governed metric view", f"SELECT MEASURE(radar_alerts) AS radar_alerts, ROUND(MEASURE(radar_alert_precision), 4) AS radar_precision, ROUND(MEASURE(radar_alert_recall), 4) AS radar_recall, MEASURE(rule_alerts) AS rule_alerts, ROUND(MEASURE(rule_alert_precision), 4) AS rule_precision, ROUND(MEASURE(rule_alert_recall), 4) AS rule_recall FROM {FQ}.mv_alert_backtest"))

    # ---- 7. Genie ----
    space_id = os.environ["GENIE_SPACE_ID"]
    qs = ["Which 5 store-SKUs have the highest revenue at risk right now?",
          "How many Critical and High risks are there by region?",
          "Which suppliers are causing the most late-delivery risks?",
          "What is the forecast WAPE of the model vs the baseline by category?",
          "What was the alert precision of the radar compared with the rule of thumb?",
          "Explain the recommendation for green beans at Stonebrook",
          "How good are the Gen AI planner notes?"]
    out = [f"\nGenie space `{space_id}` (bundle resource `inventory_risk_genie`). Questions asked through the Genie Conversation API.\n"]
    for qn in qs:
        msg = w.genie.start_conversation_and_wait(space_id, qn)
        out.append(f"\n## Q: {qn}\n\nStatus: {msg.status.value if msg.status else ''}\n")
        for att in msg.attachments or []:
            if att.text and att.text.content:
                out.append(f"\n**Answer text:** {att.text.content}\n")
            if att.query:
                out.append(f"\n**Description:** {att.query.description}\n\n```sql\n{att.query.query}\n```\n")
                try:
                    res = w.genie.get_message_attachment_query_result(space_id, msg.conversation_id, msg.id, att.attachment_id).statement_response
                    cols = [c.name for c in res.manifest.schema.columns]
                    out.append("\n" + to_md(cols, (res.result.data_array or [])[:12]) + "\n")
                except Exception as e:  # keep capturing the rest
                    out.append(f"\n(result fetch failed: {e})\n")
        time.sleep(2)
    write("07_genie_answers.md", "Genie: natural-language questions over the governed risk data", "".join(out))

    # ---- 7b. Gen AI note evaluation ----
    ge = json.loads((EV / "run_summaries" / "05d_genai_eval.json").read_text())
    m = ge["metrics"]
    body = (f"\n- Writer: `{ge['writer_endpoint']}` | Judge: `{ge['judge_endpoint']}` (a different model)\n- MLflow experiment `{ge['experiment']}`, run `{ge['mlflow_run_id']}`\n"
            f"- Quality gate (final pass rate >= {ge['min_pass_rate']:.0%}): **{ge['quality_gate']}**; {ge['notes_replaced_by_template']} failing notes replaced by the deterministic template before publishing\n\n"
            "| Metric | Value |\n|---|---|\n" + "".join(f"| {k} | {v:.3f} |\n" if isinstance(v, float) else f"| {k} | {v} |\n" for k, v in m.items()))
    body += sql_section("Failing notes and why (judge issue / unsupported numbers)", f"""SELECT recommendation_id, recommended_action, recommended_qty, unsupported_numbers, action_match, quantity_match, sentence_count,
  judge_faithfulness, judge_verdict, judge_issue FROM {FQ}.risk_explanation_eval WHERE NOT final_pass ORDER BY judge_faithfulness LIMIT 10""")
    body += sql_section("Passing notes (sample)", f"SELECT recommendation_id, judge_faithfulness, judge_actionability, judge_clarity, llm_explanation FROM {FQ}.risk_explanation_eval WHERE final_pass LIMIT 4")
    body += sql_section("Published notes: LLM vs template after the gate", f"SELECT explanation_is_llm, count(*) AS rows FROM {FQ}.risk_recommendations WHERE risk_tier IN ('Critical','High') GROUP BY 1")
    write("12_genai_note_evaluation.md", "Gen AI planner notes: evaluation and quality gate", body)

    # ---- 7c. Row filter / mask enforcement ----
    gv = json.loads((EV / "run_summaries" / "06_governance.json").read_text())["enforcement_test"]
    fmt = lambda rows: "| region | rows visible | revenue values visible |\n|---|---|---|\n" + "".join(f"| {r['region']} | {r['rows_visible']} | {r['revenue_values_visible']} |\n" for r in rows)
    body = (f"\nTest identity: `{gv['principal']}` (the job's run-as user). The job maps it to **Valley only, without financials**, queries "
            f"`planner_risk_queue`, then removes the mapping. Assertions in the job: row filter enforced = **{gv['row_filter_enforced']}**, "
            f"mask enforced = **{gv['mask_enforced']}**.\n\n### Before mapping (admin, unmapped)\n\n{fmt(gv['before_mapping'])}"
            f"\n### Mapped to Valley, no financials\n\n{fmt(gv['mapped_to_valley_no_financials'])}\n### After mapping removed\n\n{fmt(gv['after_mapping_removed'])}"
            "\n### Policies attached to the table (`DESCRIBE TABLE EXTENDED`)\n\n| item | value |\n|---|---|\n"
            + "".join(f"| {r['col_name']} | {r['data_type']} |\n" for r in gv["describe_row_filter_and_mask"] if r["data_type"]))
    body += sql_section("Row filter and mask functions", f"""SELECT routine_name, routine_definition FROM {CAT}.information_schema.routines
WHERE routine_schema = '{SCH}' AND routine_name IN ('region_row_filter', 'mask_revenue') ORDER BY 1""")
    write("13_row_filter_enforcement.md", "Unity Catalog row filter and column mask: enforcement test", body)

    # ---- 7d. Drift monitoring ----
    body = sql_section("model_monitoring (every drift check, newest first)", f"""SELECT checked_at, as_of_date, champion_version, champion_current_wape, champion_registered_wape, baseline_current_wape,
  degradation_pct, drift_threshold_pct, retrain, reasons FROM {FQ}.model_monitoring ORDER BY checked_at DESC LIMIT 10""")
    for rid in [x for x in os.environ.get("DRIFT_RUNS", str(run_id)).split(",") if x]:
        rr = w.jobs.get_run(int(rid))
        params = {p.name: p.value for p in (rr.job_parameters or [])}
        body += (f"\n### Job run `{rid}` (drift_threshold_pct = {params.get('drift_threshold_pct', '10')}) - {rr.state.result_state.value if rr.state.result_state else ''}\n\n"
                 "| Task | Result |\n|---|---|\n" + "".join(
                     f"| {t.task_key} | {t.state.result_state.value if t.state.result_state else t.state.life_cycle_state.value} |\n"
                     for t in sorted(rr.tasks, key=lambda t: t.start_time or 9e15) if t.task_key in ("drift_check", "needs_retrain", "train_forecast", "batch_forecast")))
    vers = w.model_versions.list(f"{FQ}.demand_forecast")
    body += "\n### Registered model versions\n\n| version | created | aliases |\n|---|---|---|\n"
    champ = w.model_versions.get_by_alias(f"{FQ}.demand_forecast", "champion").version
    for v in sorted(vers, key=lambda v: v.version):
        body += f"| {v.version} | {datetime.fromtimestamp(v.created_at / 1000, timezone.utc):%Y-%m-%d %H:%M} | {'@champion' if v.version == champ else ''} |\n"
    write("14_drift_monitoring.md", "Forecast drift check and conditional retraining", body)

    # ---- 8. Lakebase ----
    lb = json.loads((EV / "run_summaries" / "08_lakebase.json").read_text())
    import psycopg
    ep = "projects/inventory-risk-radar/branches/production/endpoints/primary"
    host = w.postgres.get_endpoint(name=ep).status.hosts.host
    conn = psycopg.connect(host=host, dbname="inventory_risk_app", user=w.current_user.me().user_name,
                           password=w.postgres.generate_database_credential(endpoint=ep).token, sslmode="require", autocommit=True)

    def pgmd(title, q):
        with conn.cursor() as cur:
            t0 = time.time(); cur.execute(q); rows = cur.fetchall(); ms = (time.time() - t0) * 1000
            return f"\n### {title} ({ms:.0f} ms)\n\n```sql\n{q}\n```\n\n" + to_md([d.name for d in cur.description], rows) + "\n"
    body = (f"\n- Project `inventory-risk-radar` (Lakebase Autoscaling, PG 17), database `inventory_risk_app`\n- Synced table `{lb['synced_table']}` "
            f"(snapshot), sync pipeline `{lb['pipeline_id']}`, last refresh: **{lb['sync_state']}**\n- Exported to Delta this run: {lb['exported_to_delta']}\n")
    body += pgmd("Synced read model by tier", 'SELECT risk_tier, count(*) AS rows, max(as_of_date) AS as_of FROM inventory_risk.risk_recommendations_online GROUP BY 1 ORDER BY 2')
    body += pgmd("App point query: Critical items in one region", "SELECT risk_rank, store_name, sku_name, risk_score, recommended_action, recommended_qty FROM inventory_risk.risk_recommendations_online WHERE region = 'Metro North' AND risk_tier = 'Critical' ORDER BY risk_rank LIMIT 5")
    body += pgmd("App-state tables", "SELECT table_name FROM information_schema.tables WHERE table_schema = 'app' ORDER BY 1")
    body += pgmd("Planner decisions written by the app", "SELECT created_at, planner, action_type, action_qty, is_override, recommended_action, risk_tier, reason FROM app.planner_actions ORDER BY created_at DESC LIMIT 10")
    body += pgmd("Planner notes", "SELECT created_at, planner, note FROM app.planner_notes ORDER BY created_at DESC LIMIT 5")
    body += pgmd("Privileges of the app service principal", "SELECT grantee, table_schema, table_name, string_agg(privilege_type, ',') AS privileges FROM information_schema.role_table_grants WHERE grantee NOT IN ('PUBLIC') AND table_schema IN ('app','inventory_risk') GROUP BY 1,2,3 ORDER BY 2,3")
    conn.close()
    body += sql_section("Lakebase -> Delta: planner_action_history in Unity Catalog", f"SELECT created_at, planner, action_type, action_qty, is_override, recommended_action, recommendation_id FROM {FQ}.planner_action_history ORDER BY created_at DESC LIMIT 10")
    write("08_lakebase_checks.md", "Lakebase operational serving and app state", body)

    # ---- 9. bundle ----
    summ = subprocess.run(["databricks", "bundle", "summary", "-o", "json"], cwd=ROOT, capture_output=True, text=True).stdout
    res = json.loads(summ)["resources"]
    lines = ["\nAll resources below are defined in `databricks.yml` + `resources/*.yml` and deployed with `databricks bundle deploy`.\n\n| Type | Key | Id / name | URL |\n|---|---|---|---|\n"]
    for typ, items in res.items():
        for key, v in items.items():
            ident = v.get("id") or v.get("name") or v.get("project_id") or ""
            lines.append(f"| {typ} | {key} | `{ident}` | {v.get('url', '')} |\n")
    val = subprocess.run(["databricks", "bundle", "validate"], cwd=ROOT, capture_output=True, text=True)
    lines.append(f"\n### `databricks bundle validate`\n\n```text\n{(val.stdout + val.stderr).strip()}\n```\n")
    app = w.apps.get("inventory-risk-radar")
    lines.append(f"\n### App status\n\n- URL: {app.url}\n- Compute: {app.compute_status.state.value if app.compute_status else ''} | App: {app.app_status.state.value if app.app_status else ''}"
                 f"\n- Service principal: `{app.service_principal_client_id}`\n- Active deployment: `{app.active_deployment.deployment_id if app.active_deployment else ''}`\n")
    write("09_bundle_resources.md", "Databricks Asset Bundle: deployed resources", "".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]))
