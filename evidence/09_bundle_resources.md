# Databricks Asset Bundle: deployed resources

_Captured 2026-11-09 13:30 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

All resources below are defined in `databricks.yml` + `resources/*.yml` and deployed with `databricks bundle deploy`.

| Type | Key | Id / name | URL |
|---|---|---|---|
| apps | planner_app | `inventory-risk-radar` |  |
| dashboards | inventory_risk_dashboard | `01f1dab0696011c59ee47f670cd5d98e` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/dashboardsv3/01f1dab0696011c59ee47f670cd5d98e/published?w=7474656932908638 |
| experiments | demand_forecast_experiment | `1061037449516920` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/ml/experiments/1061037449516920?w=7474656932908638 |
| experiments | planner_note_eval_experiment | `4029406326013483` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/ml/experiments/4029406326013483?w=7474656932908638 |
| genie_spaces | inventory_risk_genie | `01f1dab0693c13bc83454db2585ad2c2` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/genie/rooms/01f1dab0693c13bc83454db2585ad2c2?w=7474656932908638 |
| jobs | inventory_risk_radar_e2e | `503908077041202` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/jobs/503908077041202?w=7474656932908638 |
| pipelines | inventory_risk_pipeline | `b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/pipelines/b4a2c36c-fd4d-429e-bc88-f7fc9e8a20e1?w=7474656932908638 |
| postgres_databases | app_db | `projects/inventory-risk-radar/branches/production/databases/inventory-risk-app` |  |
| postgres_projects | inventory_risk_lakebase | `projects/inventory-risk-radar` |  |
| postgres_synced_tables | risk_recommendations_online | `synced_tables/serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations_online` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/explore/data/serverless_stable_3vku19_catalog/inventory_risk/risk_recommendations_online?w=7474656932908638 |
| registered_models | demand_forecast | `serverless_stable_3vku19_catalog.inventory_risk.demand_forecast` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/explore/data/models/serverless_stable_3vku19_catalog/inventory_risk/demand_forecast?w=7474656932908638 |
| schemas | inventory_risk | `serverless_stable_3vku19_catalog.inventory_risk` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/explore/data/serverless_stable_3vku19_catalog/inventory_risk?w=7474656932908638 |
| volumes | evidence | `serverless_stable_3vku19_catalog.inventory_risk.evidence` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/explore/data/volumes/serverless_stable_3vku19_catalog/inventory_risk/evidence?w=7474656932908638 |
| volumes | landing | `serverless_stable_3vku19_catalog.inventory_risk.landing` | https://fevm-serverless-stable-3vku19.cloud.databricks.com/explore/data/volumes/serverless_stable_3vku19_catalog/inventory_risk/landing?w=7474656932908638 |

### `databricks bundle validate`

```text
Name: retail_inventory_risk_radar
Target: dev
Workspace:
  Host: https://fevm-serverless-stable-3vku19.cloud.databricks.com
  User: adarsh.nandan@databricks.com
  Path: /Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev

Validation OK!
```

### App status

- URL: https://inventory-risk-radar-7474656932908638.aws.databricksapps.com
- Compute: ACTIVE | App: RUNNING
- Service principal: `f9d7ebf5-8461-4f27-9cf0-7ee975da796a`
- Active deployment: `01f1dab61ad31533bf453da7f50fa1ff`
