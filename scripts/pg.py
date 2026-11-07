"""Run SQL against the Lakebase app database as the current CLI user (OAuth token). Usage: python scripts/pg.py "SQL" """
import os
import sys

import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient(profile=os.environ.get("DATABRICKS_CONFIG_PROFILE", "serverless-stable-3vku19"))
EP = "projects/inventory-risk-radar/branches/production/endpoints/primary"
host = w.postgres.get_endpoint(name=EP).status.hosts.host
tok = w.postgres.generate_database_credential(endpoint=EP).token
with psycopg.connect(host=host, dbname=os.environ.get("PGDATABASE", "inventory_risk_app"), user=w.current_user.me().user_name,
                     password=tok, sslmode="require", autocommit=True) as c, c.cursor() as cur:
    for stmt in sys.argv[1:]:
        cur.execute(stmt)
        if cur.description:
            cols = [d.name for d in cur.description]
            print(" | ".join(cols))
            for r in cur.fetchall():
                print(" | ".join(str(v) for v in r))
        else:
            print("ok:", stmt[:100])
