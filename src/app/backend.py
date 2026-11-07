"""Data access for the planner app.

* Lakebase (Postgres): low-latency reads of the synced risk queue + transactional planner state
  (actions/overrides, notes, watchlists). OAuth tokens are minted with the app's service principal and
  refreshed before the 1-hour expiry; every new pooled connection gets a fresh token.
* Databricks SQL warehouse: analytical drill-down on Delta (daily forecast, inbound POs).
* Genie Conversation API: natural-language questions over the governed risk tables.
"""
import os
import time
from functools import lru_cache

import pandas as pd
import psycopg
from databricks import sql as dbsql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from psycopg_pool import ConnectionPool

CATALOG = os.getenv("UC_CATALOG", "serverless_stable_3vku19_catalog")
SCHEMA = os.getenv("UC_SCHEMA", "inventory_risk")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "210233ae7af4e4bb")
ENDPOINT = os.getenv("LAKEBASE_ENDPOINT", "projects/inventory-risk-radar/branches/production/endpoints/primary")
PG_DB = os.getenv("PGDATABASE", "inventory_risk_app")
GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")
SYNCED_TABLE = f'"{SCHEMA}"."risk_recommendations_online"'

cfg = Config()
w = WorkspaceClient()

_token = {"value": None, "expires": 0.0}


def _pg_token() -> str:
    if time.time() > _token["expires"] - 300:
        cred = w.postgres.generate_database_credential(endpoint=ENDPOINT)
        _token.update(value=cred.token, expires=time.time() + 3600)
    return _token["value"]


class _OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo: str = "", **kwargs):
        kwargs["password"] = _pg_token()
        return super().connect(conninfo, **kwargs)


@lru_cache(maxsize=1)
def pool() -> ConnectionPool:
    host = os.getenv("PGHOST") or w.postgres.get_endpoint(name=ENDPOINT).status.hosts.host
    user = os.getenv("PGUSER") or w.current_user.me().user_name
    conninfo = f"host={host} port={os.getenv('PGPORT', '5432')} dbname={PG_DB} user={user} sslmode=require application_name=inventory-risk-radar-app"
    p = ConnectionPool(conninfo, connection_class=_OAuthConnection, min_size=1, max_size=8, max_lifetime=2700, open=True,
                       kwargs={"autocommit": True})
    p.wait(timeout=60)
    return p


def pg_df(query: str, params=None) -> pd.DataFrame:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d.name for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def pg_exec(query: str, params=None) -> None:
    with pool().connection() as conn, conn.cursor() as cur:
        cur.execute(query, params)


