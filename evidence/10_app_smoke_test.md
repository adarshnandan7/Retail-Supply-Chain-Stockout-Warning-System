# Planner app: deployed status and headless functional test

_Captured 2026-11-07 14:19 UTC._

## Deployed app

- App: `inventory-risk-radar` (bundle resource `planner_app`), URL https://inventory-risk-radar-7474656932908638.aws.databricksapps.com
- Health endpoint with workspace OAuth: `ok HTTP 200`

### App log excerpt (`databricks apps logs`)

```text
2026-11-07T14:16:33Z [HTTP] 75.125.237.192 - 1417608165157698@7474656932908638 [07/Nov/2026:14:16:32 +0000] "GET /_stcore/health HTTP/1.1" 200 2 "-" "curl/8.7.1"
2026-11-07T14:18:31Z [BUILD] [INFO] Starting deployment 01f1dab61ad31533bf453da7f50fa1ff...
2026-11-07T14:18:31Z [APP]   Stopping...
2026-11-07T14:18:31Z [BUILD] [INFO] Downloading source code from /Workspace/Users/f9d7ebf5-8461-4f27-9cf0-7ee975da796a/src/01f1dab61ad31533bf453da7f50fa1ff
2026-11-07T14:18:31Z [BUILD] [INFO] Updated file: python/source_code/backend.py
2026-11-07T14:18:32Z [BUILD] [INFO] Updated file: python/source_code/app.yaml
2026-11-07T14:18:32Z [BUILD] [INFO] Updated file: python/source_code/requirements.txt
2026-11-07T14:18:32Z [BUILD] [INFO] Updated file: python/source_code/app.py
2026-11-07T14:18:32Z [BUILD] [INFO] Requirements have not changed. Skipping installation.
2026-11-07T14:18:32Z [BUILD] [INFO] Starting app with command: [streamlit run app.py --server.headless true]
2026-11-07T14:18:33Z [APP] 
  You can now view your Streamlit app in your browser.

  URL: 
2026-11-07T14:18:33Z [APP] http://0.0.0.0:8000
2026-11-07T14:18:34Z [BUILD] [INFO] Deployment 01f1dab61ad31533bf453da7f50fa1ff ended in 3.272530569s
2026-11-07T14:18:34Z [BUILD] [INFO] Deployment successful
2026-11-07T14:19:39Z [HTTP] 75.125.237.192 - 1417608165157698@7474656932908638 [07/Nov/2026:14:19:39 +0000] "GET /_stcore/health HTTP/1.1" 200 2 "-" "curl/8.7.1"
```

## Headless functional test (`tests/test_app_smoke.py`)

Runs `src/app/app.py` with Streamlit `AppTest` against the real Lakebase database, SQL warehouse and Genie space. It checks that the KPIs render, the 4 tabs exist, a planner decision, note and watchlist entry round-trip through Lakebase, the 28-day drill-down returns from Delta, and Genie answers with SQL.

```text
KPIs: {'Critical': '808', 'High': '1530', 'Revenue at risk (Critical+High)': '$53,020', 'Stockouts projected ≤ 3 days': '1863', 'Actioned': '1 (0%)', 'Critical/High alerts': '2338', 'Median time to planner action': '0.20 h'}
top item: 1 Harvest Lane Stonebrook Superstore II Meadow Fresh Green Beans 2ct Critical EXPEDITE 348
projection rows: 28 | open POs: 1
 critical_high_alerts  actioned pct_actioned median_hours_to_action
                 2338         1          0.0                   0.20
Genie SQL: WITH ranked AS (
  SELECT
    risk_recommendations.risk_rank,
    risk_recommendations.store_name,
    risk_recommendations.sku_name,
    risk_recommendations.risk_tier,
    risk_recommendations.risk_score,
    risk_recommendations.revenue_at_risk,
    risk_recommendations.primary_driver,
    risk_r
  risk_rank  ... recommended_qty
0         1  ...             348
1         2  ...             138
2         3  ...             192
3         4  ...             204
4       231  ...             180

[5 rows x 9 columns]
.
1 passed in 48.38s
```
