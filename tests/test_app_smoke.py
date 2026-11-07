"""Headless smoke test of the planner app against the real workspace (Lakebase, SQL warehouse, Genie).

Run: DATABRICKS_CONFIG_PROFILE=serverless-stable-3vku19 GENIE_SPACE_ID=<id> \
     uv run --with-requirements src/app/requirements.txt --with pytest pytest -q tests/test_app_smoke.py -s
"""
import os
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "src" / "app"
pytestmark = pytest.mark.skipif(not os.getenv("DATABRICKS_CONFIG_PROFILE"), reason="needs a workspace profile")


def test_app_renders_and_records_decision():
    sys.path.insert(0, str(APP_DIR))
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=180).run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    print("KPIs:", metrics)
    assert int(metrics["Critical"]) > 0
    assert len(at.tabs) == 4

    import backend as be
    q = be.risk_queue()
    row = q.iloc[0]
    print("top item:", row.risk_rank, row.store_name, row.sku_name, row.risk_tier, row.recommended_action, row.recommended_qty)
    be.record_action(row, row.recommended_action, int(row.recommended_qty), "Smoke test: supplier confirmed expedite", "smoke-test@harvestlane.example")
    be.add_note(row.recommendation_id, "smoke-test@harvestlane.example", "Called supplier; truck moved up by 2 days")
    be.toggle_watch("smoke-test@harvestlane.example", row.recommendation_id, True)
    log = be.action_log(5)
    assert (log.reason == "Smoke test: supplier confirmed expedite").any()
    assert row.recommendation_id in set(be.watchlist("smoke-test@harvestlane.example").recommendation_id)
    proj = be.item_projection(row.store_id, row.sku_id)
    assert len(proj) == 28
    print("projection rows:", len(proj), "| open POs:", len(be.open_pos(row.store_id, row.sku_id)))
    print(be.action_kpis().to_string(index=False))

    if os.getenv("GENIE_SPACE_ID"):
        ans = be.ask_genie("Which 5 store-SKUs have the highest revenue at risk?")
        print("Genie SQL:", (ans.get("sql") or "")[:300])
        print(ans.get("table").head() if ans.get("table") is not None else ans)
        assert ans.get("sql")