APP_DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.planner_actions (
  action_id          BIGSERIAL PRIMARY KEY,
  recommendation_id  TEXT NOT NULL,
  store_id           TEXT NOT NULL,
  sku_id             TEXT NOT NULL,
  as_of_date         DATE NOT NULL,
  action_type        TEXT NOT NULL CHECK (action_type IN ('ACKNOWLEDGE','EXPEDITE','TRANSFER','REORDER','DISMISS')),
  action_qty         INTEGER,
  is_override        BOOLEAN NOT NULL DEFAULT FALSE,
  recommended_action TEXT,
  recommended_qty    INTEGER,
  risk_score         INTEGER,
  risk_tier          TEXT,
  reason             TEXT,
  planner            TEXT NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS planner_actions_rec_idx ON app.planner_actions (recommendation_id, created_at DESC);
CREATE TABLE IF NOT EXISTS app.planner_notes (
  note_id           BIGSERIAL PRIMARY KEY,
  recommendation_id TEXT NOT NULL,
  planner           TEXT NOT NULL,
  note              TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app.watchlists (
  planner           TEXT NOT NULL,
  recommendation_id TEXT NOT NULL,
  added_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (planner, recommendation_id)
);
GRANT USAGE ON SCHEMA app TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA app TO PUBLIC;
"""


def init_app_schema() -> None:
    pg_exec(APP_DDL)


def risk_queue() -> pd.DataFrame:
    df = pg_df(f"""
      SELECT r.recommendation_id, r.risk_rank, r.risk_score, r.risk_tier, r.store_id, r.store_name, r.region, r.sku_id, r.sku_name,
             r.category, r.supplier_name, r.on_hand_units, r.inbound_units_in_window, r.forecast_demand_window, r.baseline_demand_window,
             r.lead_time_window_days, r.days_of_cover, r.projected_stockout_in_days, r.stockout_probability, r.revenue_at_risk,
             r.primary_driver, r.driver_details, r.recommended_action, r.recommended_qty, r.action_source_id, r.action_rationale,
             r.planner_explanation, r.as_of_date, r.scored_at,
             a.action_type AS last_action, a.planner AS last_action_by, a.created_at AS last_action_at
      FROM {SYNCED_TABLE} r
      LEFT JOIN LATERAL (SELECT action_type, planner, created_at FROM app.planner_actions p
                         WHERE p.recommendation_id = r.recommendation_id AND p.as_of_date = r.as_of_date
                         ORDER BY created_at DESC LIMIT 1) a ON TRUE
      WHERE r.risk_tier IN ('Critical', 'High', 'Medium')
      ORDER BY r.risk_rank""")
    for c in ["stockout_probability", "revenue_at_risk", "forecast_demand_window", "baseline_demand_window", "days_of_cover", "projected_stockout_in_days"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def record_action(row: pd.Series, action_type: str, qty: int | None, reason: str, planner: str) -> None:
    is_override = action_type not in ("ACKNOWLEDGE", "DISMISS") and (action_type != row.recommended_action or qty != int(row.recommended_qty))
    pg_exec("""INSERT INTO app.planner_actions (recommendation_id, store_id, sku_id, as_of_date, action_type, action_qty, is_override,
               recommended_action, recommended_qty, risk_score, risk_tier, reason, planner)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (row.recommendation_id, row.store_id, row.sku_id, row.as_of_date, action_type, qty, is_override,
             row.recommended_action, int(row.recommended_qty), int(row.risk_score), row.risk_tier, reason or None, planner))


def add_note(rec_id: str, planner: str, note: str) -> None:
    pg_exec("INSERT INTO app.planner_notes (recommendation_id, planner, note) VALUES (%s,%s,%s)", (rec_id, planner, note))


def notes(rec_id: str) -> pd.DataFrame:
    return pg_df("SELECT planner, note, created_at FROM app.planner_notes WHERE recommendation_id = %s ORDER BY created_at DESC", (rec_id,))


def toggle_watch(planner: str, rec_id: str, on: bool) -> None:
    if on:
        pg_exec("INSERT INTO app.watchlists (planner, recommendation_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (planner, rec_id))
    else:
        pg_exec("DELETE FROM app.watchlists WHERE planner = %s AND recommendation_id = %s", (planner, rec_id))


def watchlist(planner: str) -> pd.DataFrame:
    return pg_df(f"""SELECT w.added_at, r.risk_rank, r.risk_score, r.risk_tier, r.store_name, r.sku_name, r.primary_driver,
                            r.recommended_action, r.recommended_qty, r.recommendation_id
                     FROM app.watchlists w JOIN {SYNCED_TABLE} r USING (recommendation_id)
                     WHERE w.planner = %s ORDER BY r.risk_rank""", (planner,))


def action_log(limit: int = 200) -> pd.DataFrame:
    return pg_df("""SELECT created_at, planner, action_type, action_qty, is_override, recommended_action, recommended_qty,
                           risk_tier, risk_score, store_id, sku_id, reason
                    FROM app.planner_actions ORDER BY created_at DESC LIMIT %s""", (limit,))


def action_kpis() -> pd.DataFrame:
    return pg_df(f"""
      WITH first_action AS (
        SELECT recommendation_id, min(created_at) AS first_at FROM app.planner_actions GROUP BY recommendation_id)
      SELECT count(*) FILTER (WHERE r.risk_tier IN ('Critical','High')) AS critical_high_alerts,
             count(f.first_at) FILTER (WHERE r.risk_tier IN ('Critical','High')) AS actioned,
             round(100.0 * count(f.first_at) FILTER (WHERE r.risk_tier IN ('Critical','High'))
                   / nullif(count(*) FILTER (WHERE r.risk_tier IN ('Critical','High')), 0), 1) AS pct_actioned,
             round(extract(epoch FROM percentile_cont(0.5) WITHIN GROUP (ORDER BY f.first_at - r.scored_at)) / 3600.0, 2) AS median_hours_to_action
      FROM {SYNCED_TABLE} r LEFT JOIN first_action f USING (recommendation_id)""")


# ---------------- SQL warehouse (Delta) ----------------

def _sql_conn():
    return dbsql.connect(server_hostname=cfg.host.replace("https://", ""), http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
                         credentials_provider=lambda: cfg.authenticate)


def sql_df(query: str, params: dict | None = None) -> pd.DataFrame:
    with _sql_conn() as conn, conn.cursor() as cur:
        cur.execute(query, params or {})
        return cur.fetchall_arrow().to_pandas()


def item_projection(store_id: str, sku_id: str) -> pd.DataFrame:
    return sql_df(f"""
      WITH f AS (SELECT target_date, horizon, forecast_units, baseline_units, on_promo
                 FROM {CATALOG}.{SCHEMA}.demand_forecast WHERE store_id = :store AND sku_id = :sku),
           inb AS (SELECT projected_arrival_date AS target_date, sum(order_qty) AS inbound_units
                   FROM {CATALOG}.{SCHEMA}.gold_inbound_po_pipeline WHERE store_id = :store AND sku_id = :sku GROUP BY 1),
           oh AS (SELECT eod_on_hand_units FROM {CATALOG}.{SCHEMA}.gold_current_inventory_position WHERE store_id = :store AND sku_id = :sku)
      SELECT f.target_date, f.horizon, f.forecast_units, f.baseline_units, f.on_promo, coalesce(inb.inbound_units, 0) AS inbound_units,
             (SELECT eod_on_hand_units FROM oh) AS on_hand_start
      FROM f LEFT JOIN inb USING (target_date) ORDER BY f.horizon""", {"store": store_id, "sku": sku_id})


def open_pos(store_id: str, sku_id: str) -> pd.DataFrame:
    return sql_df(f"""SELECT po_line_id, supplier_name, order_date, order_qty, expected_delivery_date, projected_arrival_date,
                             days_overdue_as_of, on_time_rate_last_30d
                      FROM {CATALOG}.{SCHEMA}.gold_inbound_po_pipeline WHERE store_id = :store AND sku_id = :sku
                      ORDER BY expected_delivery_date""", {"store": store_id, "sku": sku_id})


# ---------------- Genie ----------------

def ask_genie(question: str, conversation_id: str | None = None) -> dict:
    if not GENIE_SPACE_ID:
        return {"error": "Genie space not configured"}
    if conversation_id:
        msg = w.genie.create_message_and_wait(GENIE_SPACE_ID, conversation_id, question)
    else:
        msg = w.genie.start_conversation_and_wait(GENIE_SPACE_ID, question)
    out = {"conversation_id": msg.conversation_id, "text": None, "sql": None, "description": None, "table": None}
    for att in msg.attachments or []:
        if att.text and att.text.content:
            out["text"] = att.text.content
        if att.query:
            out["sql"], out["description"] = att.query.query, att.query.description
            try:
                res = w.genie.get_message_attachment_query_result(GENIE_SPACE_ID, msg.conversation_id, msg.id, att.attachment_id)
                sr = res.statement_response
                cols = [c.name for c in sr.manifest.schema.columns]
                out["table"] = pd.DataFrame(sr.result.data_array or [], columns=cols)
            except Exception as e:  # result fetch is best effort; SQL is still shown
                out["table_error"] = str(e)
    return out
