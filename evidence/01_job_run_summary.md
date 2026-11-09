# End-to-end job run

_Captured 2026-11-09 13:27 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- Job: `inventory-risk-radar-e2e` (job id `503908077041202`)
- Run id: `1079588740947181`
- Result: **SUCCESS**
- Started: 2026-11-09 12:51:38 UTC
- Run page: https://fevm-serverless-stable-3vku19.cloud.databricks.com/?o=7474656932908638#job/503908077041202/run/1079588740947181

| Task | Result | Duration (s) | Task run id |
|---|---|---|---|
| generate_raw_data | SUCCESS | 228 | `1125512045038137` |
| lakeflow_pipeline | SUCCESS | 173 | `694501049959075` |
| drift_check | SUCCESS | 90 | `472196703421925` |
| needs_retrain | SUCCESS | 1 | `307246775067234` |
| train_forecast | EXCLUDED | 0 | `763236794632056` |
| batch_forecast | SUCCESS | 71 | `802445467347544` |
| score_risk | SUCCESS | 54 | `1014406213266521` |
| genai_explanations | SUCCESS | 108 | `914518877414782` |
| evaluate_explanations | SUCCESS | 158 | `728235320267827` |
| apply_governance | SUCCESS | 77 | `446362247060598` |
| metric_views | SUCCESS | 14 | `475118626531516` |
| lakebase_sync_and_export | SUCCESS | 87 | `338308863743829` |
