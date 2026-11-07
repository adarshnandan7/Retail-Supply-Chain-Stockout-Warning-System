# End-to-end job run

_Captured 2026-11-07 14:11 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- Job: `inventory-risk-radar-e2e` (job id `503908077041202`)
- Run id: `465476598725505`
- Result: **SUCCESS**
- Started: 2026-11-07 13:51:06 UTC
- Run page: https://fevm-serverless-stable-3vku19.cloud.databricks.com/?o=7474656932908638#job/503908077041202/run/465476598725505

| Task | Result | Duration (s) | Task run id |
|---|---|---|---|
| generate_raw_data | SUCCESS | 226 | `1063207499416537` |
| lakeflow_pipeline | SUCCESS | 172 | `334947631201403` |
| train_forecast | SUCCESS | 275 | `745938303385983` |
| batch_forecast | SUCCESS | 64 | `598486591863471` |
| score_risk | SUCCESS | 40 | `842884710569891` |
| genai_explanations | SUCCESS | 158 | `409117182177508` |
| apply_governance | SUCCESS | 70 | `105227783949572` |
| metric_views | SUCCESS | 26 | `829500589129562` |
| lakebase_sync_and_export | SUCCESS | 129 | `531750778966372` |
