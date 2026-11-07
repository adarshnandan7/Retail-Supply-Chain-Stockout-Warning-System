# Architecture - Retail Inventory Risk Radar

```
 Source systems (synthetic)          Lakeflow Declarative Pipeline (serverless)                Intelligence                     Serving & experience
 ─────────────────────────          ───────────────────────────────────────────              ────────────                     ────────────────────
 POS daily sales  (CSV)   ─┐        BRONZE  streaming tables (Auto Loader, append-only)        demand_forecast  (LightGBM       Lakebase Autoscaling (Postgres)
 Inventory snapshots (JSON)─┤  UC    bronze_pos_sales, bronze_inventory_snapshots,             @champion, 28-day, store/SKU)    ├─ inventory_risk.risk_recommendations_online
 PO events (JSON)          ─┤ Volume bronze_po_events, bronze_products, ...                          │                          │   (snapshot synced table, read path)
 Product / store /         ─┤ landing   │                                                           ▼                          └─ app.planner_actions / planner_notes /
 supplier masters (CSV)    ─┤           ▼                                                     risk_scores (transparent              watchlists (app writes)
 Promotion calendar (CSV)  ─┤        SILVER  validated (expectations), de-duplicated          stockout probability, drivers,             │
 Holidays (CSV)            ─┘        silver_pos_sales, silver_inventory_snapshots,             suggested action)                         ▼
                                     silver_po_events (ST) + masters (MV)                         │                          Databricks App "inventory-risk-radar"
                                        │                                                         ▼                          (Streamlit, app service principal)
                                        ▼                                                  ai_query (Claude Haiku)            ├─ risk queue (Lakebase, ms latency)
                                     GOLD  materialized views                              planner explanations               ├─ drill-down (SQL warehouse on Delta)
                                     gold_daily_store_sku_sales, gold_po_lines,                   │                          ├─ decisions/overrides/notes -> Lakebase
                                     gold_supplier_lead_time_stats, gold_inbound_po_pipeline,     ▼                          └─ Ask Genie tab (Conversation API)
                                     gold_current_inventory_position, gold_promo_store_sku_daily  risk_recommendations (Delta, CDF)
                                                                                                  │                          Genie space (metric definitions, certified SQL)
 Unity Catalog: one schema `inventory_risk` - tables, volumes, model, functions, metric views,   ├─> v_planner_risk_queue      AI/BI dashboard (ranked exceptions, accuracy)
 tags, comments, lineage, row filter/mask view, grants; MLflow experiment + UC model registry.    └─> mv_* metric views          planner_action_history (Lakebase -> Delta)
```

## Design decisions

| Decision | Why |
|---|---|
| Streaming tables for POS, inventory and PO events; materialized views for joins/aggregates | Append-only feeds are processed incrementally exactly once; joined/aggregated layers recompute correctly when masters change. |
| Inventory snapshots define the store/SKU/day grid | POS only emits non-zero rows; the grid makes zero-sales days and stockout days explicit. |
| Stockout days excluded from training labels and history averages | Sales on a day that ended at zero on hand are censored demand; including them teaches the model to under-forecast exactly the items that run out. |
| One global LightGBM, direct multi-horizon (1-28 days) | Learns shared promo/holiday/seasonality effects across 20,000 series; one model to govern instead of 20,000. Tweedie objective suits intermittent counts. |
| Seasonal-naive baseline logged as its own MLflow run | Value is shown against what planners already use, not against a straw man. |
| Risk score is deterministic and explainable (`src/risk/risk_logic.py`, unit-tested) | Planners must trust and challenge each alert; every number (window, probability, drivers in units) is traceable. The LLM only rephrases facts. |
| Replenishment window = mean actual supplier lead time over the last 30 days | Asks "will this run out before an order placed today arrives, given how the supplier is performing now" - picks up supplier disruptions immediately. |
| Overdue PO lines projected with the supplier's lateness-when-late | A line that is already late is not arriving tomorrow; this is what surfaces EXPEDITE actions. |
| Lakebase for app state, Delta for analytics | Decisions and notes need row-level transactional writes with low latency; history and KPIs belong in the lakehouse. Synced table keeps one source of truth (Delta) for recommendations. |
| Governed dynamic view instead of filters on base tables | Base tables are rewritten every run and feed the synced table; consumers get region row-filtering and revenue masking through `v_planner_risk_queue`. |
| Metric views for KPIs | Forecast error, stockout rate, cover/excess and alert precision are defined once and reused by Genie, the dashboard and the readout. |
| Everything in a Databricks Asset Bundle | Schema, volumes, pipeline, job, experiment, model, Lakebase project/database/synced table, Genie space, dashboard and app deploy with `databricks bundle deploy`. |

## Security

* App runs as its own service principal; resources (warehouse `CAN_USE`, Lakebase `CAN_CONNECT_AND_CREATE`, Genie `CAN_RUN`, table `SELECT`) are declared in `resources/app.yml`.
* Lakebase uses short-lived OAuth tokens (refreshed before the 1-hour expiry); no passwords or secrets in code.
* Users authenticate through workspace SSO; the app records the signed-in planner's email from the forwarded identity header.
* Consumers query `v_planner_risk_queue` (row filter by region group, revenue masked unless `supply_chain_finance`/admin).
* Synthetic data only; no customer data.

## Running it

```bash
databricks bundle deploy                       # all resources
databricks bundle run inventory_risk_radar_e2e # data -> pipeline -> model -> risk -> Gen AI -> governance -> metric views -> Lakebase
databricks bundle run planner_app              # start the app
```
