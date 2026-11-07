"""Run SQL on the project's serverless SQL warehouse and print results as a Markdown table.

Usage: uv run --with databricks-sdk python scripts/run_sql.py "SELECT 1" [--out evidence/file.md --title "..."]
"""
import argparse
import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "serverless-stable-3vku19")
WAREHOUSE = os.environ.get("WAREHOUSE_ID", "210233ae7af4e4bb")


def run(sql: str, w: WorkspaceClient | None = None):
    w = w or WorkspaceClient(profile=PROFILE)
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=WAREHOUSE, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{r.status.state}: {r.status.error.message if r.status.error else ''}")
    cols = [c.name for c in r.manifest.schema.columns]
    rows = r.result.data_array or []
    return cols, rows


def to_md(cols, rows) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("" if v is None else str(v).replace("|", "/").replace("\n", " ") for v in row) + " |" for row in rows]
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sql")
    ap.add_argument("--out")
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    cols, rows = run(a.sql)
    md = to_md(cols, rows)
    print(md)
    if a.out:
        with open(a.out, "a") as f:
            f.write(f"\n### {a.title}\n\n```sql\n{a.sql.strip()}\n```\n\n{md}\n")
