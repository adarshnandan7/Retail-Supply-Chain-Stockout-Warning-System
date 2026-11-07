# Lakebase operational serving and app state

_Captured 2026-11-07 14:14 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- Project `inventory-risk-radar` (Lakebase Autoscaling, PG 17), database `inventory_risk_app`
- Synced table `serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations_online` (snapshot), sync pipeline `5cbc13ff-b5aa-4181-9ae7-01fa8725a851`, last refresh: **COMPLETED**
- Exported to Delta this run: {'planner_action_history': 1, 'planner_note_history': 1, 'planner_watchlists': 1}

### Synced read model by tier (312 ms)

```sql
SELECT risk_tier, count(*) AS rows, max(as_of_date) AS as_of FROM inventory_risk.risk_recommendations_online GROUP BY 1 ORDER BY 2
```

| risk_tier | rows | as_of |
|---|---|---|
| Critical | 808 | 2026-11-06 |
| Medium | 826 | 2026-11-06 |
| High | 1530 | 2026-11-06 |
| Low | 16832 | 2026-11-06 |

### App point query: Critical items in one region (272 ms)

```sql
SELECT risk_rank, store_name, sku_name, risk_score, recommended_action, recommended_qty FROM inventory_risk.risk_recommendations_online WHERE region = 'Metro North' AND risk_tier = 'Critical' ORDER BY risk_rank LIMIT 5
```

| risk_rank | store_name | sku_name | risk_score | recommended_action | recommended_qty |
|---|---|---|---|---|---|
| 9 | Harvest Lane Fairhaven Standard II | Green Valley Oat Milk Value Pack | 100 | EXPEDITE | 60 |
| 14 | Harvest Lane Kingsley Standard | Crestline Cheddar Block | 100 | EXPEDITE | 36 |
| 16 | Harvest Lane Kingsley Standard II | Golden Fields Heavy Cream | 100 | EXPEDITE | 60 |
| 29 | Harvest Lane Ashford Neighborhood | Golden Fields Heavy Cream | 100 | EXPEDITE | 42 |
| 34 | Harvest Lane Ashford Neighborhood | Crestline Cheddar Block | 100 | EXPEDITE | 24 |

### App-state tables (280 ms)

```sql
SELECT table_name FROM information_schema.tables WHERE table_schema = 'app' ORDER BY 1
```

| table_name |
|---|
| planner_actions |
| planner_notes |
| watchlists |

### Planner decisions written by the app (276 ms)

```sql
SELECT created_at, planner, action_type, action_qty, is_override, recommended_action, risk_tier, reason FROM app.planner_actions ORDER BY created_at DESC LIMIT 10
```

| created_at | planner | action_type | action_qty | is_override | recommended_action | risk_tier | reason |
|---|---|---|---|---|---|---|---|
| 2026-11-07 13:48:32.772058+00:00 | smoke-test@harvestlane.example | EXPEDITE | 348 | False | EXPEDITE | Critical | Smoke test: supplier confirmed expedite |

### Planner notes (313 ms)

```sql
SELECT created_at, planner, note FROM app.planner_notes ORDER BY created_at DESC LIMIT 5
```

| created_at | planner | note |
|---|---|---|
| 2026-11-07 13:48:33.054408+00:00 | smoke-test@harvestlane.example | Called supplier; truck moved up by 2 days |

### Privileges of the app service principal (274 ms)

```sql
SELECT grantee, table_schema, table_name, string_agg(privilege_type, ',') AS privileges FROM information_schema.role_table_grants WHERE grantee NOT IN ('PUBLIC') AND table_schema IN ('app','inventory_risk') GROUP BY 1,2,3 ORDER BY 2,3
```

| grantee | table_schema | table_name | privileges |
|---|---|---|---|
| adarsh.nandan@databricks.com | app | planner_actions | REFERENCES,TRUNCATE,TRIGGER,INSERT,SELECT,UPDATE,DELETE |
| databricks_gateway | app | planner_actions | SELECT |
| databricks_reader_16852 | app | planner_actions | SELECT |
| databricks_superuser | app | planner_actions | INSERT,TRIGGER,REFERENCES,TRUNCATE,DELETE,UPDATE,SELECT |
| f9d7ebf5-8461-4f27-9cf0-7ee975da796a | app | planner_actions | UPDATE,SELECT,INSERT,DELETE |
| adarsh.nandan@databricks.com | app | planner_notes | REFERENCES,TRUNCATE,TRIGGER,INSERT,SELECT,UPDATE,DELETE |
| databricks_gateway | app | planner_notes | SELECT |
| databricks_reader_16852 | app | planner_notes | SELECT |
| databricks_superuser | app | planner_notes | REFERENCES,INSERT,SELECT,UPDATE,DELETE,TRUNCATE,TRIGGER |
| f9d7ebf5-8461-4f27-9cf0-7ee975da796a | app | planner_notes | DELETE,INSERT,SELECT,UPDATE |
| adarsh.nandan@databricks.com | app | watchlists | DELETE,UPDATE,TRIGGER,INSERT,SELECT,REFERENCES,TRUNCATE |
| databricks_gateway | app | watchlists | SELECT |
| databricks_reader_16852 | app | watchlists | SELECT |
| databricks_superuser | app | watchlists | TRUNCATE,INSERT,SELECT,UPDATE,DELETE,REFERENCES,TRIGGER |
| f9d7ebf5-8461-4f27-9cf0-7ee975da796a | app | watchlists | SELECT,UPDATE,DELETE,INSERT |
| adarsh.nandan@databricks.com | inventory_risk | risk_recommendations_online | SELECT,DELETE,TRUNCATE |
| databricks_superuser | inventory_risk | risk_recommendations_online | SELECT,INSERT,TRIGGER,REFERENCES,TRUNCATE,DELETE,UPDATE |
| f9d7ebf5-8461-4f27-9cf0-7ee975da796a | inventory_risk | risk_recommendations_online | SELECT |

### Lakebase -> Delta: planner_action_history in Unity Catalog

```sql
SELECT created_at, planner, action_type, action_qty, is_override, recommended_action, recommendation_id FROM serverless_stable_3vku19_catalog.inventory_risk.planner_action_history ORDER BY created_at DESC LIMIT 10
```

| created_at | planner | action_type | action_qty | is_override | recommended_action | recommendation_id |
|---|---|---|---|---|---|---|
| 2026-11-07T13:48:32.772Z | smoke-test@harvestlane.example | EXPEDITE | 348 | false | EXPEDITE | S044-P00043 |
